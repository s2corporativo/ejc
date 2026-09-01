"""Regressão da migration 156 — #968.

A migration é aditiva: cria somente colunas nullable para marcos processuais e
prova de revisão. Não há backfill porque publicação/termo inicial não podem ser
inferidos de registros legados.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND_DIR / "alembic" / "versions" / "156_prazos_auditaveis_regime.py"

DEADLINE_COLS = {
    "data_publicacao",
    "termo_inicial",
    "regime_calculo",
    "calculo_metadata",
    "calculado_por",
    "conferido_por",
    "conferido_em",
}
DJEN_COLS = {
    "data_publicacao",
    "termo_inicial",
    "regime_calculo",
    "calculo_metadata",
    "prazo_revisado_por",
    "prazo_revisado_em",
}


def _script() -> ScriptDirectory:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(cfg)


def test_156_encadeia_no_head_155():
    rev = _script().get_revision("156_prazos_auditaveis_regime")
    assert rev.down_revision == "155_indices_listagem_espinha"


def test_upgrade_156_e_estritamente_aditivo_e_sem_backfill():
    fonte = MIGRATION.read_text(encoding="utf-8")
    upgrade = fonte.split("def upgrade() -> None:", 1)[1].split(
        "def downgrade() -> None:", 1
    )[0]
    assert "op.add_column" in upgrade
    assert "op.drop_column" not in upgrade
    assert "op.drop_table" not in upgrade
    assert "op.execute" not in upgrade
    assert "UPDATE " not in upgrade.upper()
    assert "DELETE " not in upgrade.upper()

    for coluna in DEADLINE_COLS | DJEN_COLS:
        assert f'"{coluna}"' in upgrade
    assert 'nullable=True' in upgrade


def test_downgrade_156_remove_somente_colunas_da_156():
    fonte = MIGRATION.read_text(encoding="utf-8")
    downgrade = fonte.split("def downgrade() -> None:", 1)[1]
    assert "op.drop_table" not in downgrade
    assert "op.execute" not in downgrade
    for coluna in DEADLINE_COLS | DJEN_COLS:
        assert f'"{coluna}"' in downgrade


def test_orm_declara_todas_as_colunas_da_156():
    from app.models.deadline import Deadline
    from app.models.djen import DjenComunicacao

    assert DEADLINE_COLS <= set(Deadline.__table__.columns.keys())
    assert DJEN_COLS <= set(DjenComunicacao.__table__.columns.keys())


@pytest.mark.skipif(
    not (os.getenv("RUN_DB_TESTS") and os.getenv("SCHEMA_CHECK_DATABASE_URL")),
    reason="requer PostgreSQL descartável para prova 155→156→155",
)
def test_upgrade_e_downgrade_156_em_postgres_real():
    import subprocess

    import psycopg2
    from sqlalchemy import create_engine, inspect

    url = os.environ["SCHEMA_CHECK_DATABASE_URL"]
    parsed = urlsplit(url)
    nome_db = f"ejc_prazos_156_{os.getpid()}"
    sync_url = urlunsplit(
        ("postgresql+psycopg2", parsed.netloc, f"/{nome_db}", "", "")
    )
    async_url = urlunsplit(
        ("postgresql+asyncpg", parsed.netloc, f"/{nome_db}", "", "")
    )

    def admin():
        conn = psycopg2.connect(
            dbname="postgres",
            user=unquote(parsed.username or ""),
            password=unquote(parsed.password or ""),
            host=parsed.hostname,
            port=parsed.port,
        )
        conn.autocommit = True
        return conn

    def alembic(*args: str):
        env = {
            **os.environ,
            "DATABASE_URL": async_url,
            "DATABASE_URL_SYNC": sync_url,
            "SCHEMA_CHECK_DATABASE_URL": sync_url,
        }
        proc = subprocess.run(
            [__import__("sys").executable, "-m", "alembic", *args],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr or proc.stdout

    conn = admin()
    try:
        with conn.cursor() as cur:
            cur.execute(f'CREATE DATABASE "{nome_db}"')
    finally:
        conn.close()

    try:
        alembic("upgrade", "155_indices_listagem_espinha")
        engine = create_engine(sync_url)
        try:
            insp = inspect(engine)
            antes_deadline = {c["name"] for c in insp.get_columns("deadlines")}
            antes_djen = {c["name"] for c in insp.get_columns("djen_comunicacoes")}
            assert not (DEADLINE_COLS & antes_deadline)
            assert not (DJEN_COLS & antes_djen)
        finally:
            engine.dispose()

        alembic("upgrade", "156_prazos_auditaveis_regime")
        engine = create_engine(sync_url)
        try:
            insp = inspect(engine)
            assert DEADLINE_COLS <= {c["name"] for c in insp.get_columns("deadlines")}
            assert DJEN_COLS <= {c["name"] for c in insp.get_columns("djen_comunicacoes")}
        finally:
            engine.dispose()

        alembic("downgrade", "155_indices_listagem_espinha")
        engine = create_engine(sync_url)
        try:
            insp = inspect(engine)
            assert not (DEADLINE_COLS & {c["name"] for c in insp.get_columns("deadlines")})
            assert not (DJEN_COLS & {c["name"] for c in insp.get_columns("djen_comunicacoes")})
        finally:
            engine.dispose()
    finally:
        conn = admin()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (nome_db,),
                )
                cur.execute(f'DROP DATABASE IF EXISTS "{nome_db}"')
        finally:
            conn.close()
