# ── app/services/ai_gateway.py ───────────────────────────────────────────────
# AI Gateway Central — ponto único de acesso à inteligência artificial do EJC.
#
# PRINCÍPIO: Nenhuma tela acessa diretamente um modelo. Tudo passa por aqui.
#
# Fluxo:
#   Frontend → Backend Router → AI Gateway → Provedor adequado (Ollama/Groq)
#
# Roteamento por tipo de tarefa:
#   analise_juridica   → DeepSeek R1 (profundidade) → Qwen 2.5 → Groq llama3
#   elaboracao_peca    → Qwen 2.5 (qualidade textual) → Groq
#   resumo             → Gemma 3 (rápido) → Groq
#   chat_rapido        → Gemma 3 → Llama 3.2 → Groq
#   analise_contrato   → DeepSeek R1 → Qwen → Groq
#   estrategia         → DeepSeek R1 (raciocínio) → Groq
#   auditoria_peca     → Qwen 2.5 → Groq
#   jurimetria         → DeepSeek R1 → Groq
#
# Fallback automático: se o modelo primário falhar, tenta o próximo da cadeia.
# Quando AI_PROVIDER="auto" → Ollama (local) tem prioridade; Groq como fallback.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.core.config import get_settings
from app.services import legal_base

logger = logging.getLogger("ejc.ai.gateway")
settings = get_settings()

# ── Tipos de tarefa e cadeia de modelos ──────────────────────────────────────
# Cada tarefa lista provedores em ordem de preferência: (provider, model).
# "groq" usa o modelo configurado em GROQ_MODEL / GROQ_MODEL_LARGE.
# "ollama" usa o modelo local especificado.

TASK_ALIASES = {
    "redacao_peca": "elaboracao_peca",
    "redacao_juridica": "elaboracao_peca",
    "peca_juridica": "elaboracao_peca",
    "analise_caso": "estrategia",
    "pesquisa_juridica": "analise_juridica",
    "rag_query": "analise_juridica",
}

NIVEL_INTELIGENCIA_PROMPTS = {
    "padrao": "Responda com objetividade, precisao e foco pratico.",
    "alto": (
        "Ative raciocinio juridico senior: decomponha o problema em fatos, direito, prova, "
        "risco e estrategia; identifique lacunas, contradicoes, teses alternativas e providencias; "
        "nao invente fontes."
    ),
    "maximo": (
        "Ative modo de inteligencia maxima: faca leitura adversarial, teste hipoteses concorrentes, "
        "analise preliminares, merito, prova, quantum, acordo e risco; entregue conclusoes verificaveis, "
        "separando fato, inferencia, lacuna e decisao humana pendente. Nao revele cadeia de pensamento."
    ),
}


def _normalizar_task_type(task_type: str) -> str:
    return TASK_ALIASES.get(task_type, task_type)


def _aplicar_nivel(messages: list[dict], nivel_inteligencia: str | None) -> list[dict]:
    nivel = (nivel_inteligencia or "padrao").lower()
    instrucao = NIVEL_INTELIGENCIA_PROMPTS.get(nivel)
    if not instrucao:
        return messages
    extra = {"role": "system", "content": f"NIVEL DE INTELIGENCIA: {nivel.upper()}\n{instrucao}"}
    return [extra] + messages


TASK_ROUTING: dict[str, list[tuple[str, str | None]]] = {
    # Tarefas COMPLEXAS incluem "anthropic" na cadeia (Núcleo Único): entra na
    # ordem de AI_PROVIDER_PRIORITY quando elegível (chave + ENABLED +
    # AI_EXTERNAL_PROVIDERS_ALLOWED) — ver _resolver_cadeia.
    "analise_juridica": [
        ("ollama",    None),  # resolvido em runtime para OLLAMA_MODEL_ANALISE
        ("anthropic", None),  # ANTHROPIC_MODEL_COMPLEXO
        ("groq",      None),
    ],
    "elaboracao_peca": [
        ("ollama",    None),  # OLLAMA_MODEL_PETICAO
        ("anthropic", None),
        ("groq",      None),
    ],
    "resumo": [
        ("ollama", None),    # OLLAMA_MODEL_RESUMO
        ("groq",   None),
    ],
    "chat_rapido": [
        ("ollama", None),    # OLLAMA_MODEL_CHAT
        ("groq",   None),
    ],
    "analise_contrato": [
        ("ollama",    None),  # OLLAMA_MODEL_CONTRATO
        ("anthropic", None),
        ("groq",      None),
    ],
    "estrategia": [
        ("ollama",    None),  # OLLAMA_MODEL_ANALISE (raciocínio profundo)
        ("anthropic", None),
        ("groq",      None),
    ],
    "auditoria_peca": [
        ("ollama",    None),  # OLLAMA_MODEL_PETICAO
        ("anthropic", None),
        ("groq",      None),
    ],
    "jurimetria": [
        ("ollama",    None),  # OLLAMA_MODEL_ANALISE
        ("anthropic", None),
        ("groq",      None),
    ],
}

