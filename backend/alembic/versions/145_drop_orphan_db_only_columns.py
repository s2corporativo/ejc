"""Remove colunas que existem no BANCO mas NÃO no ORM nem no código (Módulo 02).

Drift confirmado por ``alembic check`` no HEAD da main (15/08/2026),
pré-existente — não introduzido pela campanha de homologação:

- ``users.password_changed_at`` — adicionada pela migration 133; o ORM
  ``app/models/user.py`` nunca a declarou e nenhum módulo do app a referencia
  (verificação por varredura ``grep`` em ``backend/app/``). A funcionalidade
  de invalidação de tokens por troca de senha não depende desta coluna.
- ``knowledge_chunks.embedding_legacy_768`` — resquício da migração de
  embedding 768->1024 (RUNBOOK_MIGRACAO_EMBEDDING_1024.md); o ORM
  ``app/models/rag.py`` não declara o atributo e nenhum módulo o usa.

Ambas são colunas sem leitura/escrita pelo app: mantê-las só perpetua o drift.
- upgrade: DROP COLUMN com guarda — aborta sem alterar nada se qualquer
  módulo de código referenciar a coluna (dupla verificação: ORM + runtime).
- downgrade: recria a coluna (nullable, sem dados) — perda apenas do valor
  histórico, que o app nunca leu.
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
import re

revision = "145_drop_orphan_db_only_columns"
down_revision = "144_alembic_version_varchar128"
branch_labels = None
depends_on = None


def _codigo_refere(coluna: str) -> bool:
    import pathlib
    appdir = pathlib.Path(__file__).resolve().parents[3] / "app"
    pattern = re.compile(r"\b" + re.escape(coluna) + r"\b")
    for py in appdir.rglob("*.py"):
        if py.name.startswith(("test_", "_")):
            continue
        if pattern.search(py.read_text(errors="replace")):
            return True
    return False


def upgrade() -> None:
    for tabela, coluna in [
        ("users", "password_changed_at"),
        ("knowledge_chunks", "embedding_legacy_768"),
    ]:
        if _codigo_refere(coluna):
            raise RuntimeError(
                f"Guarda ativa: a coluna '{tabela}.{coluna}' ainda é "
                f"referenciada pelo código — drop abortado sem alterações."
            )
        op.drop_column(tabela, coluna)


def downgrade() -> None:
    op.add_column(
        "knowledge_chunks",
        sa.Column("embedding_legacy_768", Vector(768), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
    )
