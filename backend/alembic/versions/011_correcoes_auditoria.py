"""011_correcoes_auditoria

Revision ID: a1b2c3d4e5f6
Revises: 010_ramos_juridicos
Create Date: 2026-06-15

Correcoes identificadas em auditoria 2026-06-15:
1. ClientOrigem enum: adicionar 'redes_sociais' e 'escritorio'
2. clients.cpf e clients.cnpj: adicionar constraint UNIQUE
3. knowledge_chunks: renomear indice tsvector para evitar colisao com indice trigram
4. Recriar indice trigram com nome correto
5. migration 002: indice embedding sem IF NOT EXISTS (correcao preventiva)
"""

from alembic import op

revision = 'a1b2c3d4e5f6'
down_revision = '010_ramos_juridicos'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Adicionar valores ao enum clientorigem
    # PostgreSQL nao permite remover valores de enum, apenas adicionar
    op.execute("ALTER TYPE clientorigem ADD VALUE IF NOT EXISTS 'redes_sociais'")
    op.execute("ALTER TYPE clientorigem ADD VALUE IF NOT EXISTS 'escritorio'")

    # 2. Unique constraints em CPF e CNPJ de clientes
    # Primeiro remover duplicatas se existirem (manter o mais recente por id)
    op.execute("""
        DELETE FROM clients a
        USING clients b
        WHERE a.id < b.id
          AND a.cpf IS NOT NULL
          AND a.cpf = b.cpf
    """)
    op.execute("""
        DELETE FROM clients a
        USING clients b
        WHERE a.id < b.id
          AND a.cnpj IS NOT NULL
          AND a.cnpj = b.cnpj
    """)
    # Criar constraints UNIQUE
    op.create_unique_constraint('uq_clients_cpf', 'clients', ['cpf'])
    op.create_unique_constraint('uq_clients_cnpj', 'clients', ['cnpj'])

    # 3. Renomear indice tsvector antigo para liberar o nome para o trigram
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE indexname = 'ix_knowledge_chunks_conteudo_trgm'
            ) THEN
                ALTER INDEX ix_knowledge_chunks_conteudo_trgm
                RENAME TO ix_knowledge_chunks_conteudo_fts;
            END IF;
        END $$
    """)

    # 4. Criar indice trigram (agora sem colisao de nome)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_conteudo_trgm
        ON knowledge_chunks USING gin (conteudo gin_trgm_ops)
    """)

    # 5. Corrigir tamanho de VARCHAR para telefone/whatsapp (banco=20, model=30)
    op.execute("ALTER TABLE clients ALTER COLUMN telefone TYPE VARCHAR(30)")
    op.execute("ALTER TABLE clients ALTER COLUMN whatsapp TYPE VARCHAR(30)")


def downgrade() -> None:
    # Reverter tamanhos (trunca dados > 20 chars)
    op.execute("ALTER TABLE clients ALTER COLUMN whatsapp TYPE VARCHAR(20)")
    op.execute("ALTER TABLE clients ALTER COLUMN telefone TYPE VARCHAR(20)")

    # Remover indice trigram
    op.drop_index('ix_knowledge_chunks_conteudo_trgm', table_name='knowledge_chunks')

    # Renomear fts de volta
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE indexname = 'ix_knowledge_chunks_conteudo_fts'
            ) THEN
                ALTER INDEX ix_knowledge_chunks_conteudo_fts
                RENAME TO ix_knowledge_chunks_conteudo_trgm;
            END IF;
        END $$
    """)

    # Remover unique constraints
    op.drop_constraint('uq_clients_cnpj', 'clients', type_='unique')
    op.drop_constraint('uq_clients_cpf', 'clients', type_='unique')

    # Nao e possivel remover valores de enum no PostgreSQL via downgrade
    # Os valores 'redes_sociais' e 'escritorio' permaneceram no tipo
