"""deadline_owner — dono e criador do prazo (ownership de prazos avulsos)

Adiciona a `deadlines`:
  - owner_id   (FK users.id, nullable) — responsável jurídico/dono do prazo.
  - created_by (FK users.id, nullable) — quem criou o prazo (trilha de autoria).
Índice em owner_id (escopo de listagem/ownership de prazos avulsos case_id=NULL).

Backfill idempotente: owner_id/created_by = responsavel_id onde ainda nulos e
houver responsavel_id (prazos legados já tinham só o responsável direto).

SYS-034/035/036 — fecha a brecha de prazos AVULSOS (sem caso) visíveis/mutáveis
por qualquer usuário interno. Aditiva: colunas nullable, sem quebrar schema.

Revision ID: 123_deadline_owner
Revises: 122_documentos_publicacao_hash
Create Date: 2026-07-26
"""
from alembic import op
import sqlalchemy as sa

revision = "123_deadline_owner"
down_revision = "122_documentos_publicacao_hash"
branch_labels = None
depends_on = None


def _colunas_existentes(conn, tabela: str) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :t"
            ),
            {"t": tabela},
        )
    }


def upgrade() -> None:
    conn = op.get_bind()
    existentes = _colunas_existentes(conn, "deadlines")

    if "owner_id" not in existentes:
        op.add_column(
            "deadlines",
            sa.Column(
                "owner_id",
                sa.String(36),
                sa.ForeignKey("users.id"),
                nullable=True,
            ),
        )
        op.create_index("ix_deadlines_owner_id", "deadlines", ["owner_id"])

    if "created_by" not in existentes:
        op.add_column(
            "deadlines",
            sa.Column(
                "created_by",
                sa.String(36),
                sa.ForeignKey("users.id"),
                nullable=True,
            ),
        )

    # Backfill: prazos legados só tinham responsavel_id — herda dono e criador
    # dele onde ainda nulos. Idempotente (WHERE ... IS NULL).
    op.execute(
        "UPDATE deadlines SET owner_id = responsavel_id "
        "WHERE owner_id IS NULL AND responsavel_id IS NOT NULL"
    )
    op.execute(
        "UPDATE deadlines SET created_by = responsavel_id "
        "WHERE created_by IS NULL AND responsavel_id IS NOT NULL"
    )


def downgrade() -> None:
    # DDL idempotente (IF EXISTS): o DROP COLUMN já remove FK/índice; o DROP
    # INDEX explícito é defensivo (mesmo padrão da 033).
    op.execute("DROP INDEX IF EXISTS ix_deadlines_owner_id")
    op.execute("ALTER TABLE deadlines DROP COLUMN IF EXISTS created_by")
    op.execute("ALTER TABLE deadlines DROP COLUMN IF EXISTS owner_id")
