"""Vínculo estável entre peças avulsas e cliente (Issue #1199).

Adiciona ``legal_docs.client_id`` e o marcador imutável
``client_admission_kind``. Peças ligadas a casos continuam usando ``case_id``.
Migration aditiva, sem backfill e sem alteração dos registros existentes.

Reconstruída sobre a cadeia canônica atual; substitui a antiga revisão 147
que nunca integrou a main e ficou incompatível depois do avanço até 152.
"""

from alembic import op
import sqlalchemy as sa

revision = "153_legal_doc_client_id"
down_revision = "152_thesis_candidate_tese_banco"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "legal_docs",
        sa.Column("client_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "legal_docs",
        sa.Column("client_admission_kind", sa.String(length=40), nullable=True),
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
    op.create_index(
        "ix_legal_docs_client_admission",
        "legal_docs",
        ["client_id", "client_admission_kind"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    vinculadas = bind.execute(
        sa.text(
            "SELECT count(*) FROM legal_docs "
            "WHERE client_id IS NOT NULL OR client_admission_kind IS NOT NULL"
        )
    ).scalar_one()
    if vinculadas:
        raise RuntimeError(
            "Downgrade recusado: existem legal_docs vinculados ao cliente. "
            "Preserve o vínculo com backup e use forward-fix."
        )
    op.drop_index("ix_legal_docs_client_admission", table_name="legal_docs")
    op.drop_index("ix_legal_docs_client_id", table_name="legal_docs")
    op.drop_constraint(
        "fk_legal_docs_client_id_clients",
        "legal_docs",
        type_="foreignkey",
    )
    op.drop_column("legal_docs", "client_admission_kind")
    op.drop_column("legal_docs", "client_id")