# Provedores que processam dados FORA do VPS → barreira LGPD obrigatória.
_PROVIDERS_EXTERNOS = {"anthropic", "groq"}

_OLLAMA_MODEL_BY_TASK = {
    "analise_juridica": lambda: settings.OLLAMA_MODEL_ANALISE,
    "elaboracao_peca":  lambda: settings.OLLAMA_MODEL_PETICAO,
    "resumo":           lambda: settings.OLLAMA_MODEL_RESUMO,
    "chat_rapido":      lambda: settings.OLLAMA_MODEL_CHAT,
    "analise_contrato": lambda: settings.OLLAMA_MODEL_CONTRATO,
    "estrategia":       lambda: settings.OLLAMA_MODEL_ANALISE,
    "auditoria_peca":   lambda: settings.OLLAMA_MODEL_PETICAO,
    "jurimetria":       lambda: settings.OLLAMA_MODEL_ANALISE,
}


@dataclass
class GatewayResponse:
    texto: str
    modelo: str
    provedor: str
    task_type: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    duracao_ms: int = 0
    fallback_ativado: bool = False
    fallback_motivo: str | None = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


async def chat(
    messages: list[dict],
    task_type: str = "analise_juridica",
    temperature: float = 0.2,
    max_tokens: int = 2048,
    model_override: str | None = None,
    provider_override: str | None = None,
    nivel_inteligencia: str | None = None,
) -> GatewayResponse:
    """
    Ponto central de chamada à IA.

    Parâmetros:
      messages        — mensagens no formato OpenAI [{role, content}, ...]
      task_type       — tipo de tarefa (define qual modelo usar)
      model_override  — forçar modelo específico (ex: "deepseek-r1:14b")
      provider_override — forçar provedor ("groq" | "ollama")

    Retorna GatewayResponse com texto, metadados e informações de fallback.
    """
    task_type = _normalizar_task_type(task_type)
    t0 = time.monotonic()
    fallback_ativado = False
    fallback_motivo: str | None = None

    # #8 — injeta a identidade do escritório no system (apenas tarefas de prosa).
    messages = _aplicar_nivel(legal_base.aplicar_base(messages, task_type), nivel_inteligencia)

    # AI_PROVIDER="groq" → ignora Ollama; "ollama" → falha se Ollama down
    provider_force = provider_override or (
        settings.AI_PROVIDER if settings.AI_PROVIDER != "auto" else None
    )

    # Cadeia de tentativas
    cadeia = _resolver_cadeia(task_type, provider_force, model_override)

    ultimo_erro: str = "Nenhum provedor disponível"
    bloqueado_por_pii = False
    for i, (provider, model) in enumerate(cadeia):
        if i > 0:
            fallback_ativado = True
        # ── Barreira FINAL LGPD (Núcleo Único): provider EXTERNO só recebe
        # conteúdo sanitizado. Se após sanitizar ainda houver PII estrutural,
        # este provedor é PULADO (tenta o próximo — ex.: Ollama local).
        # Nunca ecoa o conteúdo — só os TIPOS de PII no log.
        messages_envio = messages
        if provider in _PROVIDERS_EXTERNOS and settings.AI_REQUIRE_SANITIZATION_FOR_EXTERNAL:
            messages_envio, residual = _sanitizar_messages_externo(messages)
            if residual:
                bloqueado_por_pii = True
                ultimo_erro = f"PII residual ({', '.join(residual)}) bloqueou provider externo"
                fallback_motivo = f"{provider}: bloqueado por PII residual (LGPD)"
                logger.warning(
                    f"[Gateway] {provider} pulado — PII residual ({', '.join(residual)}) "
                    "após sanitização (LGPD)."
                )
                continue
        try:
            texto, usage = await _chamar_provedor(
                provider, model, messages_envio, temperature, max_tokens
            )
            duracao = int((time.monotonic() - t0) * 1000)
            resp = GatewayResponse(
                texto=texto,
                modelo=usage.get("model", model or ""),
                provedor=provider,
                task_type=task_type,
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
                duracao_ms=duracao,
                fallback_ativado=fallback_ativado,
                fallback_motivo=fallback_motivo if fallback_ativado else None,
            )
            if fallback_ativado:
                logger.warning(
                    f"[Gateway] Fallback ativado → {provider}/{model}. "
                    f"Motivo: {fallback_motivo}"
                )
            else:
                logger.info(
                    f"[Gateway] {task_type} → {provider}/{usage.get('model')} "
                    f"({duracao}ms)"
                )
            return resp
        except Exception as e:
            ultimo_erro = str(e)[:200]
            fallback_motivo = f"{provider}: {ultimo_erro}"
            logger.warning(
                f"[Gateway] {provider}/{model} falhou, tentando próximo: {ultimo_erro}"
            )

    if bloqueado_por_pii:
        # Mensagem segura: não ecoa o conteúdo nem os valores de PII.
        raise RuntimeError(
            "Conteúdo com dados pessoais não pode ir a provider externo — "
            "configure Ollama ou revise o texto"
        )
    raise RuntimeError(
        f"Todos os provedores falharam para task={task_type}. "
        f"Último erro: {ultimo_erro}"
    )


