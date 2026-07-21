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
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.core.config import get_settings
from app.services import legal_base
from app.services.ai_cost import estimar_custo_brl

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
    # Raciocinio estruturado pelo metodo FIRAC (auditoria IA 2026-07-17, O-3):
    # forca a decomposicao juridica e amarra cada premissa a uma fonte verificavel
    # (casa com o gate de citacoes anti-alucinacao).
    "alto": (
        "Ative raciocinio juridico senior e estruture pelo metodo FIRAC: "
        "(1) FATOS relevantes, separando fato de inferencia e apontando lacunas; "
        "(2) QUESTAO juridica central; "
        "(3) REGRA aplicavel, citando o dispositivo/sumula/precedente que a sustenta "
        "(NUNCA invente fonte; sem certeza, escreva 'verificar fonte'); "
        "(4) APLICACAO da regra aos fatos, com teses alternativas e contra-argumentos; "
        "(5) CONCLUSAO com nivel de confianca e providencias. "
        "Identifique contradicoes e o que ainda depende de decisao humana."
    ),
    "maximo": (
        "Ative modo de inteligencia maxima: leitura adversarial e teste de hipoteses "
        "concorrentes, estruturando pelo metodo FIRAC (fato / questao / regra-com-fonte / "
        "aplicacao / conclusao). Analise preliminares, merito, prova, quantum, acordo e risco; "
        "para CADA premissa juridica cite o dispositivo/sumula/precedente ou marque "
        "'verificar fonte' (nunca invente). Separe explicitamente FATO, INFERENCIA, LACUNA e "
        "DECISAO HUMANA PENDENTE, e entregue conclusoes verificaveis com nivel de confianca. "
        "Nao revele a cadeia de pensamento — entregue apenas o resultado estruturado."
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


# Cadeias: Ollama (local, custo zero) → Anthropic (qualidade, se houver chave)
# → Groq (grátis, último recurso). Tarefas simples (resumo/chat) pulam o
# Anthropic — Groq grátis basta e mantém o custo baixo.
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
        ("maritaca",  None),  # MARITACA_MODEL (provider BR para redação jurídica PT-BR)
        ("anthropic", None),  # ANTHROPIC_MODEL_COMPLEXO
        ("groq",      None),
    ],
    "resumo": [
        ("ollama", None),    # OLLAMA_MODEL_RESUMO
        ("maritaca", None),  # MARITACA_MODEL_RAPIDO (só se ENABLED+chave)
        ("groq",   None),
    ],
    "chat_rapido": [
        ("ollama", None),    # OLLAMA_MODEL_CHAT
        ("maritaca", None),  # MARITACA_MODEL_RAPIDO (só se ENABLED+chave)
        ("groq",   None),
    ],
    "analise_contrato": [
        ("ollama",    None),  # OLLAMA_MODEL_CONTRATO
        ("maritaca",  None),  # MARITACA_MODEL (provider BR para contratos)
        ("anthropic", None),
        ("groq",      None),
    ],
    "estrategia": [
        ("ollama",    None),  # OLLAMA_MODEL_ANALISE (raciocínio profundo)
        ("maritaca",  None),  # MARITACA_MODEL (provider BR para estratégia jurídica)
        ("anthropic", None),
        ("groq",      None),
    ],
    "auditoria_peca": [
        ("ollama",    None),  # OLLAMA_MODEL_PETICAO
        ("maritaca",  None),  # MARITACA_MODEL (provider BR para auditoria)
        ("anthropic", None),
        ("groq",      None),
    ],
    "jurimetria": [
        ("ollama",    None),  # OLLAMA_MODEL_ANALISE
        ("maritaca",  None),  # MARITACA_MODEL (provider BR para jurimetria)
        ("anthropic", None),
        ("groq",      None),
    ],
    # Fase 5 — Modo Duas IAs: crítica adversarial de peça (leitura como
    # advogado da parte contrária/magistrado). Tarefa COMPLEXA: inclui
    # Anthropic/Maritaca. O chamador (services/ai/adversarial.py) ainda prefere
    # provider DIFERENTE do que gerou a peça via provider_override.
    "critica_adversarial": [
        ("ollama",    None),  # OLLAMA_MODEL_ANALISE (raciocínio crítico)
        ("maritaca",  None),  # MARITACA_MODEL (provider BR para crítica jurídica)
        ("anthropic", None),
        ("groq",      None),
    ],
}

# Provedores que processam dados FORA do VPS → barreira LGPD obrigatória.
_PROVIDERS_EXTERNOS = {"anthropic", "groq", "maritaca"}

_OLLAMA_MODEL_BY_TASK = {
    "analise_juridica": lambda: settings.OLLAMA_MODEL_ANALISE,
    "elaboracao_peca":  lambda: settings.OLLAMA_MODEL_PETICAO,
    "resumo":           lambda: settings.OLLAMA_MODEL_RESUMO,
    "chat_rapido":      lambda: settings.OLLAMA_MODEL_CHAT,
    "analise_contrato": lambda: settings.OLLAMA_MODEL_CONTRATO,
    "estrategia":       lambda: settings.OLLAMA_MODEL_ANALISE,
    "auditoria_peca":   lambda: settings.OLLAMA_MODEL_PETICAO,
    "jurimetria":       lambda: settings.OLLAMA_MODEL_ANALISE,
    "critica_adversarial": lambda: settings.OLLAMA_MODEL_ANALISE,
}

# Modelo Claude por tarefa: complexas → COMPLEXO (qualidade); simples → RAPIDO.
_ANTHROPIC_MODEL_BY_TASK = {
    "analise_juridica": lambda: settings.ANTHROPIC_MODEL_COMPLEXO,
    "elaboracao_peca":  lambda: settings.ANTHROPIC_MODEL_COMPLEXO,
    "resumo":           lambda: settings.ANTHROPIC_MODEL_RAPIDO,
    "chat_rapido":      lambda: settings.ANTHROPIC_MODEL_RAPIDO,
    "analise_contrato": lambda: settings.ANTHROPIC_MODEL_COMPLEXO,
    "estrategia":       lambda: settings.ANTHROPIC_MODEL_COMPLEXO,
    "auditoria_peca":   lambda: settings.ANTHROPIC_MODEL_COMPLEXO,
    "jurimetria":       lambda: settings.ANTHROPIC_MODEL_COMPLEXO,
    "critica_adversarial": lambda: settings.ANTHROPIC_MODEL_COMPLEXO,
}


