"""124 — data_room_links.token_hash (DOC-098)

Autenticação de link público por HASH (sha256) em vez do token em claro.
A coluna `token` (texto em claro) permanece para compatibilidade retroativa,
mas a verificação de acesso passa a comparar sha256(token_recebido) == token_hash.

Backfill: popula token_hash para todos os links existentes a partir do token
vigente, de modo que nenhum link já emitido seja invalidado.

Revision ID: 124_data_room_token_hash
Revises: 123_deadline_owner
Create Date: 2026-07-26
"""
from alembic import op
import sqlalchemy as sa

revision = "124_data_room_token_hash"
down_revision = "123_deadline_owner"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "data_room_links",
        sa.Column("token_hash", sa.String(64), nullable=True),
    )
    # Backfill: sha256(token) em hex, batendo com hashlib.sha256(token.encode()).
    # sha256()/convert_to() são built-in do Postgres (>=11), sem exigir pgcrypto.
    op.execute(
        """
        UPDATE data_room_links
           SET token_hash = encode(sha256(convert_to(token, 'UTF8')), 'hex')
         WHERE token_hash IS NULL
           AND token IS NOT NULL
        """
    )
    op.create_index(
        "ix_data_room_links_token_hash",
        "data_room_links",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_data_room_links_token_hash",
        table_name="data_room_links",
    )
    op.drop_column("data_room_links", "token_hash")
