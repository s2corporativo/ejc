"""Vínculo estável entre peças avulsas e cliente (Issue #1199).

Adiciona ``legal_docs.client_id`` como FK opcional. Peças ligadas a casos continuam
usando ``case_id``; peças de admissão criadas antes de existir caso passam a usar
``client_id`` para impedir associação por nome/título e vazamento entre homônimos.

Migration aditiva, sem backfill e sem alteração dos registros existentes.
"""

from alembic import op
import sqlalchemy as sa

revision = "147_legal_doc_client_id"
down_revision = "146_case_sigilo_reforcado"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "legal_docs",
        sa.Column("client_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_legal_docs_client_id_clients",
        "legal_docs",
        "clients",
        ["client_id"],
        ["id"],
    )
    op.create_index(
        "ix_legal_docs_client_id",
        "legal_docs",
        ["client_id"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    vinculadas = bind.execute(
        sa.text("SELECT count(*) FROM legal_docs WHERE client_id IS NOT NULL")
    ).scalar_one()
    if vinculadas:
        raise RuntimeError(
            "Downgrade recusado: existem legal_docs vinculados a client_id. "
            "Preserve o vínculo com backup e use forward-fix."
        )
    op.drop_index("ix_legal_docs_client_id", table_name="legal_docs")
    op.drop_constraint(
        "fk_legal_docs_client_id_clients",
        "legal_docs",
        type_="foreignkey",
    )
    op.drop_column("legal_docs", "client_id")
