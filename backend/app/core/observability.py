# ── app/core/observability.py ────────────────────────────────────────────────
# Observabilidade GATED do EJC:
#   · init_sentry()          — inicializa Sentry SÓ com SENTRY_DSN preenchido.
#   · app_version()/uptime   — dados do liveness (/api/health), sem I/O externo.
#   · check_migrations_head()— readiness: alembic na head? (informativo).
#
# Regra de ouro: observabilidade JAMAIS pode derrubar o boot. Tudo aqui é
# defensivo (try/except). Sem SENTRY_DSN, init_sentry() é um no-op silencioso —
# comportamento idêntico ao de um EJC sem esta camada.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import asyncio
import logging
import os
import time
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings

logger = logging.getLogger("ejc.observability")

# Marca monotônica do início do processo — base do uptime do liveness.
_PROCESS_START_MONOTONIC = time.monotonic()

# Estado REAL do coletor: True apenas depois de `sentry_sdk.init()` concluir.
# Presença de SENTRY_DSN não basta — DSN malformado ou falha de import caem no
# caminho engolido de init_sentry() e deixam este flag em False.
_sentry_inicializado = False

# Chaves cujo VALOR deve ser mascarado antes de qualquer evento sair para o
# Sentry (LGPD). Comparação case-insensitive.
_SCRUB_KEYS = frozenset({
    "cpf", "cnpj", "senha", "password", "passwd", "token", "access_token",
    "refresh_token", "secret", "authorization", "cookie", "set-cookie",
    "api_key", "apikey", "x-api-key", "pii_encryption_key", "pii_hash_key",
})
_SCRUB_MASK = "[Filtered]"


def uptime_seconds() -> float:
    """Segundos desde o start do processo (monotônico, sem I/O)."""
    return round(time.monotonic() - _PROCESS_START_MONOTONIC, 3)


def app_version() -> str:
    """Versão para o healthcheck: env APP_VERSION/GIT_SHA, senão 'dev'."""
    return os.getenv("APP_VERSION") or os.getenv("GIT_SHA") or "dev"


def _scrub(obj):
    """Mascara recursivamente valores de chaves sensíveis em dict/list/tuple."""
    if isinstance(obj, dict):
        return {
            k: (_SCRUB_MASK if isinstance(k, str) and k.lower() in _SCRUB_KEYS
                else _scrub(v))
            for k, v in obj.items()
        }
    if isinstance(obj, (list, tuple)):
        return type(obj)(_scrub(v) for v in obj)
    return obj


def _before_send(event, hint):
    """
    before_send do Sentry (LGPD): remove headers Authorization/Cookie e mascara
    campos sensíveis (cpf/cnpj/senha/token/...) em request data e extras.
    Nunca levanta — na dúvida, deixa o evento passar sem os dados sensíveis.
    """
    try:
        req = event.get("request")
        if isinstance(req, dict):
            headers = req.get("headers")
            if isinstance(headers, dict):
                for h in list(headers):
                    if isinstance(h, str) and h.lower() in _SCRUB_KEYS:
                        headers[h] = _SCRUB_MASK
            if "cookies" in req:
                req["cookies"] = _SCRUB_MASK
            if "data" in req:
                req["data"] = _scrub(req["data"])
        if isinstance(event.get("extra"), dict):
            event["extra"] = _scrub(event["extra"])
    except Exception:  # pragma: no cover - scrub nunca derruba o envio
        pass
    return event


def init_sentry() -> None:
    """
    Inicializa o Sentry apenas se SENTRY_DSN estiver preenchido.

    - DSN vazio  → no-op + log info "Sentry desativado (SENTRY_DSN vazio)".
    - DSN setado → sentry_sdk.init(..., send_default_pii=False, before_send=scrub).
    - Qualquer exceção é engolida: observabilidade jamais derruba o boot.

    Registra em `_sentry_inicializado` se o init de fato concluiu — é esse
    estado (e não a presença de DSN) que `coletor_erros_ativo()` reporta.
    """
    global _sentry_inicializado
    _sentry_inicializado = False
    try:
        settings = get_settings()
        dsn = (settings.SENTRY_DSN or "").strip()
        if not dsn:
            logger.info("Sentry desativado (SENTRY_DSN vazio)")
            return

        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        environment = settings.SENTRY_ENVIRONMENT or settings.APP_ENV
        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            send_default_pii=False,          # LGPD: obrigatório
            before_send=_before_send,        # scrub de dados sensíveis
            integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        )
        _sentry_inicializado = True
        logger.info(
            "Sentry inicializado (environment=%s, traces_sample_rate=%s)",
            environment, settings.SENTRY_TRACES_SAMPLE_RATE,
        )
    except Exception as e:  # pragma: no cover - defensivo, nunca derruba o boot
        logger.warning("Falha ao inicializar Sentry (ignorado): %s", e)


def coletor_erros_ativo() -> bool:
    """Há coletor de erros recebendo os 500 deste processo?

    Existe para que a resposta de erro não AFIRME algo que não acontece. Sem
    `SENTRY_DSN`, o erro é apenas logado no container: ninguém é notificado e
    não há registro histórico consultável. Prometer notificação nesse estado faz
    o usuário esperar por um retorno que nunca vem, e a auditoria de julho/2026
    registrou exatamente isso em `/analytics/roi-por-area`.

    Reporta o ESTADO REAL registrado por `init_sentry()` — não a presença de
    configuração. Com DSN preenchido mas malformado (ou falha de import), o
    init cai no caminho engolido, o flag fica False e a resposta de 500 não
    promete notificação que não acontecerá (review do PR #619). Ler um bool de
    módulo nunca levanta: na dúvida o default é False, a afirmação segura.
    """
    return _sentry_inicializado


def _load_migration_heads() -> frozenset[str]:
    """Resolve o DAG Alembic no filesystem.

    ScriptDirectory percorre o catálogo de migrations e pode levar vários
    segundos em cold start. O chamador deve executá-lo fora do event loop.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    backend_dir = Path(__file__).resolve().parents[2]  # .../backend
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    return frozenset(ScriptDirectory.from_config(cfg).get_heads())


@lru_cache(maxsize=1)
def _expected_migration_heads() -> frozenset[str]:
    """Head(s) esperados são imutáveis durante a vida do processo."""
    return _load_migration_heads()


async def warm_migration_heads() -> bool:
    """Pré-aquece o DAG Alembic sem bloquear o event loop do FastAPI."""
    try:
        heads = await asyncio.to_thread(_expected_migration_heads)
        if not heads:
            logger.error("Alembic sem head canônico durante o startup")
            return False
        logger.info("Alembic head(s) pré-aquecidos: %s", ",".join(sorted(heads)))
        return True
    except Exception as exc:
        logger.error(
            "Falha ao pré-aquecer Alembic heads (%s)",
            type(exc).__name__,
        )
        return False


async def check_migrations_head() -> bool | None:
    """Confirma que alembic_version corresponde ao head do código.

    O DAG do filesystem é calculado uma vez e pré-aquecido no lifespan.
    Mesmo em chamada isolada, o cálculo roda em thread para não bloquear o
    event loop; depois do warm-up, resta somente a consulta curta ao banco.
    """
    try:
        from sqlalchemy import text

        from app.core.database import engine

        heads = set(await asyncio.to_thread(_expected_migration_heads))
        if not heads:
            return None

        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT version_num FROM alembic_version"))
            current = {row[0] for row in res}
        return current == heads
    except Exception as exc:
        logger.warning(
            "Não foi possível comprovar o head Alembic (%s)",
            type(exc).__name__,
        )
        return None