async def health() -> dict:
    """Retorna status de saúde de cada provedor."""
    from app.services.providers import groq_provider, ollama_provider, anthropic_provider
    groq_ok   = await groq_provider.health()   if settings.GROQ_API_KEY else False
    ollama_ok = await ollama_provider.health() if settings.OLLAMA_ENABLED else False
    anthropic_ok = await anthropic_provider.health()
    modelos_ollama = await ollama_provider.modelos_disponiveis() if settings.OLLAMA_ENABLED else []

    return {
        "groq":      {"disponivel": groq_ok, "modelo": settings.GROQ_MODEL},
        "ollama":    {"disponivel": ollama_ok, "modelos": modelos_ollama},
        "anthropic": {"disponivel": anthropic_ok, "modelo": settings.ANTHROPIC_MODEL_RAPIDO},
        "provider_mode": settings.AI_PROVIDER,
    }


# ── Helpers internos ──────────────────────────────────────────────────────────

def _provider_elegivel(provider: str) -> bool:
    """Elegibilidade por provedor (mesmas regras da AIProviderPolicy)."""
    if provider == "ollama":
        return bool(settings.OLLAMA_ENABLED)
    if provider == "anthropic":
        return bool(
            settings.ANTHROPIC_ENABLED and settings.ANTHROPIC_API_KEY
            and settings.AI_EXTERNAL_PROVIDERS_ALLOWED
        )
    if provider == "groq":
        return bool(settings.GROQ_API_KEY and settings.AI_EXTERNAL_PROVIDERS_ALLOWED)
    return False


def _ordenar_por_prioridade(providers: list[str]) -> list[str]:
    """Ordena a lista pela AI_PROVIDER_PRIORITY (csv); desconhecidos vão ao fim
    mantendo a ordem original do TASK_ROUTING."""
    prioridade = [p.strip().lower() for p in (settings.AI_PROVIDER_PRIORITY or "").split(",") if p.strip()]

    def _chave(p: str) -> int:
        return prioridade.index(p) if p in prioridade else len(prioridade)

    return sorted(providers, key=_chave)


