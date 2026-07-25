# ── app/services/providers/anthropic_provider.py ─────────────────────────────
# Provider Anthropic (Claude) — mesmo contrato de groq_provider/ollama_provider:
#   chat(messages, model, temperature, max_tokens) -> (texto, usage_dict)
# Converte mensagens formato OpenAI [{role,content}] → API Anthropic (system separado).
# Cliente lazy: só inicializa quando há ANTHROPIC_API_KEY. Sem chave → erro claro
# (o gateway faz fallback para Groq na cadeia).
#
# Endurecimento (Núcleo Único de IA):
#   • ANTHROPIC_ENABLED=false desliga o provider sem remover a chave;
#   • timeout do client = ANTHROPIC_TIMEOUT_SECONDS;
#   • max_tokens capado por ANTHROPIC_MAX_TOKENS (teto duro de custo);
#   • erros da API re-lançados como RuntimeError CURTO — sem stack trace,
#     sem corpo de resposta e SEM chave (nada sensível vaza para logs/HTTP).
#
# API 2026: nos modelos "modernos" (Opus 4.7+, Sonnet 5, Fable/Mythos 5) os
# parâmetros temperature/top_p/top_k foram REMOVIDOS (HTTP 400 se enviados).
# O controle de raciocínio passa a ser thinking adaptativo + output_config.effort.
from __future__ import annotations
import os
import asyncio

from app.core.config import get_settings

_client = None

# Modelos que usam a superfície nova da API (sem temperature; adaptive thinking).
_MODERN_PREFIXES = (
    "claude-opus-4-7",
    "claude-opus-4-8",
    "claude-sonnet-5",
    "claude-fable-5",
    "claude-mythos-5",
)


def _is_modern(model: str) -> bool:
    return model.startswith(_MODERN_PREFIXES)


def _api_key() -> str:
    """Chave Anthropic: prioriza a Settings tipada (.env carregado pelo pydantic);
    cai para os.getenv (ex.: docker env_file exporta no ambiente do processo)."""
    return get_settings().ANTHROPIC_API_KEY or os.getenv("ANTHROPIC_API_KEY", "")


def _default_model() -> str:
    return get_settings().ANTHROPIC_MODEL_RAPIDO or "claude-haiku-4-5-20251001"


def _get_client():
    global _client
    if not get_settings().ANTHROPIC_ENABLED:
        raise RuntimeError("Provider Anthropic desabilitado (ANTHROPIC_ENABLED=false)")
    if _client is None:
        import anthropic  # import tardio: só quando realmente usado
        api_key = _api_key()
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY não configurada")
        _client = anthropic.Anthropic(
            api_key=api_key,
            timeout=float(get_settings().ANTHROPIC_TIMEOUT_SECONDS),
        )
    return _client


def _system_param(system: str):
    """Bloco system para a API. Com AI_PROMPT_CACHING_ENABLED (default True),
    envia como bloco com cache_control ephemeral (prompt caching: leituras
    repetidas do mesmo prefixo custam ~10%; prefixos curtos apenas não cacheiam,
    sem erro). Desligado → string pura (formato aceito por qualquer modelo)."""
    if get_settings().AI_PROMPT_CACHING_ENABLED:
        return [{
            "type": "text",
            "text": system,
            "cache_control": {"type": "ephemeral"},
        }]
    return system


def _web_search_tool() -> dict | None:
    """Tool server-side de busca web (verificação ativa) — opt-in via
    AI_WEB_SEARCH_ENABLED (default OFF, padrão de integrações do repo).

    LGPD: este provider é invocado EXCLUSIVAMENTE pelo ai_gateway
    (_chamar_com_barreira → _chamar_provedor), DEPOIS da barreira de
    pseudonimização/sanitização (_preparar_mensagens_externo). Portanto qualquer
    query que o modelo derive das mensagens para a busca já está sem PII — o
    tool nunca vê conteúdo cru."""
    s = get_settings()
    if not s.AI_WEB_SEARCH_ENABLED:
        return None
    return {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": max(1, int(s.AI_WEB_SEARCH_MAX_USES)),
    }


def _contar_buscas_web(resp) -> int:
    """Quantas buscas web o modelo executou nesta resposta (0 sem o tool).
    Preferimos o contador oficial usage.server_tool_use.web_search_requests;
    fallback: conta blocos server_tool_use com name=web_search."""
    stu = getattr(getattr(resp, "usage", None), "server_tool_use", None)
    buscas = getattr(stu, "web_search_requests", None)
    if buscas is None:
        buscas = sum(
            1 for b in (getattr(resp, "content", None) or [])
            if getattr(b, "type", "") == "server_tool_use"
            and getattr(b, "name", "") == "web_search"
        )
    return int(buscas or 0)


