"""Contratos do hardening PostgreSQL/RAG — Issue #1717, fase 2."""
from __future__ import annotations

from pathlib import Path

from app.core.database import runtime_ddl_permitido

ROOT = Path(__file__).resolve().parents[2]


class _Dialect:
    def __init__(self, name: str):
        self.name = name


class _Bind:
    def __init__(self, name: str):
        self.dialect = _Dialect(name)


class _DB:
    def __init__(self, name: str):
        self._bind = _Bind(name)

    def get_bind(self):
        return self._bind


def test_runtime_ddl_so_e_permitido_em_sqlite():
    assert runtime_ddl_permitido(_DB("sqlite")) is True
    assert runtime_ddl_permitido(_DB("postgresql")) is False
    assert runtime_ddl_permitido(object()) is False


def test_migration_162_adota_todas_as_tabelas_e_indices_priorizados():
    src = (
        ROOT / "backend/alembic/versions/162_runtime_tables_alembic.py"
    ).read_text(encoding="utf-8")
    for tabela in (
        "google_drive_sync_state",
        "transparencia_cache",
        "indices_bcb_cache",
        "indices_bcb_cache_meta",
        "radar_legislativo_visto",
        "backup_drive_state",
        "infosimples_uso",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {tabela}" in src
    assert "ix_knowledge_docs_versao_anterior_id" in src
    assert "ix_diario_oficial_alertas_keyword_id" in src
    downgrade = src[src.index("def downgrade()") :]
    assert "DROP TABLE" not in downgrade


def test_services_delegam_schema_postgres_ao_alembic():
    paths = (
        "backend/app/services/google_drive_service.py",
        "backend/app/services/transparencia_service.py",
        "backend/app/services/indices_service.py",
        "backend/app/services/radar_legislativo.py",
        "backend/app/services/backup_service.py",
        "backend/app/services/infosimples_service.py",
    )
    for rel in paths:
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert "runtime_ddl_permitido" in src


def test_scheduler_limita_total_do_auto_reembed():
    config = (ROOT / "backend/app/core/config.py").read_text(encoding="utf-8")
    sched = (ROOT / "backend/app/services/scheduler.py").read_text(encoding="utf-8")
    reparador = (
        ROOT / "backend/scripts/reembedar_chunks_orfaos.py"
    ).read_text(encoding="utf-8")
    assert "RAG_AUTO_REEMBED_MAX_DOCS_PER_RUN: int = 20" in config
    assert "RAG_AUTO_REEMBED_MAX_DOCS_PER_RUN" in sched
    assert "max_docs: int | None = None" in reparador
    assert "processados >= limite_total" in reparador


def test_deploy_nao_varre_backlog_rag_inteiro():
    deploy = (ROOT / "scripts/deploy_vps_safe.sh").read_text(encoding="utf-8")
    repair = (
        ROOT / "backend/scripts/reparar_conhecimento_rag.py"
    ).read_text(encoding="utf-8")
    assert "reparar_conhecimento_rag --batch-size 20 --max-docs 20" in deploy
    assert "max_docs: int | None = None" in repair
    assert "max_docs=max_docs" in repair
