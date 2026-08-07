"""Integração de processo eletrônico via MNI 2.2.2 — Fase A (somente leitura).

Issue #762. Cria o catálogo de tribunais habilitados ao MNI (`tribunais`,
seed TJMG 1º/2º grau), o cofre de credenciais por advogado/tribunal
(`credenciais_processo_eletronico` — segredos SEMPRE cifrados, nunca em
claro), o estado de sincronização por caso em tabela própria
(`sincronizacao_processo_eletronico` — decisão: não reaproveitar os campos
DataJud/PJe já existentes em `cases`, que têm fonte e semântica de erro
diferentes) e a chave de dedup idDocumento(tribunal) → Document(EJC) para
idempotência da sincronização (`documentos_processo_eletronico_dedup`).

Não cobre `entregarManifestacaoProcessual` (peticionamento) — fora de
escopo desta fase, nenhuma tabela/coluna aqui dá suporte a isso.
"""
from alembic import op
import sqlalchemy as sa


revision = '132_processo_eletronico_mni'
down_revision = '131_audit_logs_worm'
branch_labels = None
depends_on = None

# O seed do catálogo é INSERT de dados, não DDL — precisa se declarar como tal
# para o `scripts/check_migration_compatibility.py`, que o deploy roda antes de
# aplicar qualquer migration pendente. A versão original usava
# `op.bulk_insert` sobre `sa.table()`: o classificador reprova tanto a
# atribuição intermediária ("estrutura dinâmica Assign") quanto o próprio
# `bulk_insert` (fora da allowlist), e o deploy automático parava no passo
# "Classificar migrations pendentes" com exit 1.
deployment_policy = 'additive_data_backfill'
data_backfill_targets = ('tribunais',)


def upgrade() -> None:
    op.create_table(
        'tribunais',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('nome', sa.String(120), nullable=False),
        sa.Column('codigo_tribunal', sa.String(4), nullable=False),
        sa.Column('grau', sa.String(10), nullable=False),
        sa.Column('endpoint_wsdl', sa.String(500), nullable=False),
        sa.Column('versao_mni', sa.String(10), nullable=False, server_default='2.2.2'),
        sa.Column('ativo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('codigo_tribunal', 'grau', name='uq_tribunais_codigo_grau'),
    )
    op.create_index('ix_tribunais_codigo_tribunal', 'tribunais', ['codigo_tribunal'])

    op.create_table(
        'credenciais_processo_eletronico',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('tribunal_id', sa.String(36), sa.ForeignKey('tribunais.id'), nullable=False),
        sa.Column('advogado_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('tipo', sa.String(20), nullable=False),
        sa.Column('id_consultante_cifrado', sa.Text(), nullable=True),
        sa.Column('senha_consultante_ref', sa.Text(), nullable=True),
        sa.Column('certificado_ref', sa.Text(), nullable=True),
        sa.Column('escopo', sa.String(30), nullable=False, server_default='leitura'),
        sa.Column('ativo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('ultima_verificacao', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('tribunal_id', 'advogado_id', 'tipo',
                             name='uq_credencial_tribunal_advogado_tipo'),
    )
    op.create_index('ix_credenciais_pe_tribunal_id', 'credenciais_processo_eletronico', ['tribunal_id'])
    op.create_index('ix_credenciais_pe_advogado_id', 'credenciais_processo_eletronico', ['advogado_id'])

    op.create_table(
        'sincronizacao_processo_eletronico',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('case_id', sa.String(36), sa.ForeignKey('cases.id'), nullable=False),
        sa.Column('tribunal_id', sa.String(36), sa.ForeignKey('tribunais.id'), nullable=True),
        sa.Column('numero_cnj', sa.String(25), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='sincronizando'),
        sa.Column('mensagem_erro', sa.Text(), nullable=True),
        sa.Column('docs_novos', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('case_id', name='uq_sincronizacao_processo_case'),
    )
    op.create_index('ix_sincronizacao_pe_case_id', 'sincronizacao_processo_eletronico', ['case_id'])
    op.create_index('ix_sincronizacao_pe_tribunal_id', 'sincronizacao_processo_eletronico', ['tribunal_id'])
    op.create_index('ix_sincronizacao_pe_numero_cnj', 'sincronizacao_processo_eletronico', ['numero_cnj'])

    op.create_table(
        'documentos_processo_eletronico_dedup',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('tribunal_id', sa.String(36), sa.ForeignKey('tribunais.id'), nullable=False),
        sa.Column('id_documento_tribunal', sa.String(60), nullable=False),
        sa.Column('document_id', sa.String(36), sa.ForeignKey('documents.id'), nullable=False),
        sa.Column('case_id', sa.String(36), sa.ForeignKey('cases.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('tribunal_id', 'id_documento_tribunal',
                             name='uq_dedup_tribunal_iddocumento'),
    )
    op.create_index('ix_dedup_pe_document_id', 'documentos_processo_eletronico_dedup', ['document_id'])
    op.create_index('ix_dedup_pe_case_id', 'documentos_processo_eletronico_dedup', ['case_id'])
    op.create_index('ix_dedup_pe_id_documento_tribunal', 'documentos_processo_eletronico_dedup',
                     ['id_documento_tribunal'])

    # Seed do catálogo TribunalRegistry (Fase A: só TJMG 1º/2º grau).
    # Endpoints WSDL conforme divulgação pública do TJMG para o serviço MNI
    # 2.2.2 — revisar/confirmar a URL exata antes de habilitar em produção
    # (ver services/tribunal_registry.py e ressalva no relatório da tarefa).
    #
    # `INSERT ... SELECT ... WHERE NOT EXISTS` em vez de `op.bulk_insert`: a
    # idempotência fica provável estaticamente (é o que o classificador de
    # deploy exige) e o seed passa a poder ser reaplicado sem violar
    # `uq_tribunais_codigo_grau`. Os UUIDs são fixos, e não `uuid4()`, para que
    # a mesma linha tenha a mesma identidade em todo ambiente — com id sorteado
    # em tempo de migration, produção, homologação e CI divergiriam.
    op.execute(
        """
        INSERT INTO tribunais
            (id, nome, codigo_tribunal, grau, endpoint_wsdl, versao_mni, ativo)
        SELECT novo.id, novo.nome, novo.codigo_tribunal, novo.grau,
               novo.endpoint_wsdl, novo.versao_mni, TRUE
        FROM (VALUES
            ('9f1c4b02-3d5a-4e77-9b64-0a1f2c3d4e51',
             'TJMG - 1º Grau', '13', '1',
             'https://pje1grau.tjmg.jus.br/pje/intercomunicacao?wsdl', '2.2.2'),
            ('9f1c4b02-3d5a-4e77-9b64-0a1f2c3d4e52',
             'TJMG - 2º Grau', '13', '2',
             'https://pje2grau.tjmg.jus.br/pje/intercomunicacao?wsdl', '2.2.2')
        ) AS novo (id, nome, codigo_tribunal, grau, endpoint_wsdl, versao_mni)
        WHERE NOT EXISTS (
            SELECT 1 FROM tribunais existente
            WHERE existente.codigo_tribunal = novo.codigo_tribunal
              AND existente.grau = novo.grau
        )
        """
    )


def downgrade() -> None:
    op.drop_table('documentos_processo_eletronico_dedup')
    op.drop_table('sincronizacao_processo_eletronico')
    op.drop_table('credenciais_processo_eletronico')
    op.drop_table('tribunais')
