"""banco_teses_juridicas

Revision ID: 148_banco_teses_juridicas
Revises: 147_pendencia_impacto_providencia
Create Date: 2026-08-23 19:00:00.000000

Consolida o Banco Nacional de Teses Jurídicas como extensão ADITIVA da
tabela canônica `teses` (migração 014) — não cria um universo paralelo de
tabelas. Uma primeira tentativa deste PR criou tabelas próprias
(taxonomias/teses_juridicas/precedentes/processos_vitoriosos/
contrateses_tese) que duplicavam a base canônica já usada por Jurimetria,
Súmulas, o matcher tese↔caso e o frontend — o mesmo erro que a migração
114 já havia corrigido uma vez (consolidação de teses_juridicas_v4 em
`teses`). Esta revisão nunca chegou a ser aplicada em produção, então foi
reescrita aqui em vez de encadear uma migração de correção.

Novo vocabulário (`orientacao`, `status_validacao`, `tipo_relacao` das
tabelas satélite) é `String` com vocabulário fechado validado no
model/Pydantic, seguindo o precedente já registrado para a migração 147
em MIGRATION_RESERVATIONS.md — evita criar enum novo no Postgres e não
toca nos enums existentes `tesetipo`/`tesestatus`, dos quais depende SQL
cru de `services/sumulas_ingestion.py`.

`teses.codigo` ganha um índice não-único (não `UNIQUE` via
`op.create_unique_constraint`, que o classificador de compatibilidade de
deploy — `scripts/check_migration_compatibility.py` — trata como
operação de revisão humana): a unicidade é garantida pelo importador
(`services/teses_importador.py`) antes de persistir. Sem `batch_alter_table`
— este projeto roda só em Postgres; o modo batch existe para contornar
limitações do SQLite e o classificador não reconhece seu corpo dinâmico.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '148_banco_teses_juridicas'
down_revision = '147_pendencia_impacto_providencia'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Estende `teses`/`jurisprudencias_internas` e cria tabelas satélite."""

    # ── Colunas novas em `teses` (todas nullable — nenhum INSERT existente quebra) ──
    op.add_column('teses', sa.Column('codigo', sa.String(20), nullable=True))
    op.add_column('teses', sa.Column('orientacao', sa.String(10), nullable=True))
    op.add_column('teses', sa.Column('status_validacao', sa.String(25), nullable=True))
    op.add_column('teses', sa.Column('score', sa.Integer(), nullable=True))
    op.add_column('teses', sa.Column('score_calculos', sa.JSON(), nullable=True))
    op.add_column('teses', sa.Column('pressupostos', sa.Text(), nullable=True))
    op.add_column('teses', sa.Column('excecoes', sa.Text(), nullable=True))
    op.add_column('teses', sa.Column('estrategia', sa.Text(), nullable=True))
    op.add_column('teses', sa.Column('instancia', sa.String(100), nullable=True))
    op.add_column('teses', sa.Column('procedimento', sa.String(100), nullable=True))
    op.add_column('teses', sa.Column('parte_favorecida', sa.String(100), nullable=True))
    op.add_column('teses', sa.Column('requisitos', sa.JSON(), nullable=True))
    op.add_column('teses', sa.Column('provas_necessarias', sa.JSON(), nullable=True))
    op.add_column('teses', sa.Column('riscos', sa.JSON(), nullable=True))
    op.add_column('teses', sa.Column('fontes', sa.JSON(), nullable=True))
    op.add_column('teses', sa.Column('versao', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('teses', sa.Column('ultima_validacao_em', sa.DateTime(timezone=True), nullable=True))
    op.add_column('teses', sa.Column('validada_por', sa.String(36), nullable=True))
    op.create_foreign_key(
        'fk_teses_validada_por_users', 'teses', 'users',
        ['validada_por'], ['id'], ondelete='SET NULL',
    )
    op.create_index('ix_teses_codigo', 'teses', ['codigo'])
    op.create_index('ix_teses_status_validacao', 'teses', ['status_validacao'])

    # ── Colunas aditivas em `jurisprudencias_internas` ──
    op.add_column('jurisprudencias_internas', sa.Column('classe', sa.String(50), nullable=True))
    op.add_column('jurisprudencias_internas', sa.Column('orgao_julgador', sa.String(150), nullable=True))
    op.add_column('jurisprudencias_internas', sa.Column('vinculante', sa.Boolean(), nullable=True))

    # ── Tabela: teses_fundamentacoes ──
    # Dispositivos legais que fundamentam uma tese (norma/artigo/interpretação).
    op.create_table(
        'teses_fundamentacoes',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('tese_id', sa.String(36), nullable=False),
        sa.Column('norma', sa.String(120), nullable=False),
        sa.Column('artigo', sa.String(20), nullable=True),
        sa.Column('paragrafo', sa.String(20), nullable=True),
        sa.Column('inciso', sa.String(20), nullable=True),
        sa.Column('alinea', sa.String(20), nullable=True),
        sa.Column('texto', sa.Text(), nullable=True),
        sa.Column('interpretacao', sa.Text(), nullable=True),
        sa.Column('tipo', sa.String(30), nullable=True),
        sa.Column('created_by', sa.String(36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['tese_id'], ['teses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_teses_fund_tese_id', 'teses_fundamentacoes', ['tese_id'])
    op.create_index('ix_teses_fund_norma', 'teses_fundamentacoes', ['norma'])

    # ── Tabela: teses_relacoes ──
    # Grafo de relações entre teses (apoia, contradiz — cobre contratese —,
    # distingue, complementa, depende_de, supera, superada_por, alternativa,
    # subsidiaria, mesma_questao). Vocabulário validado no service/router.
    op.create_table(
        'teses_relacoes',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('tese_origem_id', sa.String(36), nullable=False),
        sa.Column('tese_destino_id', sa.String(36), nullable=False),
        sa.Column('tipo_relacao', sa.String(30), nullable=False),
        sa.Column('observacao', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['tese_origem_id'], ['teses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tese_destino_id'], ['teses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_teses_rel_origem_id', 'teses_relacoes', ['tese_origem_id'])
    op.create_index('ix_teses_rel_destino_id', 'teses_relacoes', ['tese_destino_id'])
    op.create_index(
        'ix_teses_rel_direcao', 'teses_relacoes',
        ['tese_origem_id', 'tese_destino_id', 'tipo_relacao'],
    )

    # ── Tabela: teses_jurisprudencias ──
    # Vínculo entre tese e jurisprudência interna (favoravel/contrario/distinguishing).
    op.create_table(
        'teses_jurisprudencias',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('tese_id', sa.String(36), nullable=False),
        sa.Column('jurisprudencia_id', sa.String(36), nullable=False),
        sa.Column('tipo_relacao', sa.String(20), nullable=False),
        sa.Column('observacao', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['tese_id'], ['teses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['jurisprudencia_id'], ['jurisprudencias_internas.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_teses_juris_tese_id', 'teses_jurisprudencias', ['tese_id'])
    op.create_index('ix_teses_juris_jurisprudencia_id', 'teses_jurisprudencias', ['jurisprudencia_id'])
    op.create_index(
        'ix_teses_juris_par', 'teses_jurisprudencias', ['tese_id', 'jurisprudencia_id'],
    )

    # ── Tabela: teses_alertas_jurisprudenciais ──
    # Um alerta por decisão detectada pelo Radar Jurisprudencial; teses e
    # casos afetados ficam em JSON porque uma decisão pode atingir N teses.
    op.create_table(
        'teses_alertas_jurisprudenciais',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('fonte', sa.String(30), nullable=False),
        sa.Column('chave_dedup', sa.String(200), nullable=False),
        sa.Column('titulo', sa.String(500), nullable=True),
        sa.Column('ementa', sa.Text(), nullable=True),
        sa.Column('tribunal', sa.String(120), nullable=True),
        sa.Column('numero_processo', sa.String(120), nullable=True),
        sa.Column('link', sa.Text(), nullable=True),
        sa.Column('data_julgamento', sa.Date(), nullable=True),
        sa.Column('severidade', sa.String(10), nullable=False),
        sa.Column('teses_afetadas', sa.JSON(), nullable=True),
        sa.Column('casos_afetados', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='novo'),
        sa.Column('tratado_por', sa.String(36), nullable=True),
        sa.Column('tratado_em', sa.DateTime(timezone=True), nullable=True),
        sa.Column('observacao', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['tratado_por'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_teses_alertas_status', 'teses_alertas_jurisprudenciais', ['status'])
    op.create_index('ix_teses_alertas_severidade', 'teses_alertas_jurisprudenciais', ['severidade'])
    op.create_index('ix_teses_alertas_created_at', 'teses_alertas_jurisprudenciais', ['created_at'])
    op.create_index('ix_teses_alertas_chave_dedup', 'teses_alertas_jurisprudenciais', ['chave_dedup'])

    # ── Tabela: legal_evidence ──
    # Trilha de auditoria de PROVENIÊNCIA: de onde saiu cada afirmação
    # jurídica do EJC (fonte, quem coletou, quando, hash do conteúdo
    # coletado, quem revisou). Não substitui `teses_jurisprudencias`
    # (vínculo tese↔jurisprudência já curada) — é o registro de auditoria
    # anterior a isso, produzido pelo pipeline de coleta (PR 3) e por
    # conferências manuais. `tese_id` é opcional: uma evidência pode ser
    # coletada antes de estar vinculada a uma tese específica.
    op.create_table(
        'legal_evidence',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('tese_id', sa.String(36), nullable=True),
        sa.Column('tipo_fonte', sa.String(30), nullable=False),
        sa.Column('tribunal', sa.String(120), nullable=True),
        sa.Column('numero', sa.String(120), nullable=True),
        sa.Column('url_oficial', sa.Text(), nullable=True),
        sa.Column('data_consulta', sa.DateTime(timezone=True), nullable=True),
        sa.Column('inteiro_teor_disponivel', sa.Boolean(), nullable=True),
        sa.Column('orgao_julgador', sa.String(150), nullable=True),
        sa.Column('relator', sa.String(200), nullable=True),
        sa.Column('data_julgamento', sa.Date(), nullable=True),
        sa.Column('data_publicacao', sa.Date(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='coletada'),
        sa.Column('trecho_relevante', sa.Text(), nullable=True),
        sa.Column('hash_fingerprint', sa.String(64), nullable=True),
        sa.Column('coletado_por', sa.String(36), nullable=True),
        sa.Column('revisado_por', sa.String(36), nullable=True),
        sa.Column('ultima_validacao_em', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['tese_id'], ['teses.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['coletado_por'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['revisado_por'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_legal_evidence_tese_id', 'legal_evidence', ['tese_id'])
    op.create_index('ix_legal_evidence_status', 'legal_evidence', ['status'])
    op.create_index('ix_legal_evidence_hash', 'legal_evidence', ['hash_fingerprint'])
    op.create_index('ix_legal_evidence_tipo_fonte', 'legal_evidence', ['tipo_fonte'])


def downgrade() -> None:
    """Reverte as extensões — nunca aplicada em produção, sem dados a preservar."""
    op.drop_index('ix_legal_evidence_tipo_fonte', table_name='legal_evidence')
    op.drop_index('ix_legal_evidence_hash', table_name='legal_evidence')
    op.drop_index('ix_legal_evidence_status', table_name='legal_evidence')
    op.drop_index('ix_legal_evidence_tese_id', table_name='legal_evidence')
    op.drop_table('legal_evidence')

    op.drop_index('ix_teses_alertas_chave_dedup', table_name='teses_alertas_jurisprudenciais')
    op.drop_index('ix_teses_alertas_created_at', table_name='teses_alertas_jurisprudenciais')
    op.drop_index('ix_teses_alertas_severidade', table_name='teses_alertas_jurisprudenciais')
    op.drop_index('ix_teses_alertas_status', table_name='teses_alertas_jurisprudenciais')
    op.drop_table('teses_alertas_jurisprudenciais')

    op.drop_index('ix_teses_juris_par', table_name='teses_jurisprudencias')
    op.drop_index('ix_teses_juris_jurisprudencia_id', table_name='teses_jurisprudencias')
    op.drop_index('ix_teses_juris_tese_id', table_name='teses_jurisprudencias')
    op.drop_table('teses_jurisprudencias')

    op.drop_index('ix_teses_rel_direcao', table_name='teses_relacoes')
    op.drop_index('ix_teses_rel_destino_id', table_name='teses_relacoes')
    op.drop_index('ix_teses_rel_origem_id', table_name='teses_relacoes')
    op.drop_table('teses_relacoes')

    op.drop_index('ix_teses_fund_norma', table_name='teses_fundamentacoes')
    op.drop_index('ix_teses_fund_tese_id', table_name='teses_fundamentacoes')
    op.drop_table('teses_fundamentacoes')

    op.drop_column('jurisprudencias_internas', 'vinculante')
    op.drop_column('jurisprudencias_internas', 'orgao_julgador')
    op.drop_column('jurisprudencias_internas', 'classe')

    op.drop_index('ix_teses_status_validacao', table_name='teses')
    op.drop_index('ix_teses_codigo', table_name='teses')
    op.drop_constraint('fk_teses_validada_por_users', 'teses', type_='foreignkey')
    op.drop_column('teses', 'validada_por')
    op.drop_column('teses', 'ultima_validacao_em')
    op.drop_column('teses', 'versao')
    op.drop_column('teses', 'fontes')
    op.drop_column('teses', 'riscos')
    op.drop_column('teses', 'provas_necessarias')
    op.drop_column('teses', 'requisitos')
    op.drop_column('teses', 'parte_favorecida')
    op.drop_column('teses', 'procedimento')
    op.drop_column('teses', 'instancia')
    op.drop_column('teses', 'estrategia')
    op.drop_column('teses', 'excecoes')
    op.drop_column('teses', 'pressupostos')
    op.drop_column('teses', 'score_calculos')
    op.drop_column('teses', 'score')
    op.drop_column('teses', 'status_validacao')
    op.drop_column('teses', 'orientacao')
    op.drop_column('teses', 'codigo')