def _resolver_modelo(provider: str, task_type: str, model_override: str | None) -> str | None:
    """Modelo default por provedor/tarefa (None = default do próprio provider)."""
    if model_override:
        return model_override
    if provider == "ollama":
        return _OLLAMA_MODEL_BY_TASK.get(task_type, lambda: settings.OLLAMA_MODEL_ANALISE)()
    if provider == "anthropic":
        # Tarefas roteadas para Anthropic aqui são as complexas → modelo COMPLEXO.
        return settings.ANTHROPIC_MODEL_COMPLEXO or settings.ANTHROPIC_MODEL_RAPIDO
    return None  # groq: default do provedor


def _resolver_cadeia(
    task_type: str,
    provider_force: str | None,
    model_override: str | None,
) -> list[tuple[str, str | None]]:
    """Resolve a cadeia de (provider, model) para a tarefa, respeitando
    AI_PROVIDER_PRIORITY e a elegibilidade de cada provedor."""
    if provider_force in ("groq", "ollama", "anthropic"):
        return [(provider_force, _resolver_modelo(provider_force, task_type, model_override))]

    base = TASK_ROUTING.get(task_type, TASK_ROUTING["analise_juridica"])
    candidatos = _ordenar_por_prioridade([p for p, _ in base])
    cadeia = [
        (p, _resolver_modelo(p, task_type, model_override))
        for p in candidatos
        if _provider_elegivel(p)
    ]

    if not cadeia:
        # Último recurso: Groq sem checar chave (vai falhar com erro claro)
        cadeia = [("groq", model_override)]
    return cadeia


def _sanitizar_messages_externo(messages: list[dict]) -> tuple[list[dict], list[str]]:
    """Barreira FINAL de LGPD antes de provider externo (Anthropic/Groq):
    sanitiza o content de CADA mensagem e devolve a lista de tipos de PII
    residual (vazia = liberado). NUNCA loga/ecoa o conteúdo em si."""
    from app.services.sanitizer import sanitizar_pii, validar_sem_pii
    limpos: list[dict] = []
    residual: set[str] = set()
    for m in messages:
        conteudo = m.get("content", "") or ""
        limpo, _ = sanitizar_pii(conteudo)
        residual.update(validar_sem_pii(limpo))
        novo = dict(m)
        novo["content"] = limpo
        limpos.append(novo)
    return limpos, sorted(residual)


async def _chamar_provedor(
    provider: str,
    model: str | None,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
) -> tuple[str, dict]:
    """Despacha para o provedor correto."""
    if provider == "ollama":
        from app.services.providers import ollama_provider
        return await ollama_provider.chat(
            messages, model or settings.OLLAMA_MODEL_ANALISE,
            temperature, max_tokens,
        )
    elif provider == "anthropic":
        from app.services.providers import anthropic_provider
        return await anthropic_provider.chat(messages, model, temperature, max_tokens)
    else:  # groq
        from app.services.providers import groq_provider
        return await groq_provider.chat(messages, model, temperature, max_tokens)


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO IA PROFISSIONAL — agente por tarefa (system_prompts + Anthropic/Groq).
# Reusa _chamar_provedor (mesmo dispatch). HITL/LGPD/auditoria preservados.
# ══════════════════════════════════════════════════════════════════════════════
import os as _os

_PRICING_USD_MM = {
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-6":         {"input": 3.00, "output": 15.00},
    "claude-opus-4-8":           {"input": 15.00, "output": 75.00},
}


def _custo_brl(model: str, inp: int, out: int) -> float:
    p = _PRICING_USD_MM.get(model, {"input": 0.0, "output": 0.0})
    usd = (inp * p["input"] + out * p["output"]) / 1_000_000
    return round(usd * float(_os.getenv("USD_BRL_RATE", "5.70")), 4)


