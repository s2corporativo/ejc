"""124 — data_room_links.token_hash (DOC-098)

Autenticação de link público por HASH (sha256) em vez do token em claro.

O segredo do link **deixa de existir em claro no banco**: depois de popular
`token_hash`, esta migration apaga a coluna `token` (SET NULL). Sem isso, um
dump ou backup do banco continuaria entregando acesso público aos documentos —
que é exatamente o achado que motivou a correção (auditoria 2026-07-26).

A coluna `token` permanece na tabela, agora anulável, apenas para não quebrar
compatibilidade retroativa de leitura; nada mais a escreve (ver
`routers/data_room.py::gerar_link`, que persiste somente o hash).

Backfill: `token_hash` é populado a partir do token vigente ANTES do apagamento,
de modo que nenhum link já emitido seja invalidado.

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
    # Apaga o segredo em claro. A ordem importa: só depois de o hash estar
    # gravado para TODOS os links. `token` vira anulável porque nada mais a
    # escreve — o índice único da coluna aceita múltiplos NULL no Postgres.
    op.alter_column(
        "data_room_links",
        "token",
        existing_type=sa.String(64),
        nullable=True,
    )
    op.execute(
        """
        UPDATE data_room_links
           SET token = NULL
         WHERE token IS NOT NULL
           AND token_hash IS NOT NULL
        """
    )


def downgrade() -> None:
    # IRREVERSÍVEL quanto ao segredo: o token em claro foi apagado e o hash não
    # o reconstrói. Reverter o código do Data Room exige REVOGAR e REGERAR os
    # links existentes (a UI já suporta — o token só é exibido na criação).
    # A coluna volta a NOT NULL apenas se não houver linha com token nulo, o que
    # na prática significa uma base sem links emitidos.
    op.drop_index(
        "ix_data_room_links_token_hash",
        table_name="data_room_links",
    )
    op.drop_column("data_room_links", "token_hash")
