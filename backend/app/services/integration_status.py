from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from typing import Any

from app.core.config import Settings


@dataclass(frozen=True)
class IntegrationStatus:
    key: str
    label: str
    group: str
    enabled: bool
    configured: bool
    status: str
    detail: str
    mode: str | None = None
    # PR-4 (Cofre): último resultado do teste de conexão da credencial vigente,
    # no vocabulário do cofre (configurada|ausente|invalida|expirada|
    # sem_permissao|indisponivel). None = sem teste registrado (default → o
    # contrato histórico status ∈ disabled|attention|ready não muda).
    credential_state: str | None = None


# ── Refinamento pelo teste do Cofre (PR-4) ────────────────────────────────────
# `key` do painel → provider_key do credential_registry. Só os itens mapeados
# ganham credential_state; os demais permanecem intactos (retrocompatível).
_ITEM_PROVIDER = {
    "anthropic": "anthropic",
    "groq": "groq",
    "maritaca": "maritaca",
    "datajud": "datajud",
    "transparencia": "transparencia",
    "infosimples": "infosimples",
    "email": "smtp",
    "whatsapp": "whatsapp_zapi",
    "push": "push_vapid",
    "langfuse": "langfuse",
}

# Estados do cofre que rebaixam um item "ready" para "attention" (dentro do
# contrato existente — nunca inventa estado novo no campo `status`).
_CRED_ATENCAO = frozenset({
    "ausente", "invalida", "expirada", "sem_permissao", "indisponivel",
})

_DETALHE_POR_ESTADO = {
    "invalida": "Último teste do cofre: credencial inválida.",
    "expirada": "Último teste do cofre: credencial expirada.",
    "sem_permissao": "Último teste do cofre: sem permissão (403).",
    "indisponivel": "Último teste do cofre: serviço indisponível no teste.",
    "ausente": "Último teste do cofre: credencial ausente.",
}


def _aplicar_estados_credencial(
    items: list[IntegrationStatus], credential_states: dict[str, str],
) -> list[IntegrationStatus]:
    """Anexa credential_state a cada item mapeado e, se o item estava `ready`
    mas o teste do cofre falhou, rebaixa `status` para `attention` (traduzindo o
    resultado do cofre para os consumidores atuais SEM sair do contrato)."""
    saida: list[IntegrationStatus] = []
    for it in items:
        provider = _ITEM_PROVIDER.get(it.key)
        estado = credential_states.get(provider) if provider else None
        if not estado:
            saida.append(it)
            continue
        novo_status = it.status
        novo_detail = it.detail
        if it.status == "ready" and estado in _CRED_ATENCAO:
            novo_status = "attention"
            novo_detail = _DETALHE_POR_ESTADO.get(estado, it.detail)
        saida.append(replace(
            it, status=novo_status, detail=novo_detail, credential_state=estado,
        ))
    return saida


def _status(
    *,
    key: str,
    label: str,
    group: str,
    enabled: bool,
    configured: bool,
    ready_detail: str,
    disabled_detail: str = "Integração desabilitada por configuração.",
    missing_detail: str = "Integração habilitada, mas a configuração obrigatória está incompleta.",
    mode: str | None = None,
) -> IntegrationStatus:
    if not enabled:
        state = "disabled"
        detail = disabled_detail
    elif not configured:
        state = "attention"
        detail = missing_detail
    else:
        state = "ready"
        detail = ready_detail
    return IntegrationStatus(
        key=key,
        label=label,
        group=group,
        enabled=enabled,
        configured=configured,
        status=state,
        detail=detail,
        mode=mode,
    )


