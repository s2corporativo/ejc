# ── app/core/observability.py ────────────────────────────────────────────────
# Observabilidade do EJC:
#   · app_version()/uptime   — dados do liveness (/api/health), sem I/O externo.
#   · check_migrations_head()— readiness: alembic na head? (informativo).
#
# Regra de ouro: observabilidade JAMAIS pode derrubar o boot. Tudo aqui é
# defensivo (try/except).
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import os
import time

# Marca monotônica do início do processo — base do uptime do liveness.
_PROCESS_START_MONOTONIC = time.monotonic()


def uptime_seconds() -> float:
    """Segundos desde o start do processo (monotônico, sem I/O)."""
    return round(time.monotonic() - _PROCESS_START_MONOTONIC, 3)


def app_version() -> str:
    """Versão para o healthcheck: env APP_VERSION/GIT_SHA, senão 'dev'."""
    return os.getenv("APP_VERSION") or os.getenv("GIT_SHA") or "dev"


async def check_migrations_head() -> bool | None:
    """
    Readiness: True se o alembic_version do banco == head(s) das migrations.

    Retorna None (indeterminado) quando alembic não está configurado ou ocorre
    qualquer erro — nesse caso o resultado é apenas informativo e NÃO bloqueia
    o readiness. Nunca levanta.
    """
    try:
        from pathlib import Path

        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from sqlalchemy import text

        from app.core.database import engine

        backend_dir = Path(__file__).resolve().parents[2]  # .../backend
        cfg = Config(str(backend_dir / "alembic.ini"))
        cfg.set_main_option("script_location", str(backend_dir / "alembic"))
        heads = set(ScriptDirectory.from_config(cfg).get_heads())
        if not heads:
            return None

        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT version_num FROM alembic_version"))
            current = {row[0] for row in res}
        return current == heads
    except Exception:
        return None
