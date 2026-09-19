from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from typing import Any
import os

from sqlalchemy import func, select, text

from app.core.config import Settings
from app.services.ai.provider_registry import PROVIDERS_SUPORTADOS, provider_elegivel_com
from app.services.notification_preferences import whatsapp_configurado


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
    # Estado operacional derivado de evidência persistida (último job/sync/
    # homologação). None = não coletado. Nunca contém erro bruto/segredo.
    operational_state: str | None = None
    last_checked_at: str | None = None
    # Conectores judiciais: o que cada integração REALMENTE oferece ao fluxo
    # do caso (consultar, sincronizar movimentações, partes, audiências,
    # baixar documentos, intimações, protocolar). None = não é conector
    # judicial. Nenhum conector protocola: peticionamento é manual e
    # registrado por PATCH /legal-docs/{id}/protocolo.
    capacidades: dict[str, bool] | None = None


# ── Capacidades declaradas dos conectores judiciais ───────────────────────────
_CAPS_CHAVES = (
    "consultar_processo", "sincronizar_movimentacoes", "partes", "audiencias",
    "baixar_documentos", "intimacoes", "protocolar",
)


def _caps(**ativas: bool) -> dict[str, bool]:
    desconhecidas = set(ativas) - set(_CAPS_CHAVES)
    if desconhecidas:
        raise ValueError(f"capacidade desconhecida: {sorted(desconhecidas)}")
    # `protocolar` nunca é declarado True por conector algum (sem API oficial
    # de peticionamento habilitada — MNI Fase A é somente leitura).
    return {chave: bool(ativas.get(chave, False)) for chave in _CAPS_CHAVES}


CAPACIDADES_CONECTORES: dict[str, dict[str, bool]] = {
    # DataJud/CNJ: API pública de metadados + movimentações (sem peças).
    "datajud": _caps(consultar_processo=True, sincronizar_movimentacoes=True,
                     partes=True),
    # MNI 2.2.2 (PJe e tribunais cadastrados) — Fase A somente leitura:
    # consultarProcesso (cabeçalho, movimentos, documentos) + avisos pendentes.
    "processo_eletronico": _caps(consultar_processo=True,
                                 sincronizar_movimentacoes=True, partes=True,
                                 baixar_documentos=True, intimacoes=True),
    # DJEN/Comunica CNJ: intimações publicadas por OAB monitorada.
    "djen": _caps(intimacoes=True),
    # Infosimples (agregador pago): consulta processual TJMG por número/parte.
    "infosimples": _caps(consultar_processo=True, partes=True),
    # Núcleo de ajuizamento: prepara/valida/revisa/assina e REGISTRA o
    # protocolo; `protocolar` eletrônico segue False até perfil de tribunal
    # homologado (matriz fina em GET /ajuizamento/capacidades).
    "ajuizamento": _caps(consultar_processo=True, sincronizar_movimentacoes=True,
                         partes=True),
}


def _aplicar_capacidades(items: list[IntegrationStatus]) -> list[IntegrationStatus]:
    return [
        replace(it, capacidades=CAPACIDADES_CONECTORES[it.key])
        if it.key in CAPACIDADES_CONECTORES else it
        for it in items
    ]


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