def build_integration_status(
    settings: Settings, credential_states: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Retorna apenas metadados seguros; nunca retorna segredo ou valor sensível.

    `credential_states` (opcional, PR-4): {provider_key: last_test_status} do
    cofre (credential_vault_service.estados_credenciais). Quando fornecido, cada
    item ganha `credential_state` e um item `ready` cujo teste falhou é rebaixado
    para `attention`. Omitido (default) → comportamento e contrato idênticos ao
    histórico (os consumidores atuais chamam sem esse argumento)."""
    items = [
        _status(
            key="ai_core",
            label="Núcleo de IA",
            group="Inteligência",
            enabled=settings.AI_ENABLED,
            configured=bool(
                settings.OLLAMA_ENABLED
                or (settings.ANTHROPIC_ENABLED and settings.ANTHROPIC_API_KEY)
                or settings.GROQ_API_KEY
            ),
            ready_detail="Há pelo menos um provedor elegível na política central de IA.",
            mode=(
                "local + externo"
                if settings.AI_EXTERNAL_PROVIDERS_ALLOWED
                else "somente local"
            ),
        ),
        _status(
            key="anthropic",
            label="Anthropic Claude",
            group="Inteligência",
            enabled=settings.AI_ENABLED and settings.ANTHROPIC_ENABLED,
            configured=bool(settings.ANTHROPIC_API_KEY),
            ready_detail="Provider habilitado e credencial presente no ambiente.",
            mode=settings.ANTHROPIC_MODEL_COMPLEXO,
        ),
        _status(
            key="groq",
            label="Groq",
            group="Inteligência",
            enabled=settings.AI_ENABLED,
            configured=bool(settings.GROQ_API_KEY),
            ready_detail="Provider de fallback com credencial presente no ambiente.",
            mode=settings.GROQ_MODEL,
        ),
        _status(
            key="maritaca",
            label="Maritaca (Sabiá)",
            group="Inteligência",
            enabled=settings.AI_ENABLED and settings.MARITACA_ENABLED,
            configured=bool(settings.MARITACA_API_KEY),
            ready_detail="Provider brasileiro (OpenAI-compatible) habilitado e credencial presente.",
            mode=settings.MARITACA_MODEL,
        ),
        _status(
            key="ollama",
            label="Ollama local",
            group="Inteligência",
            enabled=settings.AI_ENABLED and settings.OLLAMA_ENABLED,
            configured=bool(settings.OLLAMA_BASE_URL),
            ready_detail="Provider local habilitado; este painel não testa conectividade de rede.",
            mode="local",
        ),
        _status(
            key="embeddings",
            label="Embeddings RAG",
            group="Inteligência",
            enabled=settings.EMBEDDINGS_ENABLED,
            configured=(
                settings.EMBEDDINGS_PROVIDER == "local"
                or bool(settings.EMBEDDINGS_API_URL)
            ),
            ready_detail="Geração de embeddings habilitada para busca semântica.",
            mode=settings.EMBEDDINGS_PROVIDER,
        ),
        _status(
            key="datajud",
            label="DataJud / CNJ",
            group="Jurídico",
            enabled=settings.DATAJUD_ENABLED,
            configured=bool(settings.DATAJUD_API_KEY),
            ready_detail="Consulta processual habilitada e chave presente no ambiente.",
            mode="APIKey pública rotativa (CNJ)",
        ),
        _status(
            key="djen",
            label="DJEN / Comunica CNJ",
            group="Jurídico",
            enabled=settings.DJEN_INGEST_ENABLED,
            configured=bool(settings.DJEN_OABS_MONITORADAS.strip()),
            ready_detail="Coleta habilitada com ao menos uma OAB monitorada.",
        ),
        _status(
            key="tjmg",
            label="Jurisprudência TJMG",
            group="Jurídico",
            enabled=settings.TJMG_INGEST_ENABLED,
            configured=True,
            ready_detail="Crawler habilitado; mudanças no portal podem exigir manutenção.",
            mode=f"janela {settings.TJMG_INGEST_JANELA_DIAS} dias",
        ),
        _status(
            key="transparencia",
            label="Portal da Transparência / CGU",
            group="Jurídico",
            enabled=settings.TRANSPARENCIA_ENABLED,
            configured=bool(settings.TRANSPARENCIA_API_KEY),
            ready_detail="Consulta de sanções (CEIS/CNEP/CEPIM) habilitada com chave gratuita presente.",
        ),
        _status(
            key="pncp",
            label="PNCP — Contratações Públicas",
            group="Jurídico",
            enabled=settings.PNCP_ENABLED,
            configured=True,
            ready_detail="Consulta pública habilitada; API sem chave/segredo.",
            mode="consulta anônima; manutenção não implementada",
        ),
        _status(
            key="indices_bcb",
            label="Índices BCB (SGS + Olinda)",
            group="Jurídico",
            enabled=settings.INDICES_BCB_ENABLED,
            configured=True,
            ready_detail="Índices oficiais para cálculos judiciais habilitados; API pública sem chave.",
        ),
        _status(
            key="feriados_brasilapi",
            label="Feriados nacionais (BrasilAPI)",
            group="Jurídico",
            enabled=settings.FERIADOS_BRASILAPI_ENABLED,
            configured=True,
            ready_detail="Sync de feriados nacionais habilitado; API pública sem chave.",
            mode="consulta anônima",
        ),
        _status(
            key="cadastros_publicos",
            label="CEP/CNPJ públicos",
            group="Jurídico",
            enabled=True,
            configured=True,
            ready_detail=(
                "Fallback autenticado no EJC: BrasilAPI/ViaCEP para CEP e "
                "OpenCNPJ/BrasilAPI/ReceitaWS pública para CNPJ."
            ),
            mode="consulta anônima com rate limit; sem Conecta gov.br",
        ),
        _status(
            key="infosimples",
            label="Infosimples (consultas pagas)",
            group="Jurídico",
            enabled=settings.INFOSIMPLES_ENABLED,
            configured=bool(settings.INFOSIMPLES_TOKEN),
            ready_detail="Agregador comercial habilitado com token presente e teto diário de custo.",
            mode=f"teto {settings.INFOSIMPLES_MAX_CONSULTAS_DIA} consultas/dia",
        ),
        _status(
            key="email",
            label="E-mail SMTP",
            group="Comunicação",
            enabled=settings.EMAIL_ENABLED,
            configured=bool(
                settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD
            ),
            ready_detail="Envio de e-mail habilitado com credenciais presentes no ambiente.",
        ),
        _status(
            key="whatsapp",
            label="WhatsApp",
            group="Comunicação",
            enabled=settings.WHATSAPP_ENABLED,
            configured=bool(
                settings.ZAPI_INSTANCE_ID
                and settings.ZAPI_TOKEN
                and settings.ZAPI_CLIENT_TOKEN
            ),
            ready_detail="Canal habilitado com configuração completa no ambiente.",
        ),
        _status(
            key="push",
            label="Web Push",
            group="Comunicação",
            enabled=settings.PUSH_ENABLED,
            configured=bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY),
            ready_detail="Notificações push habilitadas com par VAPID configurado.",
        ),
        _status(
            key="celery",
            label="Celery / Redis",
            group="Infraestrutura",
            enabled=settings.CELERY_ENABLED,
            configured=bool(settings.REDIS_URL),
            ready_detail="Fila assíncrona habilitada; este painel não testa conectividade.",
        ),
        _status(
            key="langfuse",
            label="Langfuse self-hosted",
            group="Infraestrutura",
            enabled=settings.LANGFUSE_ENABLED,
            configured=bool(
                settings.LANGFUSE_HOST
                and settings.LANGFUSE_PUBLIC_KEY
                and settings.LANGFUSE_SECRET_KEY
            ),
            ready_detail="Observabilidade de IA habilitada em modo self-hosted.",
            mode=(
                "metadados + conteúdo sanitizado"
                if settings.LANGFUSE_CAPTURE_CONTENT
                else "somente metadados"
            ),
        ),
        _status(
            key="sentry",
            label="Sentry",
            group="Infraestrutura",
            enabled=bool(settings.SENTRY_DSN),
            configured=bool(settings.SENTRY_DSN),
            ready_detail="Rastreamento de erros configurado no ambiente.",
        ),
        _status(
            key="backup_offsite",
            label="Backup offsite",
            group="Infraestrutura",
            enabled=bool(settings.BACKUP_REMOTE),
            configured=bool(settings.BACKUP_REMOTE),
            ready_detail="Destino remoto declarado; a execução deve ser confirmada pelos logs de backup.",
            mode=f"retenção local {settings.BACKUP_RETENTION_DAYS} dias",
        ),
    ]
    if credential_states:
        items = _aplicar_estados_credencial(items, credential_states)
    counts = {
        "total": len(items),
        "ready": sum(item.status == "ready" for item in items),
        "attention": sum(item.status == "attention" for item in items),
        "disabled": sum(item.status == "disabled" for item in items),
    }
    return {
        "mode": "configuration_only",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "summary": counts,
        "items": [asdict(item) for item in items],
        "notice": (
            "O painel verifica somente habilitação e presença de configuração. "
            "Não revela valores sensíveis e não substitui healthchecks de conectividade."
        ),
    }
