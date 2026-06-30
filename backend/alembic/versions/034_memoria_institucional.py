"""memoria_institucional — memória institucional do escritório (FASE 8)

Registros estruturados do que foi feito e do resultado: peças vencedoras,
estratégias, pareceres, acordos. Browsável/filtrável por caso, tipo, área e
resultado. (Busca semântica fica no Knowledge Hub — Etapa 3.)

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'f4a5b6c7d8e9'
down_revision = 'e3f4a5b6c7d8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'memoria_institucional',
        sa.Column('id', sa.String, primary_key=True,
                  server_default=sa.text("gen_random_uuid()::text")),
        # caso é opcional: a memória pode ser geral do escritório (não atrelada a um caso)
        sa.Column('case_id', sa.String,
                  sa.ForeignKey('cases.id', ondelete='SET NULL'), nullable=True),
        sa.Column('advogado_id', sa.String,
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),

        sa.Column('tipo', sa.String(50), nullable=False),   # peticao|recurso|parecer|contrato|decisao|acordo|tese_vencedora|estrategia
        sa.Column('titulo', sa.String(255), nullable=False),
        sa.Column('conteudo', sa.Text, nullable=False),
        sa.Column('resultado', sa.String(50)),              # favoravel|desfavoravel|parcial|acordo|em_andamento
        sa.Column('area_direito', sa.String(100)),
        sa.Column('tags', JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column('metadados', JSONB, server_default=sa.text("'{}'::jsonb")),

        sa.Column('created_by', sa.String, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_memoria_case', 'memoria_institucional', ['case_id'])
    op.create_index('ix_memoria_tipo', 'memoria_institucional', ['tipo'])
    op.create_index('ix_memoria_area', 'memoria_institucional', ['area_direito'])


def downgrade():
    op.drop_index('ix_memoria_area', table_name='memoria_institucional')
    op.drop_index('ix_memoria_tipo', table_name='memoria_institucional')
    op.drop_index('ix_memoria_case', table_name='memoria_institucional')
    op.drop_table('memoria_institucional')
