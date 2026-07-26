"""Configuração compartilhada da suíte pytest do backend.

Único ponto: quando os testes de banco estão ativos (``RUN_DB_TESTS=1``, usado
pelo job ``db-validation`` do CI), a trigger WORM de ``audit_logs`` (migration
127_audit_log_worm) impede qualquer ``DELETE``/``UPDATE`` na tabela — o que é o
comportamento CORRETO em produção, mas quebra o teardown dos testes ``*_dblevel``
que fazem ``DELETE FROM audit_logs`` para limpar a massa (e, por FK, o
``DELETE FROM users`` seguinte).

A fixture abaixo desabilita a trigger APENAS no banco de teste, no início da
sessão de testes, e a reabilita ao final. Não toca a migration nem a proteção em
produção: fora de ``RUN_DB_TESTS`` (sandbox local, boot de produção) é um no-op.
Requer apenas privilégio de owner sobre a tabela — o mesmo papel que aplicou as
migrations no CI.
"""
from __future__ import annotations

import os

import pytest

_TRIGGER = "trg_audit_logs_worm"


@pytest.fixture(scope="session", autouse=True)
def _liberar_audit_worm_para_testes_db():
    """Desliga a trigger WORM de audit_logs durante os testes de banco.

    No-op quando RUN_DB_TESTS não está definido (não há Postgres migrado).
    """
    if not os.getenv("RUN_DB_TESTS"):
        yield
        return

    engine = None
    try:
        from sqlalchemy import create_engine, text

        from app.core.config import get_settings

        url = get_settings().DATABASE_URL_SYNC
        engine = create_engine(url, future=True)
        with engine.connect() as conn:
            conn.execution_options(isolation_level="AUTOCOMMIT")
            # Guardado: só age se a tabela/trigger existirem (banco migrado).
            existe = conn.execute(
                text(
                    "SELECT 1 FROM pg_trigger t "
                    "JOIN pg_class c ON c.oid = t.tgrelid "
                    "WHERE c.relname = 'audit_logs' AND t.tgname = :tg"
                ),
                {"tg": _TRIGGER},
            ).scalar()
            if existe:
                conn.execute(
                    text(f"ALTER TABLE audit_logs DISABLE TRIGGER {_TRIGGER}")
                )
    except Exception:  # pragma: no cover — ambiente sem DB/deps: segue sem travar
        engine = None

    try:
        yield
    finally:
        if engine is not None:
            try:
                from sqlalchemy import text

                with engine.connect() as conn:
                    conn.execution_options(isolation_level="AUTOCOMMIT")
                    conn.execute(
                        text(f"ALTER TABLE audit_logs ENABLE TRIGGER {_TRIGGER}")
                    )
            except Exception:  # pragma: no cover
                pass
            engine.dispose()
