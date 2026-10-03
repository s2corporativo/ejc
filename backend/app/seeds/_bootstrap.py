"""Bootstrap puro de scripts e primitivas comuns de seeds síncronos."""

from __future__ import annotations

import os
import sys


def bootstrap_backend(script_file: str) -> None:
    candidatos = [
        "/app",
        "/opt/ejc/backend",
        "/home/ubuntu/ejc/backend",
        os.path.dirname(os.path.dirname(os.path.abspath(script_file))),
    ]
    for candidato in candidatos:
        if os.path.isdir(os.path.join(candidato, "app")):
            if candidato not in sys.path:
                sys.path.insert(0, candidato)
            return


def create_sync_engine():
    from sqlalchemy import create_engine

    url = os.getenv("DATABASE_URL_SYNC") or os.getenv("DATABASE_URL", "")
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "+psycopg2")
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://")
    if not url:
        print("❌ DATABASE_URL(_SYNC) não configurada.")
        sys.exit(1)
    return create_engine(url)


def insert_skill(session, skill, now, *, uuid_factory):
    from sqlalchemy import text

    session.execute(text(_INSERT_SKILL_SQL), {"id": str(uuid_factory()), "now": now, **skill})


_INSERT_SKILL_SQL = """
                    INSERT INTO ejc_skills (
                        id, name, display_name, description, system_prompt,
                        engine, area, active, requires_case,
                        requires_human_review, oab_restricted,
                        version, created_at, updated_at
                    ) VALUES (
                        :id, :name, :display_name, :description, :system_prompt,
                        'groq', :area, true, false, true, true,
                        1, :now, :now
                    )
                """