def _anthropic_key() -> str:
    """Mesma resolução do provider: Settings tipada → os.getenv (docker env_file)."""
    return settings.ANTHROPIC_API_KEY or os.getenv("ANTHROPIC_API_KEY", "")


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
    # Fase 6 — custo estimado (R$) pela tabela de preços; roteamento inteligente.
    custo_estimado_brl: float = 0.0
    roteamento_tier: str | None = None
    roteamento_score: int | None = None
    # True quando a resposta veio do cache (dedup de requisição idêntica).
    cache_hit: bool = False
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class _ProviderPulado(Exception):
    """A barreira LGPD PULOU este provider (PII residual após a sanitização): o
    chamador deve tentar o PRÓXIMO da cadeia, não tratar como falha do provider.
    O conteúdo NUNCA foi enviado ao provider externo."""

    def __init__(self, residual):
        self.residual = list(residual)
        super().__init__("PII residual: " + ", ".join(self.residual))


async def _chamar_com_barreira(provider, model, messages, modo_sanitizacao,
                               entidades, temperature, max_tokens):
    """Barreira FINAL LGPD + chamada ao provider + reidratação — FONTE ÚNICA.

    #39: antes esta lógica estava DUPLICADA em chat() e executar_tarefa_ia(); duas
    cópias de um controle de PII arriscam divergência silenciosa. Consolidada aqui:
      - provider EXTERNO só recebe conteúdo sanitizado; se após sanitizar ainda
        sobra PII estrutural, levanta _ProviderPulado (o chamador pula p/ o
        próximo, ex.: Ollama local) — o conteúdo nunca é enviado nem ecoado;
      - chama o provider e REIDRATA a resposta devolvida ao chamador (modo
        reversível). O `texto_para_log` fica SEM PII real (pseudonimizado) — é a
        versão que deve ir a log/observabilidade.

    Retorna (texto, texto_para_log, usage, messages_envio, pii_removida).
    """
    messages_envio = messages
    # `mapa_reidratacao` contém PII real (só EXTERNO_PSEUDONIMIZADO): vive só
    # nesta chamada/memória, nunca é logado/persistido/enviado.
    mapa_reidratacao = None
    if provider in _PROVIDERS_EXTERNOS and settings.AI_REQUIRE_SANITIZATION_FOR_EXTERNAL:
        messages_envio, residual, mapa_reidratacao = _preparar_mensagens_externo(
            messages, modo_sanitizacao, entidades
        )
        if residual:
            raise _ProviderPulado(residual)
    texto, usage = await _chamar_provedor(provider, model, messages_envio,
                                          temperature, max_tokens)
    # Reidratação LOCAL: só a resposta DEVOLVIDA recupera o dado real; a versão
    # pseudonimizada (texto_para_log) é a que vai à observabilidade.
    texto_para_log = texto
    if mapa_reidratacao:
        from app.services.ai.pseudonymizer import reidratar
        texto = reidratar(texto, mapa_reidratacao)
    return texto, texto_para_log, usage, messages_envio, bool(mapa_reidratacao)