async def executar_tarefa_ia(tarefa, mensagem: str, case_id: str | None = None,
                             contexto_rag: list[str] | None = None,
                             user_id: str | None = None, db=None,
                             nivel_inteligencia: str = "alto") -> dict:
    """Entrada do MÓDULO IA por tarefa. Resultado SEMPRE rascunho (HITL/OAB).

    Auditoria 2026-07-04 (P1-1/P2-1): este caminho aplica as MESMAS regras do
    chat() — elegibilidade por provedor (inclui o kill-switch de soberania
    AI_EXTERNAL_PROVIDERS_ALLOWED) e barreira final de sanitização antes de
    provider EXTERNO (cobre o contexto RAG, que pode conter PII de precedentes
    internos). AILog via ai_guard (canônico): erro de gravação PROPAGA."""
    from app.services.system_prompts import SYSTEM_PROMPTS, get_configuracao
    cfg = get_configuracao(tarefa)
    system_prompt = SYSTEM_PROMPTS.get(cfg.prompt_key, SYSTEM_PROMPTS["default"])
    if contexto_rag:
        trechos = "\n\n---\n\n".join(f"Trecho {i+1}:\n{c}" for i, c in enumerate(contexto_rag))
        system_prompt += f"\n\n## CONHECIMENTO RECUPERADO (BASE INTERNA):\n{trechos}"
    messages = _aplicar_nivel([{ "role": "system", "content": system_prompt },
                {"role": "user", "content": mensagem}], nivel_inteligencia)

    # Cadeia: provedor da tarefa → Groq (custo ~zero) → Ollama (local).
    cadeia: list[tuple[str, str | None]] = [(cfg.provider, cfg.model)]
    if cfg.provider != "groq":
        cadeia.append(("groq", None))
    if settings.OLLAMA_ENABLED and cfg.provider != "ollama":
        cadeia.append(("ollama", None))

    texto = usage = provedor_usado = None
    ultimo_erro = "nenhum provedor elegível"
    bloqueado_por_pii = False
    for provider, model in cadeia:
        if not _provider_elegivel(provider):
            ultimo_erro = f"{provider} inelegível (habilitação/chave/soberania)"
            continue
        messages_envio = messages
        if provider in _PROVIDERS_EXTERNOS and settings.AI_REQUIRE_SANITIZATION_FOR_EXTERNAL:
            messages_envio, residual = _sanitizar_messages_externo(messages)
            if residual:
                bloqueado_por_pii = True
                ultimo_erro = f"PII residual ({', '.join(residual)}) bloqueou provider externo"
                logger.warning(f"[Gateway] {provider} pulado em executar_tarefa_ia — "
                               f"PII residual ({', '.join(residual)}) após sanitização (LGPD).")
                continue
        try:
            texto, usage = await _chamar_provedor(provider, model, messages_envio,
                                                  cfg.temperature, cfg.max_tokens)
            provedor_usado = provider
            break
        except Exception as e:
            ultimo_erro = str(e)[:120]
            logger.warning(f"[Gateway] {provider} falhou em executar_tarefa_ia; "
                           f"tentando próximo: {ultimo_erro}")
    if provedor_usado is None:
        if bloqueado_por_pii:
            raise RuntimeError(
                "Conteúdo com dados pessoais não pode ir a provider externo — "
                "configure Ollama ou revise o texto"
            )
        raise RuntimeError(f"Nenhum provedor disponível para a tarefa. Último erro: {ultimo_erro}")

    inp = usage.get("input_tokens") or 0
    out = usage.get("output_tokens") or 0
    modelo_real = usage.get("model", cfg.model or "")
    custo = _custo_brl(modelo_real, inp, out) if provedor_usado == "anthropic" else 0.0
    if db is not None and user_id:
        # Canônico (ai_guard): tipo_uso mapeado para o enum real e erro PROPAGA —
        # IA sem trilha de auditoria deve falhar, não responder em silêncio.
        from app.services.ai_guard import registrar_ai_log
        from app.services.ai.core.audit_logger import _tipo_uso
        await registrar_ai_log(
            db, user_id=user_id, tipo_uso=_tipo_uso(tarefa), case_id=case_id,
            prompt_sanitizado=mensagem[:8000], pii_removida=False,
            resposta=texto, modelo=f"{provedor_usado}/{modelo_real}",
            tokens_input=inp, tokens_output=out, custo_estimado=custo,
        )
    return {
        "conteudo": texto, "modelo": f"{provedor_usado}/{modelo_real}", "provider": provedor_usado,
        "nivel_inteligencia": nivel_inteligencia,
        "tarefa": getattr(tarefa, "value", str(tarefa)),
        "is_rascunho": True, "requer_revisao": True,
        "tokens_usados": inp + out, "custo_estimado_brl": custo,
    }