def _iso(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _aplicar_estados_operacionais(
    items: list[IntegrationStatus],
    operational_states: dict[str, dict[str, Any]],
) -> list[IntegrationStatus]:
    """Rebaixa falso verde usando somente evidência operacional sanitizada.

    O contrato público continua status disabled|attention|ready. Integração
    desabilitada nunca vira falha; evidência operacional apenas enriquece o
    item e rebaixa ready quando há erro/ausência comprovada.
    """
    saida: list[IntegrationStatus] = []
    for it in items:
        op = operational_states.get(it.key)
        if not op:
            saida.append(it)
            continue
        estado = str(op.get("state") or "")
        detail = str(op.get("detail") or it.detail)
        checked_at = op.get("checked_at")
        status = it.status
        if status == "ready" and estado in {"attention", "error", "not_ready"}:
            status = "attention"
        saida.append(replace(
            it,
            status=status,
            detail=detail if status == "attention" else it.detail,
            operational_state=estado or None,
            last_checked_at=checked_at,
        ))
    return saida


async def collect_operational_states(db) -> dict[str, dict[str, Any]]:
    """Coleta metadados operacionais sem segredos e sem I/O externo."""
    out: dict[str, dict[str, Any]] = {}

    try:
        from app.models.rag import FonteIngestao

        map_slug = {
            "djen": "djen",
            "tjmg": "tjmg",
            "lexml": "lexml",
            "anpd": "anpd",
            "normas_rfb": "normas_rfb",
        }
        rows = (
            await db.execute(
                select(FonteIngestao).where(FonteIngestao.slug.in_(list(map_slug)))
            )
        ).scalars().all()
        for fonte in rows:
            key = map_slug.get(fonte.slug)
            if not key:
                continue
            ultimo = (fonte.ultimo_status or "").lower()
            nunca_produziu = not bool(fonte.ja_produziu)
            zeros = int(fonte.execucoes_zeradas_consecutivas or 0)
            if ultimo in {"erro", "parcial"}:
                state = "error"
                detail = "Última execução operacional falhou; consulte o diagnóstico da fonte."
            elif nunca_produziu and zeros >= 3:
                state = "attention"
                detail = (
                    "A fonte executa, mas não produz resultados há execuções consecutivas; "
                    "não tratar como ausência de dados."
                )
            else:
                state = "ok"
                detail = "Última execução operacional sem erro registrado."
            out[key] = {
                "state": state,
                "detail": detail,
                "checked_at": _iso(fonte.ultima_execucao),
            }
    except Exception:
        pass

    try:
        from app.models.processo_eletronico import (
            CredencialProcessoEletronico,
            Tribunal,
        )

        tribunais = int((await db.execute(
            select(func.count()).select_from(Tribunal).where(Tribunal.ativo.is_(True))
        )).scalar() or 0)
        credenciais = int((await db.execute(
            select(func.count()).select_from(CredencialProcessoEletronico).where(
                CredencialProcessoEletronico.ativo.is_(True)
            )
        )).scalar() or 0)
        if tribunais and credenciais:
            out["processo_eletronico"] = {
                "state": "ok",
                "detail": f"MNI com {tribunais} tribunal(is) e credencial ativa cadastrada.",
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        else:
            out["processo_eletronico"] = {
                "state": "not_ready",
                "detail": (
                    "Infraestrutura MNI disponível, mas falta tribunal ativo ou "
                    "credencial de advogado homologada."
                ),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
    except Exception:
        pass

    try:
        from app.models.ajuizamento import JudicialIntegrationProfile

        homologados = int((await db.execute(
            select(func.count()).select_from(JudicialIntegrationProfile).where(
                JudicialIntegrationProfile.ativo.is_(True),
                JudicialIntegrationProfile.authorized.is_(True),
                JudicialIntegrationProfile.credentials_valid.is_(True),
                JudicialIntegrationProfile.filing_supported.is_(True),
                JudicialIntegrationProfile.homologated_at.is_not(None),
            )
        )).scalar() or 0)
        out["ajuizamento"] = {
            "state": "ok" if homologados else "not_ready",
            "detail": (
                f"{homologados} perfil(is) de tribunal homologado(s) para protocolo."
                if homologados
                else "Nenhum perfil de tribunal está homologado para protocolo eletrônico."
            ),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception:
        pass

    try:
        existe = (await db.execute(
            text("SELECT to_regclass('public.google_drive_sync_state')")
        )).scalar()
        if not existe:
            out["google_drive_knowledge"] = {
                "state": "not_ready",
                "detail": "Google Drive Knowledge configurado, mas nenhuma sincronização foi iniciada.",
                "checked_at": None,
            }
        else:
            row = (await db.execute(text(
                "SELECT last_sync_at, last_status FROM google_drive_sync_state "
                "ORDER BY last_sync_at DESC NULLS LAST LIMIT 1"
            ))).mappings().first()
            if not row:
                out["google_drive_knowledge"] = {
                    "state": "not_ready",
                    "detail": "Google Drive Knowledge ainda não possui sincronização registrada.",
                    "checked_at": None,
                }
            else:
                status = str(row.get("last_status") or "").lower()
                ok = status in {"ok", "sucesso", "success"}
                out["google_drive_knowledge"] = {
                    "state": "ok" if ok else "error",
                    "detail": (
                        "Última sincronização Google Drive Knowledge concluída."
                        if ok else "Última sincronização Google Drive Knowledge falhou."
                    ),
                    "checked_at": _iso(row.get("last_sync_at")),
                }
    except Exception:
        pass

    return out


def _env_true(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "sim", "on"}


def _drive_auth_configurado() -> bool:
    modo = (os.getenv("GOOGLE_DRIVE_AUTH_MODE", "auto") or "auto").strip().lower()
    oauth = bool(
        os.getenv("GOOGLE_DRIVE_OAUTH_USER_FILE", "").strip()
        or os.getenv("GOOGLE_DRIVE_OAUTH_USER_JSON", "").strip()
        or (
            os.getenv("GOOGLE_DRIVE_OAUTH_CLIENT_ID", "").strip()
            and os.getenv("GOOGLE_DRIVE_OAUTH_CLIENT_SECRET", "").strip()
            and os.getenv("GOOGLE_DRIVE_OAUTH_REFRESH_TOKEN", "").strip()
        )
    )
    service_account = bool(
        os.getenv("GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE", "").strip()
        or os.getenv("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON", "").strip()
    )
    if modo == "oauth":
        return oauth
    if modo == "service_account":
        return service_account
    return oauth or service_account


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


def _estado_overlay_seguro() -> dict[str, Any]:
    """Estado do overlay do cofre em formato serializável (sem valores).

    Import LOCAL de propósito: `integration_status` é usado por rotas de
    diagnóstico que não devem depender da cadeia de import do cofre, e a falha
    de leitura do estado jamais pode derrubar o painel."""
    try:
        from app.services.credential_vault_service import estado_overlay

        estado = estado_overlay()
        aplicado_em = estado.get("aplicado_em")
        return {
            "status": estado.get("status"),
            "aplicado": bool(estado.get("aplicado")),
            "aplicado_em": (
                aplicado_em.isoformat() if isinstance(aplicado_em, datetime)
                else aplicado_em
            ),
            "campos": estado.get("campos"),
            "erro_tipo": estado.get("erro_tipo"),
            "falhas": estado.get("falhas"),
        }
    except Exception:   # pragma: no cover — painel nunca cai por causa disso
        return {"status": "indisponivel", "aplicado": False}


def build_integration_status(
    settings: Settings,
    credential_states: dict[str, str] | None = None,
    operational_states: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Retorna apenas metadados seguros; nunca retorna segredo ou valor sensível.

    `credential_states` (opcional, PR-4): {provider_key: last_test_status} do
    cofre (credential_vault_service.estados_credenciais). Quando fornecido, cada
    item ganha `credential_state` e um item `ready` cujo teste falhou é rebaixado
    para `attention`. Omitido (default) → comportamento e contrato idênticos ao
    histórico (os consumidores atuais chamam sem esse argumento)."""
    items = [
        # Elegibilidade pela fonte única (provider_registry): antes esta cópia
        # local ignorava GROQ_ENABLED e AI_EXTERNAL_PROVIDERS_ALLOWED e dizia
        # "ready" com cadeia vazia no gateway (análise E2E 03/09/2026, A3).
        _status(
            key="ai_core",
            label="Núcleo de IA",
            group="Inteligência",
            enabled=settings.AI_ENABLED,
            configured=any(
                provider_elegivel_com(p, settings) for p in PROVIDERS_SUPORTADOS
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
            configured=provider_elegivel_com("anthropic", settings),
            ready_detail="Provider habilitado e credencial presente no ambiente.",
            mode=settings.ANTHROPIC_MODEL_COMPLEXO,
        ),
        _status(
            key="groq",
            label="Groq",
            group="Inteligência",
            enabled=settings.AI_ENABLED and settings.GROQ_ENABLED,
            configured=provider_elegivel_com("groq", settings),
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
            key="processo_eletronico",
            label="Processo Eletrônico (MNI 2.2.2 / PJe)",
            group="Jurídico",
            # A sincronização roda em task Celery; sem fila não há conector.
            enabled=settings.CELERY_ENABLED,
            configured=bool(settings.REDIS_URL),
            ready_detail=(
                "Sincronização MNI habilitada via fila; tribunais e credenciais "
                "são cadastrados em /processo-eletronico."
            ),
            missing_detail="CELERY habilitado sem REDIS_URL — a fila MNI não sobe.",
            mode="somente leitura (sem peticionamento)",
        ),
        _status(
            key="ajuizamento",
            label="Ajuizamento (PDPJ / PJe-MNI / eproc)",
            group="Jurídico",
            enabled=settings.JUDICIAL_FILING_ENABLED,
            # Sem credencial PDPJ o fluxo funciona até o registro manual do
            # protocolo; o painel fino por tribunal é /ajuizamento/capacidades.
            configured=True,
            ready_detail=(
                "Wizard de ajuizamento com validação, revisão humana e registro de "
                "protocolo; protocolo eletrônico exige perfil de tribunal homologado."
            ),
            mode=(
                "PDPJ " + ("credencial presente" if settings.PDPJ_CLIENT_ID and settings.PDPJ_CLIENT_SECRET
                           else "REQUIRES_AUTHORIZATION")
            ),
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
            key="lexml",
            label="Federação LexML (legislação + jurisprudência)",
            group="Jurídico",
            enabled=settings.LEXML_INGEST_ENABLED,
            configured=True,
            ready_detail=("Federa legislação estadual (ALMG)/municipal (Betim) e "
                          "jurisprudência de TJ/TRT/TRF/TST/STJ/STF por temas."),
            mode=f"até {settings.LEXML_INGEST_MAX_POR_TEMA} itens/tema",
        ),
        _status(
            key="anpd",
            label="ANPD — regulamentações e guias",
            group="Conhecimento",
            enabled=settings.CONHECIMENTO_INGEST_ENABLED,
            configured=True,
            ready_detail="Fonte oficial ANPD habilitada para ingestão de conhecimento.",
        ),
        _status(
            key="normas_rfb",
            label="Normas RFB",
            group="Conhecimento",
            enabled=settings.CONHECIMENTO_INGEST_ENABLED,
            configured=True,
            ready_detail="Fonte de normas tributárias RFB habilitada para ingestão de conhecimento.",
        ),
        _status(
            key="transparencia",
            label="Portal da Transparência / CGU",
            group="Jurídico",
            enabled=settings.TRANSPARENCIA_ENABLED,
            configured=bool(settings.TRANSPARENCIA_API_KEY),
            ready_detail="Consulta de sanções (CEIS/CNEP/CEPIM) habilitada com chave gratuita presente.",
        ),
        # PNCP removido — licitações desativadas no EJC
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
            key="google_drive_knowledge",
            label="Google Drive Knowledge",
            group="Conhecimento",
            enabled=_env_true("GOOGLE_DRIVE_ENABLED"),
            configured=bool(
                os.getenv("GOOGLE_DRIVE_KNOWLEDGE_FOLDER_ID", "").strip()
                and _drive_auth_configurado()
            ),
            ready_detail="Google Drive Knowledge habilitado com pasta e autenticação configuradas.",
            missing_detail=(
                "Google Drive Knowledge habilitado, mas pasta ou autenticação está incompleta."
            ),
            mode=(os.getenv("GOOGLE_DRIVE_AUTH_MODE", "auto").strip().lower() or "auto"),
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
            # O remetente voltou pela Evolution API (a mesma instância do
            # webhook de ENTRADA). Este painel dizia `configured=False` fixo
            # ("vendor Z-API removido") enquanto as preferências já davam o
            # canal por disponível com a mesma flag/URL/chave — inventário e
            # envio real discordavam. A regra agora é ÚNICA:
            # notification_preferences.whatsapp_configurado.
            configured=whatsapp_configurado(settings),
            ready_detail="Canal habilitado com configuração completa no ambiente.",
            missing_detail=(
                "Evolution API incompleta (EVOLUTION_API_URL, EVOLUTION_API_KEY "
                "e EVOLUTION_INSTANCE) — envio automático de WhatsApp indisponível."
            ),
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
    if operational_states:
        items = _aplicar_estados_operacionais(items, operational_states)
    items = _aplicar_capacidades(items)
    counts = {
        "total": len(items),
        "ready": sum(item.status == "ready" for item in items),
        "attention": sum(item.status == "attention" for item in items),
        "disabled": sum(item.status == "disabled" for item in items),
    }
    return {
        "mode": "configuration_and_operational",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "summary": counts,
        "items": [asdict(item) for item in items],
        # Estado do overlay do Cofre NESTE processo (só metadados, nunca valor).
        # `aplicado=False` = o painel acima está lendo o `.env`, que não conhece
        # revogação — credencial revogada no cofre ainda vale. Chave aditiva:
        # os consumidores existentes não mudam.
        "credential_overlay": _estado_overlay_seguro(),
        "notice": (
            "O painel combina configuração, último teste do Cofre e evidência "
            "operacional persistida. Não revela valores sensíveis; testes de rede "
            "continuam separados quando aplicável."
        ),
    }
