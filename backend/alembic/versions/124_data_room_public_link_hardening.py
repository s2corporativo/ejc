"""Protege links públicos do Data Room e separa publicação externa.

- converte tokens claros existentes em SHA-256 sem invalidar as URLs emitidas;
- token claro deixa de existir no banco;
- arquivos legados ficam fechados até publicação externa explícita;
- registra autor e instante da publicação.

O downgrade é estruturalmente reversível, mas não recupera os tokens claros a
partir do hash. Após downgrade, links existentes devem ser revogados e gerados
novamente.

Revision ID: 124_dataroom_public_hardening
Revises: 123_legal_doc_ai_log_vinculo
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa

revision = "124_dataroom_public_hardening"
down_revision = "123_legal_doc_ai_log_vinculo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pgcrypto já é extensão obrigatória no stack, mas a migration falha de forma
    # autossuficiente em banco vazio usado no restore drill.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.alter_column(
        "data_room_links",
        "token",
        new_column_name="token_hash",
        existing_type=sa.String(length=64),
        existing_nullable=False,
    )
    op.execute(
        """
        UPDATE data_room_links
           SET token_hash = encode(digest(token_hash, 'sha256'), 'hex')
         WHERE token_hash !~ '^[0-9a-f]{64}$'
        """
    )

    op.add_column(
        "data_room_arquivos",
        sa.Column(
            "publicado_externamente",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "data_room_arquivos",
        sa.Column("publicado_por", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "data_room_arquivos",
        sa.Column("publicado_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_data_room_arquivos_publicado_por",
        "data_room_arquivos",
        "users",
        ["publicado_por"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_data_room_arquivos_publicacao",
        "data_room_arquivos",
        ["data_room_id", "publicado_externamente"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_data_room_arquivos_publicacao",
        table_name="data_room_arquivos",
    )
    op.drop_constraint(
        "fk_data_room_arquivos_publicado_por",
        "data_room_arquivos",
        type_="foreignkey",
    )
    op.drop_column("data_room_arquivos", "publicado_em")
    op.drop_column("data_room_arquivos", "publicado_por")
    op.drop_column("data_room_arquivos", "publicado_externamente")

    # A coluna volta a se chamar `token`, mas contém hashes irreversíveis. O
    # procedimento operacional seguro é revogar e gerar novos links.
    op.alter_column(
        "data_room_links",
        "token_hash",
        new_column_name="token",
        existing_type=sa.String(length=64),
        existing_nullable=False,
    )