def _split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    """Separa mensagens 'system' (Anthropic usa param próprio) das demais."""
    system_parts, conv = [], []
    for m in messages or []:
        role = m.get("role")
        content = m.get("content", "")
        if role == "system":
            if content:
                system_parts.append(content)
        else:
            conv.append({"role": "assistant" if role == "assistant" else "user",
                         "content": content})
    if not conv:  # Anthropic exige ao menos 1 mensagem de usuário
        conv = [{"role": "user", "content": "(sem conteúdo)"}]
    return "\n\n".join(system_parts), conv


async def health() -> bool:
    s = get_settings()
    return bool(s.ANTHROPIC_ENABLED and _api_key())


async def chat(messages: list[dict], model: str | None,
               temperature: float, max_tokens: int) -> tuple[str, dict]:
    """Mesmo contrato dos demais providers. Nos modelos modernos (Opus 4.7+,
    Sonnet 5, Fable 5) `temperature` é IGNORADA — a API a rejeita com 400; o
    raciocínio é controlado por thinking adaptativo + effort (ANTHROPIC_EFFORT)."""
    settings = get_settings()
    if not settings.ANTHROPIC_ENABLED:
        raise RuntimeError("Provider Anthropic desabilitado (ANTHROPIC_ENABLED=false)")


    system, conv = _split_system(messages)
    mdl = model or _default_model()
    # Teto duro de saída — controle de custo independente do chamador.
    mt = min(int(max_tokens or 1024), int(settings.ANTHROPIC_MAX_TOKENS))

    def _call():
        import anthropic  # import tardio (mesmo padrão do _get_client)
        client = _get_client()
        kwargs = dict(model=mdl, messages=conv)
        if system:
            # Prompt caching (AI_PROMPT_CACHING_ENABLED): bloco system com
            # cache_control — leituras repetidas do mesmo prefixo (system prompt
            # + base legal + RAG do caso) custam ~10% do preço.
            kwargs["system"] = _system_param(system)
        # Busca web (verificação ativa, opt-in): as `messages` recebidas aqui já
        # passaram pela barreira LGPD do gateway (pseudonimização/sanitização em
        # _chamar_com_barreira) — ver docstring de _web_search_tool.
        tool_busca = _web_search_tool()
        if tool_busca:
            kwargs["tools"] = [tool_busca]
        if _is_modern(mdl):
            effort = (get_settings().ANTHROPIC_EFFORT or "high").lower()
            # O thinking adaptativo consome o MESMO budget de max_tokens da
            # resposta → piso de 8192 para o texto não truncar no meio. O teto
            # ANTHROPIC_MAX_TOKENS continua valendo acima do piso: teto efetivo
            # nos modelos modernos = max(ANTHROPIC_MAX_TOKENS, 8192).
            teto = max(int(settings.ANTHROPIC_MAX_TOKENS), 8192)
            kwargs["max_tokens"] = min(max(mt, 8192), teto)
            # extra_body: compatível com qualquer versão do SDK python (evita
            # TypeError em SDKs que ainda não tipam thinking/output_config).
            kwargs["extra_body"] = {
                "thinking": {"type": "adaptive"},
                "output_config": {"effort": effort},
            }
        else:
            # Modelos legados (Haiku 4.5, Sonnet/Opus 4.6 e anteriores): a
            # temperature continua válida; effort não é suportado (erra no Haiku).
            kwargs["max_tokens"] = mt
            kwargs["temperature"] = temperature
        try:
            return client.messages.create(**kwargs)
        except anthropic.APIError as e:
            # Mensagem CURTA e segura: tipo + status. Sem corpo, sem stack,
            # sem chave. `from None` corta a cadeia de exceção original.
            status = getattr(e, "status_code", None)
            # Degradação graciosa da busca web: se a API rejeitou a requisição
            # COM o tool (400 — modelo/conta sem suporte ao web_search), repete
            # a MESMA chamada sem tools em vez de falhar a resposta.
            if tool_busca and status == 400:
                kwargs.pop("tools", None)
                try:
                    return client.messages.create(**kwargs)
                except anthropic.APIError as e2:
                    status2 = getattr(e2, "status_code", None)
                    raise RuntimeError(
                        f"Anthropic API falhou ({type(e2).__name__}"
                        + (f", HTTP {status2}" if status2 else "") + ")"
                    ) from None
            raise RuntimeError(
                f"Anthropic API falhou ({type(e).__name__}"
                + (f", HTTP {status}" if status else "") + ")"
            ) from None

    # SDK síncrono → roda em thread para não bloquear o event loop.
    resp = await asyncio.to_thread(_call)
    # A resposta pode conter blocos "thinking" antes do texto — nunca ler
    # content[0] às cegas: concatena apenas os blocos de tipo "text".
    texto = "".join(
        getattr(b, "text", "") for b in (resp.content or [])
        if getattr(b, "type", "") == "text"
    )
    u = getattr(resp, "usage", None)
    usage = {
        "model": mdl,
        "input_tokens": getattr(u, "input_tokens", None),
        "output_tokens": getattr(u, "output_tokens", None),
        # Transparência de custo do prompt caching (leitura ≈ 10% do preço).
        "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", None),
        "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", None),
        # Nº de buscas web executadas (0 quando o tool está OFF/não usado) —
        # o gateway registra este metadado em AILog/observabilidade.
        "web_search_requests": _contar_buscas_web(resp),
    }
    return texto, usage


