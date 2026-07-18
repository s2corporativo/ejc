"""105 — bytes em BIGINT na Entrada Universal (M-D1).

``document_intake_batches.total_bytes`` e ``document_intake_items.size_bytes``
nasceram como ``Integer`` (int32) na 101_entrada_universal_documentos e
estouram com lotes/arquivos acima de 2 GiB (2_147_483_647 bytes). Aqui apenas
alargamos o tipo para ``BIGINT`` — conversão sem perda, sem mudança de
nullability nem de server_default.

Downgrade reverte para ``Integer`` (com perda de capacidade; falhará se já
houver valores acima de int32, o que é o comportamento correto).

Revision ID: 105_bytes_bigint
Revises: 104_merge_entrada_orquestrador
"""
from alembic import op
import sqlalchemy as sa

revision = "105_bytes_bigint"
down_revision = "104_merge_entrada_orquestrador"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "document_intake_batches",
        "total_bytes",
        type_=sa.BigInteger(),
        existing_type=sa.Integer(),
        existing_nullable=False,
        existing_server_default="0",
    )
    op.alter_column(
        "document_intake_items",
        "size_bytes",
        type_=sa.BigInteger(),
        existing_type=sa.Integer(),
        existing_nullable=False,
        existing_server_default="0",
    )


def downgrade() -> None:
    op.alter_column(
        "document_intake_items",
        "size_bytes",
        type_=sa.Integer(),
        existing_type=sa.BigInteger(),
        existing_nullable=False,
        existing_server_default="0",
    )
    op.alter_column(
        "document_intake_batches",
        "total_bytes",
        type_=sa.Integer(),
        existing_type=sa.BigInteger(),
        existing_nullable=False,
        existing_server_default="0",
    )
