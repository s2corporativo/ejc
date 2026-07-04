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
    "analise_juridica": [
        ("ollama", None),    # resolvido em runtime para OLLAMA_MODEL_ANALISE
        ("groq",   None),
    ],
    "elaboracao_peca": [
        ("anthropic", settings.ANTHROPIC_MODEL_RAZOES),  # Claude: redação jurídica de alta qualidade
        ("ollama", None),    # OLLAMA_MODEL_PETICAO
        ("groq",   None),
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
        ("ollama", None),    # OLLAMA_MODEL_CONTRATO
        ("groq",   None),
    ],
    "estrategia": [
        ("anthropic", settings.ANTHROPIC_MODEL_RAZOES),  # Claude: raciocínio jurídico adversarial
        ("ollama", None),    # OLLAMA_MODEL_ANALISE (raciocínio profundo)
        ("groq",   None),
    ],
    "auditoria_peca": [
        ("ollama", None),    # OLLAMA_MODEL_PETICAO
        ("groq",   None),
    ],
    "jurimetria": [
        ("ollama", None),    # OLLAMA_MODEL_ANALISE
        ("groq",   None),
    ],
}

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
    for i, (provider, model) in enumerate(cadeia):
        if i > 0:
            fallback_ativado = True
        try:
            texto, usage = await _chamar_provedor(
                provider, model, messages, temperature, max_tokens
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

    raise RuntimeError(
        f"Todos os provedores falharam para task={task_type}. "
        f"Último erro: {ultimo_erro}"
    )


async def health() -> dict:
    """Retorna status de saúde de cada provedor."""
    from app.services.providers import groq_provider, ollama_provider
    groq_ok   = await groq_provider.health()   if settings.GROQ_API_KEY else False
    ollama_ok = await ollama_provider.health() if settings.OLLAMA_ENABLED else False
    modelos_ollama = await ollama_provider.modelos_disponiveis() if settings.OLLAMA_ENABLED else []

    return {
        "groq":   {"disponivel": groq_ok, "modelo": settings.GROQ_MODEL},
        "ollama": {"disponivel": ollama_ok, "modelos": modelos_ollama},
        "provider_mode": settings.AI_PROVIDER,
    }


# ── Helpers internos ──────────────────────────────────────────────────────────

def _resolver_cadeia(
    task_type: str,
    provider_force: str | None,
    model_override: str | None,
) -> list[tuple[str, str | None]]:
    """Resolve a cadeia de (provider, model) para a tarefa."""
    if provider_force == "groq":
        return [("groq", model_override)]
    if provider_force == "ollama":
        modelo = model_override or _OLLAMA_MODEL_BY_TASK.get(task_type, lambda: None)()
        return [("ollama", modelo)]

    base = TASK_ROUTING.get(task_type, TASK_ROUTING["analise_juridica"])
    cadeia = []
    for provider, modelo_cadeia in base:
        if provider == "ollama" and not settings.OLLAMA_ENABLED:
            continue  # pular Ollama se desabilitado
        if provider == "groq" and not settings.GROQ_API_KEY:
            continue  # pular Groq sem chave
        if provider == "anthropic" and not settings.ANTHROPIC_API_KEY:
            continue  # pular Claude sem chave → cai para Ollama/Groq
        modelo_resolvido: str | None = None
        if provider == "ollama":
            modelo_resolvido = model_override or _OLLAMA_MODEL_BY_TASK.get(
                task_type, lambda: settings.OLLAMA_MODEL_ANALISE
            )()
        else:
            # Respeita o modelo declarado na cadeia (ex.: claude-sonnet-5);
            # model_override tem prioridade. None (Groq) = default do provedor.
            modelo_resolvido = model_override or modelo_cadeia
        cadeia.append((provider, modelo_resolvido))

    if not cadeia:
        # Último recurso: Groq sem checar chave (vai falhar com erro claro)
        cadeia = [("groq", model_override)]
    return cadeia


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
from uuid import uuid4 as _uuid4
from sqlalchemy import text as _sql_text

# Preços oficiais Anthropic (USD por 1.000.000 de tokens) — conferidos 2026-07.
# Sonnet 5 tem preço promocional US$2/US$10 até 2026-08-31; usamos o de tabela
# (US$3/US$15) para não subestimar o custo na auditoria de gasto.
_PRICING_USD_MM = {
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
    "claude-haiku-4-5":          {"input": 1.00, "output": 5.00},
    "claude-sonnet-4-6":         {"input": 3.00, "output": 15.00},
    "claude-sonnet-5":           {"input": 3.00, "output": 15.00},
    "claude-opus-4-8":           {"input": 5.00, "output": 25.00},
}


def _custo_brl(model: str, inp: int, out: int) -> float:
    p = _PRICING_USD_MM.get(model, {"input": 0.0, "output": 0.0})
    usd = (inp * p["input"] + out * p["output"]) / 1_000_000
    return round(usd * float(_os.getenv("USD_BRL_RATE", "5.70")), 4)


async def _registrar_ai_log(db, user_id, case_id, tipo_uso, modelo, inp, out, custo):
    """Grava na tabela REAL ai_logs (HITL). Fail-safe."""
    from app.models.ai_log import normalizar_modelo_ia  # BUG-22: nome canônico
    try:
        await db.execute(_sql_text("""
            INSERT INTO ai_logs (id, user_id, case_id, tipo_uso, modelo,
                                 tokens_input, tokens_output, custo_estimado, status_hitl, created_at)
            VALUES (:id, :uid, :cid, :tipo, :modelo, :ti, :to, :custo, 'gerado', now())
        """), {"id": str(_uuid4()), "uid": user_id, "cid": case_id, "tipo": tipo_uso,
               "modelo": normalizar_modelo_ia(modelo), "ti": inp or 0, "to": out or 0, "custo": custo})
        await db.commit()
    except Exception as e:
        logger.warning(f"[Gateway] ai_logs falhou: {e}")


async def executar_tarefa_ia(tarefa, mensagem: str, case_id: str | None = None,
                             contexto_rag: list[str] | None = None,
                             user_id: str | None = None, db=None,
                             nivel_inteligencia: str = "alto") -> dict:
    """Entrada do MÓDULO IA por tarefa. Resultado SEMPRE rascunho (HITL/OAB)."""
    from app.services.system_prompts import SYSTEM_PROMPTS, get_configuracao
    cfg = get_configuracao(tarefa)
    system_prompt = SYSTEM_PROMPTS.get(cfg.prompt_key, SYSTEM_PROMPTS["default"])
    if contexto_rag:
        trechos = "\n\n---\n\n".join(f"Trecho {i+1}:\n{c}" for i, c in enumerate(contexto_rag))
        system_prompt += f"\n\n## CONHECIMENTO RECUPERADO (BASE INTERNA):\n{trechos}"
    messages = _aplicar_nivel([{ "role": "system", "content": system_prompt },
                {"role": "user", "content": mensagem}], nivel_inteligencia)
    try:
        texto, usage = await _chamar_provedor(cfg.provider, cfg.model, messages, cfg.temperature, cfg.max_tokens)
        provedor_usado = cfg.provider
    except Exception as e:
        # Fallback custo-baixo: Anthropic indisponível (sem chave/limite) → Groq grátis.
        if cfg.provider == "anthropic" and settings.GROQ_API_KEY:
            logger.warning(f"[Gateway] anthropic falhou ({str(e)[:80]}); fallback Groq.")
            texto, usage = await _chamar_provedor("groq", None, messages, cfg.temperature, cfg.max_tokens)
            provedor_usado = "groq"
        else:
            raise
    inp = usage.get("input_tokens") or 0
    out = usage.get("output_tokens") or 0
    modelo_real = usage.get("model", cfg.model or "")
    custo = _custo_brl(modelo_real, inp, out) if provedor_usado == "anthropic" else 0.0
    if db is not None and user_id:
        await _registrar_ai_log(db, user_id, case_id, getattr(tarefa, "value", str(tarefa)),
                                f"{provedor_usado}/{modelo_real}", inp, out, custo)
    return {
        "conteudo": texto, "modelo": f"{provedor_usado}/{modelo_real}", "provider": provedor_usado,
        "nivel_inteligencia": nivel_inteligencia,
        "tarefa": getattr(tarefa, "value", str(tarefa)),
        "is_rascunho": True, "requer_revisao": True,
        "tokens_usados": inp + out, "custo_estimado_brl": custo,
    }