async def chat_tools(messages: list[dict], model: str | None,
                     max_tokens: int, tools: list[dict]) -> dict:
    """Tool-use NATIVO para o loop agêntico (MÓDULO AGÊNTICO DE IA).

    ADITIVO — não altera `chat()`. Mesma superfície de endurecimento do `chat()`
    (client lazy, teto duro de max_tokens, extra_body/effort dos modelos modernos,
    erro CURTO e seguro), porém:
      • expõe as `tools` (schema Anthropic: [{"name","description","input_schema"}])
        ao modelo via client.messages.create(tools=...);
      • NÃO envia `temperature` (o loop não a usa e os modelos modernos a rejeitam);
      • devolve os blocos ESTRUTURADOS para o loop decidir o próximo passo.

    `messages` já vem no formato Anthropic — `content` pode ser str OU lista de
    blocos (text/tool_use/tool_result). A pseudonimização LGPD roda ANTES, no
    ai_gateway.chat_agentico (fonte única da barreira); aqui nada é sanitizado.

    Retorna:
      {"text": str,
       "tool_calls": [{"id","name","input":dict}],
       "stop_reason": str,
       "usage": {...}}
    """
    settings = get_settings()
    if not settings.ANTHROPIC_ENABLED:
        raise RuntimeError("Provider Anthropic desabilitado (ANTHROPIC_ENABLED=false)")

    system, conv = _split_system(messages)
    mdl = model or _default_model()
    # Teto duro de saída — mesmo controle de custo do chat().
    mt = min(int(max_tokens or 1024), int(settings.ANTHROPIC_MAX_TOKENS))

    def _call():
        import anthropic  # import tardio (mesmo padrão do _get_client)
        client = _get_client()
        # NOTA: o tool de busca web NÃO é anexado aqui — o loop agêntico
        # (services/ai/agent/loop.py) gerencia sua própria lista de tools e
        # executa cada tool_call localmente; um server-side tool intercalado
        # mudaria o contrato do loop. Busca web opt-in vale só para chat().
        kwargs = dict(model=mdl, messages=conv, tools=tools)
        if system:
            # Prompt caching condicionado a AI_PROMPT_CACHING_ENABLED (idem chat()).
            kwargs["system"] = _system_param(system)
        if _is_modern(mdl):
            effort = (get_settings().ANTHROPIC_EFFORT or "high").lower()
            # Achado M3: NÃO forçar o piso de 8192 no caminho de TOOL-USE. Ao
            # contrário do chat() (resposta longa de prosa, onde o thinking
            # adaptativo divide o budget com o texto e o piso evita truncar), os
            # turnos do agente são CURTOS (uma decisão + uma tool_call). Forçar
            # 8192 por turno estourava o teto acumulado do agente prematuramente.
            # Respeitamos o max_tokens do chamador (loop), sempre sob o teto duro.
            kwargs["max_tokens"] = mt
            kwargs["extra_body"] = {
                "thinking": {"type": "adaptive"},
                "output_config": {"effort": effort},
            }
        else:
            # Modelos legados: sem temperature (o contrato agêntico não a expõe).
            kwargs["max_tokens"] = mt
        try:
            return client.messages.create(**kwargs)
        except anthropic.APIError as e:
            status = getattr(e, "status_code", None)
            raise RuntimeError(
                f"Anthropic API falhou ({type(e).__name__}"
                + (f", HTTP {status}" if status else "") + ")"
            ) from None

    resp = await asyncio.to_thread(_call)
    # Parse dos blocos: text → `text`; tool_use → `tool_calls`. Nunca lê
    # content[0] às cegas (pode vir bloco "thinking" antes).
    texto_parts: list[str] = []
    tool_calls: list[dict] = []
    for b in (resp.content or []):
        btype = getattr(b, "type", "")
        if btype == "text":
            texto_parts.append(getattr(b, "text", "") or "")
        elif btype == "tool_use":
            tool_calls.append({
                "id": getattr(b, "id", "") or "",
                "name": getattr(b, "name", "") or "",
                "input": getattr(b, "input", None) or {},
            })
    u = getattr(resp, "usage", None)
    usage = {
        "model": mdl,
        "input_tokens": getattr(u, "input_tokens", None),
        "output_tokens": getattr(u, "output_tokens", None),
        "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", None),
        "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", None),
    }
    return {
        "text": "".join(texto_parts),
        "tool_calls": tool_calls,
        "stop_reason": getattr(resp, "stop_reason", None),
        "usage": usage,
    }
