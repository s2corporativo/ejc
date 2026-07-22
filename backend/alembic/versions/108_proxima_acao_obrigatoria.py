"""próxima ação obrigatória e estados operacionais

Revision ID: 108
Revises: 107
Create Date: 2026-07-20

Implementa Recomendação 2: Próxima ação obrigatória em todo caso ativo
- Estados operacionais padronizados
- Campos de próxima ação (responsável, data, urgência, origem)
- Índices para performance das consultas no dashboard
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '108'
down_revision = '107'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Criar enum para estados operacionais
    op.execute("""
        CREATE TYPE caseoperationalstatus AS ENUM (
            'onboarding',
            'planejamento',
            'aguardando_cliente',
            'aguardando_terceiro',
            'em_andamento',
            'providencia_urgente',
            'negociacao',
            'encerramento',
            'encerrado'
        )
    """)
    
    # 2. Adicionar colunas de próxima ação na tabela cases
    op.add_column('cases', sa.Column('operacional_status', 
        postgresql.ENUM(
            'onboarding', 'planejamento', 'aguardando_cliente', 
            'aguardando_terceiro', 'em_andamento', 'providencia_urgente',
            'negociacao', 'encerramento', 'encerrado', 
            name='caseoperationalstatus', create_type=False
        ),
        nullable=True, server_default='onboarding'))
    
    op.add_column('cases', sa.Column('proxima_acao', sa.Text(), nullable=True,
        comment='Descrição da próxima ação necessária'))
    
    op.add_column('cases', sa.Column('responsavel_proxima_acao_id', 
        sa.String(36), nullable=True))
    
    op.add_column('cases', sa.Column('data_esperada_proxima_acao', 
        sa.DateTime(timezone=True), nullable=True))
    
    op.add_column('cases', sa.Column('urgencia_proxima_acao', 
        postgresql.ENUM('baixa', 'media', 'alta', 'critica', 
                       name='caseprioridade', create_type=False),
        nullable=True))
    
    op.add_column('cases', sa.Column('bloqueio_descricao', 
        sa.Text(), nullable=True,
        comment='Se há bloqueio, descrevê-lo'))
    
    op.add_column('cases', sa.Column('documento_origem_acao', 
        sa.String(36), nullable=True))
    
    op.add_column('cases', sa.Column('evento_origem_acao', 
        sa.String(36), nullable=True))
    
    # 3. Criar índices para performance
    op.create_index('ix_cases_operacional_status', 'cases', ['operacional_status'])
    op.create_index('ix_cases_responsavel_proxima_acao_id', 'cases', ['responsavel_proxima_acao_id'])
    
    # 4. Adicionar constraint de foreign key
    op.create_foreign_key(
        'fk_cases_responsavel_proxima_acao_users',
        'cases', 'users',
        ['responsavel_proxima_acao_id'], ['id']
    )
    
    op.create_foreign_key(
        'fk_cases_documento_origem_acao_documents',
        'cases', 'documents',
        ['documento_origem_acao'], ['id']
    )
    
    op.create_foreign_key(
        'fk_cases_evento_origem_acao_case_movimentos',
        'cases', 'case_movimentos',
        ['evento_origem_acao'], ['id']
    )
    
    print("✓ Migration 108: Campos de próxima ação adicionados com sucesso!")


def downgrade():
    # Remover constraints
    op.drop_constraint('fk_cases_evento_origem_acao_case_movimentos', 'cases', type_='foreignkey')
    op.drop_constraint('fk_cases_documento_origem_acao_documents', 'cases', type_='foreignkey')
    op.drop_constraint('fk_cases_responsavel_proxima_acao_users', 'cases', type_='foreignkey')
    
    # Remover índices
    op.drop_index('ix_cases_operacional_status', 'cases')
    op.drop_index('ix_cases_responsavel_proxima_acao_id', 'cases')
    
    # Remover colunas
    op.drop_column('cases', 'evento_origem_acao')
    op.drop_column('cases', 'documento_origem_acao')
    op.drop_column('cases', 'bloqueio_descricao')
    op.drop_column('cases', 'urgencia_proxima_acao')
    op.drop_column('cases', 'data_esperada_proxima_acao')
    op.drop_column('cases', 'responsavel_proxima_acao_id')
    op.drop_column('cases', 'proxima_acao')
    op.drop_column('cases', 'operacional_status')
    
    # Remover enum type
    op.execute("DROP TYPE IF EXISTS caseoperationalstatus")
    
    print("✓ Migration 108: Rollback realizado com sucesso!")
