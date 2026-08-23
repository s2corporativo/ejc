"""banco_teses_juridicas

Revision ID: 148_banco_teses_juridicas
Revises: 147_pendencia_impacto_providencia
Create Date: 2026-08-23 19:00:00.000000

Banco Nacional de Teses Jurídicas — estrutura central para armazenar teses validadas,
fundamentações legais, precedentes e processos vitoriosos.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '148_banco_teses_juridicas'
down_revision = '147_pendencia_impacto_providencia'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Criar tabelas de Banco de Teses Jurídicas."""

    # ── Tabela: taxonomias ──
    # Classificação hierárquica de teses (Área → Subárea → Tema).
    op.create_table(
        'taxonomias',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('area', sa.String(100), nullable=False),
        sa.Column('subarea', sa.String(100), nullable=False),
        sa.Column('tema', sa.String(150), nullable=False),
        sa.Column('subtema', sa.String(150), nullable=True),
        sa.Column('nivel', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('descricao', sa.Text(), nullable=True),
        sa.Column('ativo', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('area', 'subarea', 'tema', 'subtema', name='uq_taxonomia_path'),
    )
    op.create_index('ix_taxonomias_area', 'taxonomias', ['area'])
    op.create_index('ix_taxonomias_area_subarea', 'taxonomias', ['area', 'subarea'])

    # ── Tabela: teses_juridicas ──
    # Registro principal de teses vencedoras.
    op.create_table(
        'teses_juridicas',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('titulo', sa.String(300), nullable=False),
        sa.Column('sumario', sa.String(500), nullable=True),
        sa.Column('taxonomia_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tipo', sa.Enum('ataque', 'defesa', 'ambos', name='tipotese'), nullable=False),
        sa.Column('parte_favorecida', sa.String(100), nullable=True),
        sa.Column('procedimento', sa.String(100), nullable=True),
        sa.Column('instancia', sa.String(100), nullable=True),
        sa.Column('tese_texto', sa.Text(), nullable=False),
        sa.Column('argumento', sa.Text(), nullable=True),
        sa.Column('pressupostos', sa.Text(), nullable=True),
        sa.Column('excecoes', sa.Text(), nullable=True),
        sa.Column('estrategia', sa.Text(), nullable=True),
        sa.Column('score', sa.Integer(), nullable=False, server_default='50'),
        sa.Column('score_calculos', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('decisoes_favoraveis', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('decisoes_desfavoraveis', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('decisoes_parciais', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('taxa_sucesso', sa.Float(), nullable=True),
        sa.Column('status', sa.Enum('rascunho', 'em_revisao', 'validada', 'nao_validada', 'descontinuada', name='statustese'), nullable=False, server_default='rascunho'),
        sa.Column('versao', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('data_revisao', sa.DateTime(timezone=True), nullable=True),
        sa.Column('criada_por', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('revisada_por', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('auditada_por', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['taxonomia_id'], ['taxonomias.id'], ),
        sa.ForeignKeyConstraint(['criada_por'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['revisada_por'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['auditada_por'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_teses_titulo', 'teses_juridicas', ['titulo'])
    op.create_index('ix_teses_taxonomia_id', 'teses_juridicas', ['taxonomia_id'])
    op.create_index('ix_teses_tipo', 'teses_juridicas', ['tipo'])
    op.create_index('ix_teses_status', 'teses_juridicas', ['status'])
    op.create_index('ix_teses_score', 'teses_juridicas', ['score'])

    # ── Tabela: fundamentacoes_legais ──
    # Dispositivos legais que fundamentam teses.
    op.create_table(
        'fundamentacoes_legais',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tese_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('norma', sa.String(50), nullable=False),
        sa.Column('artigo', sa.String(20), nullable=True),
        sa.Column('paragrafo', sa.String(20), nullable=True),
        sa.Column('inciso', sa.String(20), nullable=True),
        sa.Column('alinea', sa.String(20), nullable=True),
        sa.Column('texto_relevante', sa.Text(), nullable=True),
        sa.Column('interpretacao', sa.Text(), nullable=True),
        sa.Column('tipo', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['tese_id'], ['teses_juridicas.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_fund_leg_tese_id', 'fundamentacoes_legais', ['tese_id'])
    op.create_index('ix_fund_leg_norma', 'fundamentacoes_legais', ['norma'])

    # ── Tabela: precedentes ──
    # Jurisprudência associada a teses.
    op.create_table(
        'precedentes',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tese_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tribunal', sa.String(120), nullable=False),
        sa.Column('orgao_julgador', sa.String(150), nullable=True),
        sa.Column('classe', sa.String(50), nullable=True),
        sa.Column('numero', sa.String(100), nullable=True),
        sa.Column('relator', sa.String(200), nullable=True),
        sa.Column('data_julgamento', sa.Date(), nullable=True),
        sa.Column('data_publicacao', sa.Date(), nullable=True),
        sa.Column('ementa', sa.Text(), nullable=True),
        sa.Column('ementa_resumida', sa.String(300), nullable=True),
        sa.Column('tipo_relacao', sa.String(50), nullable=False, server_default='favoravel'),
        sa.Column('vinculante', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('fonte_url', sa.Text(), nullable=True),
        sa.Column('fonte', sa.String(50), nullable=True),
        sa.Column('vezes_citada', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['tese_id'], ['teses_juridicas.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_precedentes_tese_id', 'precedentes', ['tese_id'])
    op.create_index('ix_precedentes_tribunal', 'precedentes', ['tribunal'])
    op.create_index('ix_precedentes_tipo_relacao', 'precedentes', ['tipo_relacao'])
    op.create_index('ix_precedentes_vinculante', 'precedentes', ['vinculante'])

    # ── Tabela: processos_vitoriosos ──
    # Casos reais onde a tese foi vencedora.
    op.create_table(
        'processos_vitoriosos',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tese_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tribunal', sa.String(120), nullable=True),
        sa.Column('classe', sa.String(50), nullable=True),
        sa.Column('numero', sa.String(100), nullable=True),
        sa.Column('resultado', sa.String(100), nullable=True),
        sa.Column('contexto', sa.Text(), nullable=True),
        sa.Column('data_decisao', sa.Date(), nullable=True),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('fonte', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['tese_id'], ['teses_juridicas.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_proc_vitor_tese_id', 'processos_vitoriosos', ['tese_id'])

    # ── Tabela: contrateses_tese ──
    # Relações entre teses contraditórias ou complementares.
    op.create_table(
        'contrateses_tese',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tese_principal_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tese_contraria_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tipo_relacao', sa.String(50), nullable=True),
        sa.Column('descricao', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['tese_principal_id'], ['teses_juridicas.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tese_contraria_id'], ['teses_juridicas.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tese_principal_id', 'tese_contraria_id', name='uq_contrateses_direcao'),
    )
    op.create_index('ix_contrat_principal_id', 'contrateses_tese', ['tese_principal_id'])
    op.create_index('ix_contrat_contraria_id', 'contrateses_tese', ['tese_contraria_id'])


def downgrade() -> None:
    """Remover tabelas de Banco de Teses Jurídicas."""
    op.drop_index('ix_contrat_contraria_id', table_name='contrateses_tese')
    op.drop_index('ix_contrat_principal_id', table_name='contrateses_tese')
    op.drop_table('contrateses_tese')

    op.drop_index('ix_proc_vitor_tese_id', table_name='processos_vitoriosos')
    op.drop_table('processos_vitoriosos')

    op.drop_index('ix_precedentes_vinculante', table_name='precedentes')
    op.drop_index('ix_precedentes_tipo_relacao', table_name='precedentes')
    op.drop_index('ix_precedentes_tribunal', table_name='precedentes')
    op.drop_index('ix_precedentes_tese_id', table_name='precedentes')
    op.drop_table('precedentes')

    op.drop_index('ix_fund_leg_norma', table_name='fundamentacoes_legais')
    op.drop_index('ix_fund_leg_tese_id', table_name='fundamentacoes_legais')
    op.drop_table('fundamentacoes_legais')

    op.drop_index('ix_teses_score', table_name='teses_juridicas')
    op.drop_index('ix_teses_status', table_name='teses_juridicas')
    op.drop_index('ix_teses_tipo', table_name='teses_juridicas')
    op.drop_index('ix_teses_taxonomia_id', table_name='teses_juridicas')
    op.drop_index('ix_teses_titulo', table_name='teses_juridicas')
    op.drop_table('teses_juridicas')

    op.drop_index('ix_taxonomias_area_subarea', table_name='taxonomias')
    op.drop_index('ix_taxonomias_area', table_name='taxonomias')
    op.drop_table('taxonomias')

    # Remover enums
    sa.Enum('rascunho', 'em_revisao', 'validada', 'nao_validada', 'descontinuada', name='statustese').drop(op.get_bind())
    sa.Enum('ataque', 'defesa', 'ambos', name='tipotese').drop(op.get_bind())