async def chat(
    messages: list[dict],
    task_type: str = "analise_juridica",
    temperature: float = 0.2,
    max_tokens: int = 2048,
    model_override: str | None = None,
    provider_override: str | None = None,
    nivel_inteligencia: str | None = None,
    entidades: dict[str, list[str]] | None = None,
) -> GatewayResponse:
    """
    Ponto central de chamada à IA.

    Parâmetros:
      messages        — mensagens no formato OpenAI [{role, content}, ...]
      task_type       — tipo de tarefa (define qual modelo usar)
      model_override  — forçar modelo específico (ex: "deepseek-r1:14b")
      provider_override — forçar provedor ("groq" | "ollama")
      entidades       — nomes próprios a pseudonimizar por tipo (opcional):
                        {"cliente": [...], "empresa": [...], "advogado": [...],
                        "parte_contraria": [...]}. Só usado em modo
                        EXTERNO_PSEUDONIMIZADO/EXTRACAO_LOCAL antes de provider
                        externo. None (default) = só PII estrutural (não quebra
                        os call sites existentes).

    Retorna GatewayResponse com texto, metadados e informações de fallback.
    """
    # Modo de sanitização de PII é decidido pelo task_type ORIGINAL (antes dos
    # aliases do gateway), pois o mapeamento LGPD usa o vocabulário de tarefa.
    task_type_original = task_type
    task_type = _normalizar_task_type(task_type)
    t0 = time.monotonic()
    fallback_ativado = False
    fallback_motivo: str | None = None

    from app.services.ai.sanitization_policy import ModoSanitizacao, modo_para_task
    modo_sanitizacao = modo_para_task(task_type_original)

    # #8 — injeta a identidade do escritório no system (apenas tarefas de prosa).
    messages = _aplicar_nivel(legal_base.aplicar_base(messages, task_type), nivel_inteligencia)

    # ── Cache de resposta (opt-in): dedup de requisição idêntica dentro do TTL.
    # Chaveado pelas messages FINAIS + parâmetros que afetam a saída. Nunca
    # quebra o fluxo (ai_cache engole erros) e só serve respostas gravadas de
    # chamadas bem-sucedidas anteriores.
    from app.services import ai_cache
    _cache_key = ai_cache.chave(
        task_type, messages, temperature=temperature, max_tokens=max_tokens,
        model_override=model_override, provider_override=provider_override,
        nivel_inteligencia=nivel_inteligencia,
        # AI_PROVIDER global entra na chave: se a config trocar (ex.: auto→groq)
        # sem override explícito, não serve resposta de outro provedor no TTL.
        ai_provider=settings.AI_PROVIDER,
    )
    _cached = await ai_cache.obter(_cache_key)
    if _cached:
        logger.info("[Gateway] cache HIT → %s (sem chamada ao provedor)", task_type)
        # Tokens/custo ZERADOS no hit: não houve chamada real ao provedor, então
        # contabilizá-los (AILog/dashboards) inflaria o gasto de IA (dupla
        # contagem). cache_hit=True sinaliza a origem; texto é o cacheado.
        return GatewayResponse(
            texto=_cached.get("texto", ""),
            modelo=_cached.get("modelo", ""),
            provedor=_cached.get("provedor", ""),
            task_type=task_type,
            input_tokens=0,
            output_tokens=0,
            duracao_ms=0,
            custo_estimado_brl=0.0,
            cache_hit=True,
        )

    # AI_PROVIDER="groq" → ignora Ollama; "ollama" → falha se Ollama down
    provider_force = provider_override or (
        settings.AI_PROVIDER if settings.AI_PROVIDER != "auto" else None
    )

    # ── Fase 6 — Roteamento inteligente (opt-in): PROPÕE provedor de partida ──
    # por complexidade/custo. Sem override e só quando ligado. O gateway ainda
    # aplica elegibilidade/PII/fallback — o roteador não sobrepõe nada disso.
    provider_preferido = model_preferido = None
    roteamento_tier = roteamento_score = None
    if (
        settings.ROTEAMENTO_INTELIGENTE_ENABLED
        and not provider_override
        and not model_override
    ):
        try:
            from app.services.ai.model_router import escolher_modelo
            texto_entrada = "\n".join(m.get("content", "") or "" for m in messages)
            decisao = escolher_modelo(task_type, texto_entrada)
            provider_preferido, model_preferido = decisao.provider, decisao.model
            roteamento_tier, roteamento_score = decisao.tier, decisao.score
            logger.info("[Gateway] roteamento inteligente → %s", decisao.motivo)
        except Exception as e:  # roteamento nunca quebra a chamada de IA
            logger.warning("[Gateway] roteamento inteligente falhou: %s", str(e)[:200])

    # Cadeia de tentativas
    cadeia = _resolver_cadeia(
        task_type, provider_force, model_override, provider_preferido, model_preferido
    )

    # ── Modo 1 (LOCAL_COMPLETO) — sigilo reforçado: a tarefa NUNCA pode ir a
    # provider externo (nem pseudonimizada). Filtra a cadeia para providers
    # LOCAIS; sem local elegível → bloqueio SEGURO (não vaza o conteúdo).
    if modo_sanitizacao == ModoSanitizacao.LOCAL_COMPLETO:
        cadeia = _restringir_cadeia_local_completo(cadeia, modo_sanitizacao, task_type_original)
        if not cadeia:
            raise RuntimeError(_MSG_BLOQUEIO_LOCAL_COMPLETO)

    # ── Fase 6 — Observabilidade (Langfuse self-hosted, NO-OP se desligado) ──
    from app.services.observability import langfuse_client as _lf
    _trace = _lf.novo_trace(
        name=task_type,
        metadata={"task_type": task_type, "nivel_inteligencia": nivel_inteligencia,
                  "roteamento_tier": roteamento_tier, "roteamento_score": roteamento_score},
    )

    ultimo_erro: str = "Nenhum provedor disponível"
    bloqueado_por_pii = False
    for i, (provider, model) in enumerate(cadeia):
        if i > 0:
            fallback_ativado = True
        try:
            # #39: barreira LGPD + chamada ao provider + reidratação num ÚNICO
            # ponto (fonte compartilhada com executar_tarefa_ia). Se o provider
            # externo é PULADO por PII residual, _chamar_com_barreira levanta
            # _ProviderPulado (tratado abaixo — tenta o próximo da cadeia).
            texto, texto_para_log, usage, messages_envio, _ = await _chamar_com_barreira(
                provider, model, messages, modo_sanitizacao, entidades,
                temperature, max_tokens,
            )
            duracao = int((time.monotonic() - t0) * 1000)
            modelo_real = usage.get("model", model or "")
            inp = usage.get("input_tokens")
            out = usage.get("output_tokens")
            # Custo pela fonte ÚNICA (ai_cost): ciente do PROVEDOR real — Groq
            # não fica mais zerado (bug anterior: só havia preço Anthropic aqui).
            custo_brl = float(estimar_custo_brl(provider, inp or 0, out or 0, modelo_real))
            resp = GatewayResponse(
                texto=texto,
                modelo=modelo_real,
                provedor=provider,
                task_type=task_type,
                input_tokens=inp,
                output_tokens=out,
                duracao_ms=duracao,
                fallback_ativado=fallback_ativado,
                fallback_motivo=fallback_motivo if fallback_ativado else None,
                custo_estimado_brl=custo_brl,
                roteamento_tier=roteamento_tier,
                roteamento_score=roteamento_score,
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
            _lf.registrar_generation(
                _trace, name=task_type, model=modelo_real,
                input_messages=messages_envio, output_text=texto_para_log,
                input_tokens=inp, output_tokens=out,
                metadata=_lf.montar_metadata(
                    provider=provider, model=modelo_real, task_type=task_type,
                    input_tokens=inp, output_tokens=out, duracao_ms=duracao,
                    fallback_ativado=fallback_ativado, fallback_motivo=fallback_motivo,
                    custo_estimado_brl=custo_brl, sucesso=True,
                    tier=roteamento_tier, roteamento_score=roteamento_score,
                ),
            )
            _lf.flush()
            # Grava no cache apenas respostas bem-sucedidas (TTL curto).
            await ai_cache.gravar(_cache_key, {
                "texto": texto, "modelo": modelo_real, "provedor": provider,
                "input_tokens": inp, "output_tokens": out,
                "custo_estimado_brl": custo_brl,
            })
            return resp
        except _ProviderPulado as _pulado:
            # Barreira LGPD pulou este provider (PII residual) → tenta o próximo.
            bloqueado_por_pii = True
            ultimo_erro = f"PII residual ({', '.join(_pulado.residual)}) bloqueou provider externo"
            fallback_motivo = f"{provider}: bloqueado por PII residual (LGPD)"
            logger.warning(
                f"[Gateway] {provider} pulado — PII residual ({', '.join(_pulado.residual)}) "
                "após sanitização (LGPD)."
            )
            _lf.registrar_evento(_trace, name=f"pii_bloqueio:{provider}",
                                 metadata={"provider": provider, "task_type": task_type})
            continue
        except Exception as e:
            ultimo_erro = str(e)[:200]  # trilha INTERNA (logger + RuntimeError)
            # B1: no que sai ao Langfuse (fallback_motivo → metadata; evento),
            # nunca o str(e) cru (pode conter PII/detalhe do provider): só a
            # CLASSE do erro (+ status HTTP quando houver).
            _status = getattr(e, "status_code", None) or getattr(
                getattr(e, "response", None), "status_code", None
            )
            erro_traco = type(e).__name__ + (f" (HTTP {_status})" if _status else "")
            fallback_motivo = f"{provider}: {erro_traco}"
            logger.warning(
                f"[Gateway] {provider}/{model} falhou, tentando próximo: {ultimo_erro}"
            )
            _lf.registrar_evento(_trace, name=f"fallback:{provider}",
                                 metadata={"provider": provider, "model": model,
                                           "task_type": task_type, "erro": erro_traco})

    _lf.flush()
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


async def transcrever_audio(
    *,
    file_bytes: bytes,
    filename: str,
    language: str = "pt",
    confirmacao_envio_externo: bool = False,
) -> dict:
    """Ponto único para transcrição de mídia em provedor externo.

    Diferentemente de texto, o áudio bruto não pode ser pseudonimizado antes da
    transcrição. Por isso o recurso nasce desligado, exige confirmação em cada
    requisição e respeita o kill-switch global de provedores externos. O arquivo
    não é persistido nem enviado à observabilidade por este fluxo.
    """
    if not confirmacao_envio_externo:
        raise PermissionError(
            "Confirme o envio temporário da mídia ao provedor externo para transcrição."
        )
    if not settings.AI_ENABLED or not settings.AUDIO_TRANSCRIPTION_ENABLED:
        raise RuntimeError(
            "Transcrição de mídia desabilitada. Ative AUDIO_TRANSCRIPTION_ENABLED após validação de privacidade."
        )
    if not settings.AI_EXTERNAL_PROVIDERS_ALLOWED:
        raise RuntimeError(
            "Provedores externos estão desabilitados pela política de soberania de dados."
        )
    if not settings.GROQ_ZDR_VERIFIED:
        raise RuntimeError(
            "Transcrição bloqueada: confirme Zero Data Retention nos Data Controls do Groq e marque GROQ_ZDR_VERIFIED."
        )
    if not settings.AUDIO_TRANSCRIPTION_DPA_APPROVED:
        raise RuntimeError(
            "Transcrição bloqueada: aprove e documente DPA/transferência internacional antes de marcar AUDIO_TRANSCRIPTION_DPA_APPROVED."
        )
    if not settings.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY não configurada para transcrição.")
    if not file_bytes:
        raise ValueError("Mídia vazia.")
    limite = settings.AUDIO_TRANSCRIPTION_MAX_MB * 1024 * 1024
    if len(file_bytes) > limite:
        raise ValueError(
            f"Mídia excede o limite configurado de {settings.AUDIO_TRANSCRIPTION_MAX_MB} MB."
        )
    language = (language or "pt").strip().lower()
    if language not in {"pt", "en", "es"}:
        raise ValueError("Idioma não suportado. Use pt, en ou es.")

    from app.services.providers import groq_provider

    try:
        texto, metadata = await groq_provider.transcrever(
            file_bytes,
            filename,
            language=language,
            model=settings.GROQ_TRANSCRIPTION_MODEL,
            timeout=settings.AUDIO_TRANSCRIPTION_TIMEOUT,
        )
    except (ValueError, PermissionError):
        raise
    except Exception as exc:
        logger.warning(
            "[Gateway] transcrição Groq falhou: %s", type(exc).__name__
        )
        raise RuntimeError(
            "Não foi possível transcrever a mídia no provedor configurado."
        ) from exc

    logger.info(
        "[Gateway] mídia transcrita por groq/%s (%d bytes; conteúdo não registrado)",
        metadata.get("model"),
        len(file_bytes),
    )
    return {"texto": texto, **metadata}


async def health() -> dict:
    """Retorna status de saúde de cada provedor."""
    from app.services.providers import groq_provider, ollama_provider, anthropic_provider, maritaca_provider
    groq_ok   = await groq_provider.health()   if settings.GROQ_API_KEY else False
    ollama_ok = await ollama_provider.health() if settings.OLLAMA_ENABLED else False
    anthropic_ok = await anthropic_provider.health()
    maritaca_ok = await maritaca_provider.health() if settings.MARITACA_ENABLED else False
    modelos_ollama = await ollama_provider.modelos_disponiveis() if settings.OLLAMA_ENABLED else []

    return {
        "groq":      {"disponivel": groq_ok, "modelo": settings.GROQ_MODEL},
        "ollama":    {"disponivel": ollama_ok, "modelos": modelos_ollama},
        "anthropic": {"disponivel": anthropic_ok, "modelo": settings.ANTHROPIC_MODEL_RAPIDO},
        "maritaca":  {"disponivel": maritaca_ok, "modelo": settings.MARITACA_MODEL},
        "provider_mode": settings.AI_PROVIDER,
    }


# ── Disponibilidade por CONFIGURAÇÃO (leve — sem chamada de rede) ─────────────
# Usado por GET /api/ia/status e pelos payloads degradados: responde "existe ao
# menos um provedor configurado/habilitado?" olhando apenas settings, ao
# contrário de health(), que bate em cada provedor.

def provedores_configurados() -> list[str]:
    """Provedores elegíveis pela configuração atual (mesmas regras da cadeia)."""
    return [p for p in ("ollama", "anthropic", "groq", "maritaca")
            if _provider_elegivel(p)]


def ia_disponivel() -> bool:
    """True se a IA está habilitada E há ao menos um provedor configurado."""
    return bool(settings.AI_ENABLED) and bool(provedores_configurados())


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
    if provider == "maritaca":
        return bool(
            settings.MARITACA_ENABLED and settings.MARITACA_API_KEY
            and settings.AI_EXTERNAL_PROVIDERS_ALLOWED
        )
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
    if provider == "maritaca":
        # Redação/volume por default; tarefas simples → modelo rápido/barato.
        if task_type in ("resumo", "chat_rapido", "triagem"):
            return settings.MARITACA_MODEL_RAPIDO or settings.MARITACA_MODEL
        return settings.MARITACA_MODEL or settings.MARITACA_MODEL_RAPIDO
    return None  # groq: default do provedor


def _resolver_cadeia(
    task_type: str,
    provider_force: str | None,
    model_override: str | None,
    provider_preferido: str | None = None,
    model_preferido: str | None = None,
) -> list[tuple[str, str | None]]:
    """Resolve a cadeia de (provider, model) para a tarefa, respeitando
    AI_PROVIDER_PRIORITY e a elegibilidade de cada provedor.

    `provider_preferido` (roteamento inteligente, Fase 6) só é uma PROPOSTA de
    provedor de PARTIDA: se elegível, vai à frente da cadeia; o resto do fallback
    é preservado. Inelegível → ignorado (cadeia normal). NUNCA sobrepõe um
    provider_force explícito nem a barreira de elegibilidade/PII."""
    if provider_force in ("groq", "ollama", "anthropic"):
        if _provider_elegivel(provider_force):
            return [(provider_force, _resolver_modelo(provider_force, task_type, model_override))]
        # Provider forçado inelegível (sem chave/desabilitado/policy): não
        # falhar duro — loga e cai no roteamento automático, preservando o
        # comportamento das EJC skills com engine fixo.
        logger.warning(
            "[Gateway] provider '%s' forçado mas inelegível "
            "(chave/enable/policy); usando cadeia automática.",
            provider_force,
        )

    base = TASK_ROUTING.get(task_type, TASK_ROUTING["analise_juridica"])
    candidatos = _ordenar_por_prioridade([p for p, _ in base])

    # Roteamento inteligente: promove o provider proposto à frente SE elegível e
    # SE participa da cadeia da tarefa (não inventa provedor fora do TASK_ROUTING).
    if (
        provider_preferido in ("groq", "ollama", "anthropic")
        and provider_preferido in candidatos
        and _provider_elegivel(provider_preferido)
    ):
        candidatos = [provider_preferido] + [p for p in candidatos if p != provider_preferido]

    cadeia = [
        (
            p,
            model_preferido if (p == provider_preferido and model_preferido)
            else _resolver_modelo(p, task_type, model_override),
        )
        for p in candidatos
        if _provider_elegivel(p)
    ]

    if not cadeia:
        # Último recurso: Groq sem checar chave (vai falhar com erro claro)
        cadeia = [("groq", model_override)]
    return cadeia


def _sanitizar_messages_externo(messages: list[dict]) -> tuple[list[dict], list[str]]:
    """Barreira FINAL antes de provider externo (Anthropic/Groq). REATIVADA na
    auditoria técnica (LGPD art. 33/46 — dado pessoal não pode seguir em claro a
    provedor fora do VPS): sanitizar_pii mascara CPF/CNPJ/processo/RG/e-mail/
    telefone/CEP/cartão/PIX e validar_sem_pii detecta PII residual. Uso 100%
    interno (Ollama local) mantém CPF/CNPJ via sanitizar_pii_interno."""
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


def _pseudonimizar_messages_externo(
    messages: list[dict],
    entidades: dict[str, list[str]] | None = None,
) -> tuple[list[dict], list[str], dict[str, str]]:
    """Barreira EXTERNO_PSEUDONIMIZADO (Modo 2+3): substitui PII por marcadores
    CONSISTENTES e REVERSÍVEIS (mesma entidade → mesmo marcador em todas as
    mensagens), verifica PII residual (segunda barreira `validar_sem_pii`) e
    devolve também o `mapa` (marcador → valor real) para REIDRATAR a resposta.

    `entidades` (opcional) protege nomes próprios por tipo — {"cliente": [...],
    "empresa": [...], "advogado": [...], "parte_contraria": [...]}: sem ela,
    apenas PII estrutural (CPF/CNPJ/processo/…) é pseudonimizada.

    ⚠️ O `mapa` contém PII real: fica só em memória na request; jamais é logado,
    persistido (AILog/Langfuse) ou enviado a provider externo. O que segue ao
    Anthropic/Groq são as mensagens já pseudonimizadas."""
    from app.services.ai.pseudonymizer import (
        pseudonimizar_mensagens,
        validar_sem_pii_pseudonimizado,
    )
    limpos, mapa = pseudonimizar_mensagens(messages, entidades)
    residual: set[str] = set()
    for m in limpos:
        residual.update(validar_sem_pii_pseudonimizado(m.get("content", "") or ""))
    return limpos, sorted(residual), mapa


# ── Política de modo de sanitização (compartilhada por chat() e
#    executar_tarefa_ia() — fonte única para não divergirem) ────────────────────
_MSG_BLOQUEIO_LOCAL_COMPLETO = (
    "Esta tarefa exige processamento por IA local (sigilo reforçado) "
    "e nenhum provedor local está disponível — habilite o Ollama."
)


def _restringir_cadeia_local_completo(cadeia, modo, task_label):
    """Modo 1 (LOCAL_COMPLETO): remove providers EXTERNOS da cadeia — a tarefa
    nunca pode sair do VPS (nem pseudonimizada). Retorna a cadeia filtrada; se
    esvaziar, loga e o chamador deve levantar bloqueio SEGURO (sem vazar conteúdo)."""
    from app.services.ai.sanitization_policy import ModoSanitizacao
    if modo != ModoSanitizacao.LOCAL_COMPLETO:
        return cadeia
    filtrada = [(p, m) for (p, m) in cadeia if p not in _PROVIDERS_EXTERNOS]
    if not filtrada:
        logger.warning(
            "[Gateway] task=%s exige IA local (sigilo reforçado) e não há "
            "provedor local elegível — chamada bloqueada (LGPD).",
            task_label,
        )
    return filtrada


def _preparar_mensagens_externo(messages, modo, entidades=None):
    """Barreira final por-provider EXTERNO conforme o modo. Retorna sempre
    (messages_envio, residual, mapa): `mapa` só é não-vazio no modo REVERSÍVEL
    (EXTERNO_PSEUDONIMIZADO/EXTRACAO_LOCAL); em MASCARAMENTO é None (irreversível)."""
    from app.services.ai.sanitization_policy import ModoSanitizacao
    if modo in (ModoSanitizacao.EXTERNO_PSEUDONIMIZADO, ModoSanitizacao.EXTRACAO_LOCAL):
        return _pseudonimizar_messages_externo(messages, entidades)
    limpos, residual = _sanitizar_messages_externo(messages)
    return limpos, residual, None


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
    elif provider == "maritaca":
        from app.services.providers import maritaca_provider
        return await maritaca_provider.chat(messages, model, temperature, max_tokens)
    else:  # groq
        from app.services.providers import groq_provider
        return await groq_provider.chat(messages, model, temperature, max_tokens)


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO IA PROFISSIONAL — agente por tarefa (system_prompts + Anthropic/Groq).
# Reusa _chamar_provedor (mesmo dispatch). HITL/LGPD/auditoria preservados.
# ══════════════════════════════════════════════════════════════════════════════
def _custo_brl(model: str, inp: int, out: int) -> float:
    """Shim de compatibilidade → ai_cost.estimar_custo_brl (fonte única de preço).

    Chamadores legados (skill_registry/orchestrator/ai_skill_service) só computam
    custo de peça Anthropic e passam o MODELO; delega assumindo provedor
    "anthropic" (modelo fora da tabela → 0, comportamento idêntico ao anterior).
    Novos call sites devem usar estimar_custo_brl(provedor, inp, out, modelo)."""
    return round(float(estimar_custo_brl("anthropic", inp, out, model)), 4)


async def executar_tarefa_ia(tarefa, mensagem: str, case_id: str | None = None,
                             contexto_rag: list[str] | None = None,
                             user_id: str | None = None, db=None,
                             nivel_inteligencia: str = "alto",
                             entidades: dict[str, list[str]] | None = None,
                             modo_sanitizacao=None) -> dict:
    """Entrada do MÓDULO IA por tarefa. Resultado SEMPRE rascunho (HITL/OAB).

    Auditoria 2026-07-04 (P1-1/P2-1): este caminho aplica as MESMAS regras do
    chat() — elegibilidade por provedor (inclui o kill-switch de soberania
    AI_EXTERNAL_PROVIDERS_ALLOWED) e barreira final de sanitização antes de
    provider EXTERNO (cobre o contexto RAG, que pode conter PII de precedentes
    internos). AILog via ai_guard (canônico): erro de gravação PROPAGA.

    Auditoria 2026-07-05: aplica a MESMA política de MODO de sanitização por
    tarefa do chat() (sanitization_policy) — LOCAL_COMPLETO nunca vai a externo;
    EXTERNO_PSEUDONIMIZADO/EXTRACAO_LOCAL pseudonimizam (reversível) e reidratam
    a resposta; MASCARAMENTO mantém o mascaramento irreversível legado. O `mapa`
    de reidratação vive só em memória; AILog/Langfuse recebem versão PSEUDONIMIZADA."""
    from app.services.ai.sanitization_policy import (
        ModoSanitizacao, modo_para_task, reforcar_sigilo,
    )
    from app.services.system_prompts import SYSTEM_PROMPTS, get_configuracao
    tarefa_label = str(getattr(tarefa, "value", tarefa))
    # S1: o modo da TAREFA é reforçado (nunca rebaixado) pelo sigilo da ÁREA do
    # caso quando o chamador (ex.: tool de escrita do agente) o informa — assim o
    # roteamento por TarefaIA não ignora um caso LOCAL_COMPLETO.
    modo_sanitizacao = reforcar_sigilo(modo_para_task(tarefa_label), modo_sanitizacao)
    cfg = get_configuracao(tarefa)
    system_prompt = SYSTEM_PROMPTS.get(cfg.prompt_key, SYSTEM_PROMPTS["default"])
    if contexto_rag:
        trechos = "\n\n---\n\n".join(f"Trecho {i+1}:\n{c}" for i, c in enumerate(contexto_rag))
        system_prompt += f"\n\n## CONHECIMENTO RECUPERADO (BASE INTERNA):\n{trechos}"
    messages = _aplicar_nivel([{ "role": "system", "content": system_prompt },
                {"role": "user", "content": mensagem}], nivel_inteligencia)

    # #40: dedup de chamada de IA no caminho por tarefa — reusa o mesmo ai_cache
    # que o chat() já usa. Requisições idênticas (mesma tarefa/mensagem/contexto/
    # nível) servem do cache no TTL, sem bater o provedor (economia de tokens e
    # latência). A chave usa as mensagens REAIS (pré-sanitização), então inputs
    # distintos nunca colidem.
    from app.services import ai_cache
    _cache_key = ai_cache.chave(
        tarefa_label, messages, temperature=cfg.temperature, max_tokens=cfg.max_tokens,
        model_override=cfg.model, provider_override=cfg.provider,
        nivel_inteligencia=nivel_inteligencia, ai_provider=settings.AI_PROVIDER,
    )
    _cached = await ai_cache.obter(_cache_key)
    if _cached:
        logger.info("[Gateway] cache HIT (tarefa) → %s (sem chamada ao provedor)", tarefa_label)
        return {
            "conteudo": _cached.get("texto", ""), "modelo": _cached.get("modelo", ""),
            "provider": _cached.get("provedor", ""),
            "nivel_inteligencia": nivel_inteligencia, "tarefa": tarefa_label,
            "is_rascunho": True, "requer_revisao": True,
            "tokens_usados": 0, "custo_estimado_brl": 0.0, "cache_hit": True,
        }

    # Cadeia: provedor da tarefa → Groq (custo ~zero) → Ollama (local).
    cadeia: list[tuple[str, str | None]] = [(cfg.provider, cfg.model)]
    if cfg.provider != "groq":
        cadeia.append(("groq", None))
    if settings.OLLAMA_ENABLED and cfg.provider != "ollama":
        cadeia.append(("ollama", None))

    # ── Modo 1 (LOCAL_COMPLETO) — sigilo reforçado: nunca sai do VPS. Remove
    # externos; sem provedor local ELEGÍVEL → bloqueio SEGURO (externo nunca é
    # chamado; a mensagem não vaza conteúdo). Espelha o chat().
    if modo_sanitizacao == ModoSanitizacao.LOCAL_COMPLETO:
        cadeia = _restringir_cadeia_local_completo(cadeia, modo_sanitizacao, tarefa_label)
        if not any(_provider_elegivel(p) for p, _ in cadeia):
            logger.warning(
                "[Gateway] executar_tarefa_ia task=%s exige IA local (sigilo "
                "reforçado) e não há provedor local elegível — bloqueada (LGPD).",
                tarefa_label,
            )
            raise RuntimeError(_MSG_BLOQUEIO_LOCAL_COMPLETO)

    texto = usage = provedor_usado = None
    ultimo_erro = "nenhum provedor elegível"
    bloqueado_por_pii = False
    # Log LGPD: por padrão o prompt cru; no modo reversível será o PSEUDONIMIZADO.
    resposta_log = None
    prompt_log = mensagem[:8000]
    pii_removida_log = False
    for provider, model in cadeia:
        if not _provider_elegivel(provider):
            ultimo_erro = f"{provider} inelegível (habilitação/chave/soberania)"
            continue
        try:
            # #39: barreira LGPD + chamada + reidratação — fonte única (idem chat).
            texto, resposta_log, usage, messages_envio, pii_removida = await _chamar_com_barreira(
                provider, model, messages, modo_sanitizacao, entidades,
                cfg.temperature, cfg.max_tokens,
            )
        except _ProviderPulado as _pulado:
            bloqueado_por_pii = True
            ultimo_erro = f"PII residual ({', '.join(_pulado.residual)}) bloqueou provider externo"
            logger.warning(f"[Gateway] {provider} pulado em executar_tarefa_ia — "
                           f"PII residual ({', '.join(_pulado.residual)}) após sanitização (LGPD).")
            continue
        except Exception as e:
            ultimo_erro = str(e)[:120]
            logger.warning(f"[Gateway] {provider} falhou em executar_tarefa_ia; "
                           f"tentando próximo: {ultimo_erro}")
            continue
        provedor_usado = provider
        # resposta_log = versão PSEUDONIMIZADA (sem PII real); no modo reversível
        # o prompt logado também é o sanitizado.
        if pii_removida:
            prompt_log = (messages_envio[-1].get("content", "") if messages_envio else mensagem)[:8000]
            pii_removida_log = True
        break
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
    # Fonte única (ai_cost), ciente do provedor: Groq deixa de reportar 0.0.
    custo = float(estimar_custo_brl(provedor_usado, inp, out, modelo_real))
    if db is not None and user_id:
        # Canônico (ai_guard): tipo_uso mapeado para o enum real e erro PROPAGA —
        # IA sem trilha de auditoria deve falhar, não responder em silêncio.
        # AILog guarda a versão PSEUDONIMIZADA (sem PII real) no modo reversível.
        from app.services.ai_guard import registrar_ai_log
        from app.services.ai.core.audit_logger import _tipo_uso
        await registrar_ai_log(
            db, user_id=user_id, tipo_uso=_tipo_uso(tarefa), case_id=case_id,
            prompt_sanitizado=prompt_log, pii_removida=pii_removida_log,
            resposta=resposta_log, modelo=f"{provedor_usado}/{modelo_real}",
            tokens_input=inp, tokens_output=out, custo_estimado=custo,
        )
    # #40: cacheia só sucesso e SEM PII reidratada — no modo reversível o `texto`
    # foi reidratado com PII real e NÃO deve ir para o cache (Redis/memória).
    if not pii_removida_log:
        await ai_cache.gravar(_cache_key, {
            "texto": texto, "modelo": f"{provedor_usado}/{modelo_real}",
            "provedor": provedor_usado,
        })
    return {
        "conteudo": texto, "modelo": f"{provedor_usado}/{modelo_real}", "provider": provedor_usado,
        "nivel_inteligencia": nivel_inteligencia,
        "tarefa": getattr(tarefa, "value", str(tarefa)),
        "is_rascunho": True, "requer_revisao": True,
        "tokens_usados": inp + out, "custo_estimado_brl": custo,
    }


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO AGÊNTICO DE IA — turno de tool-use com a MESMA barreira LGPD (fonte
# única). O histórico agêntico (loop.py) vive em ESPAÇO REAL (PII real); AQUI,
# a CADA turno, pseudonimizamos a lista INTEIRA de mensagens (text/tool_use/
# tool_result) com o MESMO conjunto `entidades` (marcadores CONSISTENTES) e
# reidratamos a saída localmente — espelha o modelo por-chamada de
# _chamar_com_barreira. NÃO cria barreira nova: reusa _preparar_mensagens_externo
# e pseudonymizer.reidratar. O `mapa` (PII real) vive só nesta chamada.
# ══════════════════════════════════════════════════════════════════════════════
def _coletar_slots_recursivo(valor, slots: list[tuple]) -> None:
    """Adiciona (container, chave) para CADA folha STRING de `valor`, descendo
    RECURSIVAMENTE por dict/list aninhados (achado S2 — defense-in-depth: uma
    tool com parâmetro object/array não pode escapar da barreira LGPD por ter a
    PII num nível interno). `container[chave]` é sempre a string mutável."""
    if isinstance(valor, dict):
        for k, v in valor.items():
            if isinstance(v, str):
                slots.append((valor, k))
            elif isinstance(v, (dict, list)):
                _coletar_slots_recursivo(v, slots)
    elif isinstance(valor, list):
        for i, v in enumerate(valor):
            if isinstance(v, str):
                slots.append((valor, i))
            elif isinstance(v, (dict, list)):
                _coletar_slots_recursivo(v, slots)


def _reidratar_recursivo(valor, mapa: dict) -> None:
    """Reidrata IN-PLACE toda folha STRING de `valor` (dict/list aninhados),
    espelhando _coletar_slots_recursivo (achado S2)."""
    from app.services.ai.pseudonymizer import reidratar
    if isinstance(valor, dict):
        for k, v in valor.items():
            if isinstance(v, str):
                valor[k] = reidratar(v, mapa)
            elif isinstance(v, (dict, list)):
                _reidratar_recursivo(v, mapa)
    elif isinstance(valor, list):
        for i, v in enumerate(valor):
            if isinstance(v, str):
                valor[i] = reidratar(v, mapa)
            elif isinstance(v, (dict, list)):
                _reidratar_recursivo(v, mapa)


def _slots_de_texto(messages: list[dict]) -> list[tuple]:
    """Referências mutáveis (container, chave) a CADA campo de texto das mensagens
    agênticas, em ordem determinística: content str; blocos text; valores STRING
    de input de tool_use (INCLUSIVE aninhados em object/array); e content de
    tool_result (str ou blocos text). Trabalha sobre a lista passada (espera-se
    uma deep copy)."""
    slots: list[tuple] = []
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            slots.append((m, "content"))
        elif isinstance(content, list):
            for bloco in content:
                if not isinstance(bloco, dict):
                    continue
                tipo = bloco.get("type")
                if tipo == "text" and isinstance(bloco.get("text"), str):
                    slots.append((bloco, "text"))
                elif tipo == "tool_use":
                    # S2: desce recursivamente pelo input (dict/list aninhados),
                    # não só nas strings de 1º nível.
                    _coletar_slots_recursivo(bloco.get("input"), slots)
                elif tipo == "tool_result":
                    rc = bloco.get("content")
                    if isinstance(rc, str):
                        slots.append((bloco, "content"))
                    elif isinstance(rc, list):
                        for sub in rc:
                            if (isinstance(sub, dict) and sub.get("type") == "text"
                                    and isinstance(sub.get("text"), str)):
                                slots.append((sub, "text"))
    return slots


def _pseudonimizar_agentico(messages, modo, entidades=None):
    """Barreira LGPD para o histórico AGÊNTICO (content estruturado). EXTRAI todos
    os campos de texto num flat [{role:"user", content:<texto>}], chama a MESMA
    primitiva da barreira (_preparar_mensagens_externo → (flat_limpos, residual,
    mapa)) e REESCREVE os textos limpos numa cópia PROFUNDA das mensagens.

    Retorna (messages_envio | None, residual, mapa). Se `residual` não-vazio o
    provider externo NÃO deve ser chamado (messages_envio=None)."""
    import copy
    msgs = copy.deepcopy(messages)
    slots = _slots_de_texto(msgs)
    flat = [{"role": "user", "content": cont[chave]} for (cont, chave) in slots]
    flat_limpos, residual, mapa = _preparar_mensagens_externo(flat, modo, entidades)
    if residual:
        return None, residual, mapa
    for (cont, chave), limpo in zip(slots, flat_limpos):
        cont[chave] = limpo.get("content", "")
    return msgs, residual, mapa


async def chat_agentico(
    messages: list[dict],
    tools: list[dict],
    task_type: str = "estrategia",
    max_tokens: int = 4096,
    entidades: dict[str, list[str]] | None = None,
    modo_sanitizacao=None,
) -> dict:
    """UM turno do loop agêntico (tool-use) com a MESMA barreira LGPD do chat().

    - Aplica legal_base.aplicar_base (identidade/base do escritório) no início.
    - `modo_sanitizacao` (achado S1): quando fornecido, é o modo de sanitização a
      aplicar na BARREIRA — derivado da ÁREA/sigilo REAL do caso pelo chamador
      (loop.rodar_agente). `task_type` continua governando o roteamento de
      MODELO. Sem ele, cai em modo_para_task(task_type) (retrocompatível).
    - Resolve a cadeia via _resolver_cadeia mas, nesta fase, só provedores com
      tool-use (anthropic). LOCAL_COMPLETO sem provider local → bloqueio SEGURO
      (RuntimeError claro).
    - Pseudonimiza a LISTA INTEIRA (text/tool_use/tool_result) com as MESMAS
      primitivas da barreira (_pseudonimizar_agentico → _preparar_mensagens_externo);
      residual → _ProviderPulado (não chama o provider).
    - Chama anthropic_provider.chat_tools e REIDRATA localmente TANTO o `text`
      QUANTO cada valor string de tool_calls[i].input (RECURSIVO, S2; o `mapa` só
      em memória).

    Retorna {"text","tool_calls","stop_reason","usage","provider","model",
             "text_para_log"}. `text_para_log` é PSEUDONIMIZADO (vai ao AILog;
    nunca PII reidratada)."""
    from app.services.ai.sanitization_policy import ModoSanitizacao, modo_para_task

    task_type_original = task_type
    task_type = _normalizar_task_type(task_type)
    # S1: o modo vem do sigilo REAL do caso (área) quando o chamador o informa;
    # senão, do task_type. Nunca deriva o sigilo só do rótulo de roteamento.
    if modo_sanitizacao is None:
        modo_sanitizacao = modo_para_task(task_type_original)

    # Identidade/base do escritório (BASE_PROMPT/16 regras) no system do agente.
    messages = legal_base.aplicar_base(messages, task_type)

    # Cadeia: reusa a resolução/elegibilidade e FILTRA para providers com
    # tool-use (só anthropic nesta fase).
    provider_force = settings.AI_PROVIDER if settings.AI_PROVIDER != "auto" else None
    cadeia = _resolver_cadeia(task_type, provider_force, None)
    if modo_sanitizacao == ModoSanitizacao.LOCAL_COMPLETO:
        # Sigilo reforçado: nunca sai do VPS. Não há provider LOCAL com tool-use
        # nesta fase → bloqueio seguro (o conteúdo nunca é enviado).
        cadeia = _restringir_cadeia_local_completo(cadeia, modo_sanitizacao, task_type_original)
        if not cadeia:
            raise RuntimeError(_MSG_BLOQUEIO_LOCAL_COMPLETO)
    cadeia_tools = [(p, m) for (p, m) in cadeia if p == "anthropic"]
    # Se AI_PROVIDER forçou um provider sem tool-use, mas o Anthropic está
    # elegível, ainda o usamos (única opção agêntica) — desde que não seja
    # LOCAL_COMPLETO (já tratado acima).
    if (not cadeia_tools and modo_sanitizacao != ModoSanitizacao.LOCAL_COMPLETO
            and _provider_elegivel("anthropic")):
        cadeia_tools = [("anthropic", _resolver_modelo("anthropic", task_type, None))]
    if not cadeia_tools or not _provider_elegivel("anthropic"):
        raise RuntimeError(
            "Módulo agêntico requer um provedor com suporte a tool-use (Anthropic) "
            "elegível — verifique ANTHROPIC_ENABLED, ANTHROPIC_API_KEY e "
            "AI_EXTERNAL_PROVIDERS_ALLOWED."
        )
    provider, model = cadeia_tools[0]

    # ── Barreira LGPD (fonte única) — pseudonimiza tudo que vai ao externo ──
    mapa = None
    messages_envio = messages
    if provider in _PROVIDERS_EXTERNOS and settings.AI_REQUIRE_SANITIZATION_FOR_EXTERNAL:
        messages_envio, residual, mapa = _pseudonimizar_agentico(
            messages, modo_sanitizacao, entidades
        )
        if residual:
            # Espelha _chamar_com_barreira: PII residual → provider NÃO é chamado.
            raise _ProviderPulado(residual)

    from app.services.providers import anthropic_provider
    resp = await anthropic_provider.chat_tools(messages_envio, model, max_tokens, tools)

    # ── Reidratação LOCAL: text + cada valor string de tool_calls[i].input ──
    text = resp.get("text", "") or ""
    text_para_log = text  # versão PSEUDONIMIZADA (sem PII real) → AILog/observabilidade
    tool_calls = resp.get("tool_calls", []) or []
    if mapa:
        from app.services.ai.pseudonymizer import reidratar
        text = reidratar(text, mapa)
        # S2: reidrata RECURSIVAMENTE o input (dict/list aninhados), não só as
        # strings de 1º nível — espelha _coletar_slots_recursivo da barreira.
        for tc in tool_calls:
            _reidratar_recursivo(tc.get("input"), mapa)

    usage = resp.get("usage", {}) or {}
    return {
        "text": text,
        "text_para_log": text_para_log,
        "tool_calls": tool_calls,
        "stop_reason": resp.get("stop_reason"),
        "usage": usage,
        "provider": provider,
        "model": usage.get("model", model),
    }
