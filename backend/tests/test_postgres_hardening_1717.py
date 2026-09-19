"""Contratos de hardening PostgreSQL/LGPD da Issue #1717."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_alembic_prefere_credencial_dedicada_com_fallback():
    src = (ROOT / "backend/alembic/env.py").read_text(encoding="utf-8")
    assert 'os.environ.get("MIGRATION_DATABASE_URL")' in src
    assert 'os.environ.get("DATABASE_URL_SYNC")' in src
    assert src.index('os.environ.get("MIGRATION_DATABASE_URL")') < src.index(
        'os.environ.get("DATABASE_URL_SYNC")'
    )


def test_compose_separa_runtime_migration_e_amplia_shm():
    src = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert 'shm_size: "${EJC_DB_SHM_SIZE:-256m}"' in src
    assert 'APP_DATABASE_URL:-postgresql+asyncpg://' in src
    assert 'APP_DATABASE_URL_SYNC:-postgresql://' in src
    assert 'MIGRATION_DATABASE_URL: "' not in src


def test_env_runtime_nao_documenta_segredo_de_migrator():
    src = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "\nMIGRATION_DATABASE_URL=" not in src
    assert "MIGRATION_DATABASE_URL NÃO pertence a este env_file" in src


def test_backfill_pii_e_fail_closed_e_nao_loga_valores():
    src = (
        ROOT / "backend/scripts/backfill_case_partes_pii.py"
    ).read_text(encoding="utf-8")
    assert 'PII_BACKFILL_ALLOW") != "1"' in src
    assert "FOR UPDATE" in src
    assert "plaintext_restante" in src
    assert "gate LGPD falhou" in src
    assert "PII_BACKFILL" in src
    assert "valores sensíveis não registrados" in src
    # O AuditLog deve persistir somente contagens, nunca campos PII.
    audit_block = src[src.index("INSERT INTO audit_logs") :]
    assert '"cpf_cnpj":' not in audit_block
    assert '"email":' not in audit_block
    assert '"telefone":' not in audit_block
