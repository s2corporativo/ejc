"""Recomendações 4 e 5: Timeline unificada e Motor de prazos auditável

Revision ID: 109
Revises: 108_proxima_acao_obrigatoria
Create Date: 2025-01-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '109'
down_revision = '108'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # RECOMENDAÇÃO 4: Linha do tempo verdadeiramente única
    # =========================================================================
    
    # 1. Criar ENUM case_movimento_tipo
    case_movimento_tipo = postgresql.ENUM(
        'peticao', 'decisao', 'audiencia', 'nota', 'intimacao', 'ia',
        'documento_recebido', 'ligacao', 'mensagem', 'pagamento',
        'mudanca_responsavel', 'aprovacao', 'rejeicao',
        name='case_movimento_tipo', create_type=True
    )
    case_movimento_tipo.create(op.get_bind(), checkfirst=True)
    
    # 2. Adicionar colunas na tabela case_movimentos
    op.add_column('case_movimentos', 
        sa.Column('tipo', sa.Enum(
            'peticao', 'decisao', 'audiencia', 'nota', 'intimacao', 'ia',
            'documento_recebido', 'ligacao', 'mensagem', 'pagamento',
            'mudanca_responsavel', 'aprovacao', 'rejeicao',
            name='case_movimento_tipo', create_type=False
        ), nullable=False, server_default='nota')
    )
    op.add_column('case_movimentos', 
        sa.Column('autor_nome', sa.String(length=255), nullable=True)
    )
    op.add_column('case_movimentos', 
        sa.Column('origem', sa.String(length=50), nullable=True)
    )
    op.add_column('case_movimentos', 
        sa.Column('caso_relacionado_id', sa.String(length=36), nullable=True)
    )
    op.add_column('case_movimentos', 
        sa.Column('informacao_anterior', sa.Text(), nullable=True)
    )
    op.add_column('case_movimentos', 
        sa.Column('informacao_posterior', sa.Text(), nullable=True)
    )
    op.add_column('case_movimentos', 
        sa.Column('deadline_id', sa.String(length=36), nullable=True)
    )
    op.add_column('case_movimentos', 
        sa.Column('document_id', sa.String(length=36), nullable=True)
    )
    op.add_column('case_movimentos', 
        sa.Column('task_id', sa.String(length=36), nullable=True)
    )
    op.add_column('case_movimentos', 
        sa.Column('atendimento_id', sa.String(length=36), nullable=True)
    )
    
    # 3. Criar índices para performance
    op.create_index('ix_case_movimentos_data_evento', 'case_movimentos', ['data_evento'])
    op.create_index('ix_case_movimentos_created_by', 'case_movimentos', ['created_by'])
    op.create_index('ix_case_movimentos_deadline_id', 'case_movimentos', ['deadline_id'])
    op.create_index('ix_case_movimentos_document_id', 'case_movimentos', ['document_id'])
    op.create_index('ix_case_movimentos_task_id', 'case_movimentos', ['task_id'])
    op.create_index('ix_case_movimentos_atendimento_id', 'case_movimentos', ['atendimento_id'])
    op.create_index('ix_case_movimentos_caso_relacionado_id', 'case_movimentos', ['caso_relacionado_id'])
    
    # 4. Migrar dados existentes (converter tipo String para ENUM)
    # Nota: Em produção, isso seria feito com UPDATE específico
    # Por enquanto, mantemos o default 'nota' para registros antigos
    
    # =========================================================================
    # RECOMENDAÇÃO 5: Motor de prazos com "prova do cálculo"
    # =========================================================================
    
    # 5. Adicionar colunas na tabela deadlines para auditoria completa do prazo
    op.add_column('deadlines', 
        sa.Column('evento_origem', sa.String(length=255), nullable=True)
    )
    op.add_column('deadlines', 
        sa.Column('documento_origem_id', sa.String(length=36), nullable=True)
    )
    op.add_column('deadlines', 
        sa.Column('data_ciencia', sa.Date(), nullable=True)
    )
    op.add_column('deadlines', 
        sa.Column('regra_legal_aplicada', sa.String(length=255), nullable=True)
    )
    op.add_column('deadlines', 
        sa.Column('forma_contagem', sa.String(length=50), nullable=True)
    )
    op.add_column('deadlines', 
        sa.Column('calendario_utilizado', sa.String(length=100), nullable=True)
    )
    op.add_column('deadlines', 
        sa.Column('feriados_suspensoes', sa.Text(), nullable=True)
    )
    op.add_column('deadlines', 
        sa.Column('termo_inicial', sa.Date(), nullable=True)
    )
    op.add_column('deadlines', 
        sa.Column('termo_final', sa.Date(), nullable=True)
    )
    op.add_column('deadlines', 
        sa.Column('calculado_por', sa.String(length=36), nullable=True)
    )
    op.add_column('deadlines', 
        sa.Column('conferido_por', sa.String(length=36), nullable=True)
    )
    op.add_column('deadlines', 
        sa.Column('alteracoes', sa.Text(), nullable=True)
    )
    op.add_column('deadlines', 
        sa.Column('cancelamento_justificativa', sa.Text(), nullable=True)
    )
    
    # 6. Criar índices para consultas de auditoria
    op.create_index('ix_deadlines_documento_origem_id', 'deadlines', ['documento_origem_id'])
    op.create_index('ix_deadlines_data_ciencia', 'deadlines', ['data_ciencia'])
    op.create_index('ix_deadlines_calculado_por', 'deadlines', ['calculado_por'])
    op.create_index('ix_deadlines_conferido_por', 'deadlines', ['conferido_por'])


def downgrade() -> None:
    # =========================================================================
    # Downgrade RECOMENDAÇÃO 5: Motor de prazos
    # =========================================================================
    
    # Remover índices
    op.drop_index('ix_deadlines_conferido_por', table_name='deadlines')
    op.drop_index('ix_deadlines_calculado_por', table_name='deadlines')
    op.drop_index('ix_deadlines_data_ciencia', table_name='deadlines')
    op.drop_index('ix_deadlines_documento_origem_id', table_name='deadlines')
    
    # Remover colunas
    op.drop_column('deadlines', 'cancelamento_justificativa')
    op.drop_column('deadlines', 'alteracoes')
    op.drop_column('deadlines', 'conferido_por')
    op.drop_column('deadlines', 'calculado_por')
    op.drop_column('deadlines', 'termo_final')
    op.drop_column('deadlines', 'termo_inicial')
    op.drop_column('deadlines', 'feriados_suspensoes')
    op.drop_column('deadlines', 'calendario_utilizado')
    op.drop_column('deadlines', 'forma_contagem')
    op.drop_column('deadlines', 'regra_legal_aplicada')
    op.drop_column('deadlines', 'data_ciencia')
    op.drop_column('deadlines', 'documento_origem_id')
    op.drop_column('deadlines', 'evento_origem')
    
    # =========================================================================
    # Downgrade RECOMENDAÇÃO 4: Timeline unificada
    # =========================================================================
    
    # Remover índices
    op.drop_index('ix_case_movimentos_caso_relacionado_id', table_name='case_movimentos')
    op.drop_index('ix_case_movimentos_atendimento_id', table_name='case_movimentos')
    op.drop_index('ix_case_movimentos_task_id', table_name='case_movimentos')
    op.drop_index('ix_case_movimentos_document_id', table_name='case_movimentos')
    op.drop_index('ix_case_movimentos_deadline_id', table_name='case_movimentos')
    op.drop_index('ix_case_movimentos_created_by', table_name='case_movimentos')
    op.drop_index('ix_case_movimentos_data_evento', table_name='case_movimentos')
    
    # Remover colunas
    op.drop_column('case_movimentos', 'atendimento_id')
    op.drop_column('case_movimentos', 'task_id')
    op.drop_column('case_movimentos', 'document_id')
    op.drop_column('case_movimentos', 'deadline_id')
    op.drop_column('case_movimentos', 'informacao_posterior')
    op.drop_column('case_movimentos', 'informacao_anterior')
    op.drop_column('case_movimentos', 'caso_relacionado_id')
    op.drop_column('case_movimentos', 'origem')
    op.drop_column('case_movimentos', 'autor_nome')
    op.drop_column('case_movimentos', 'tipo')
    
    # Remover ENUM
    case_movimento_tipo = postgresql.ENUM(
        'peticao', 'decisao', 'audiencia', 'nota', 'intimacao', 'ia',
        'documento_recebido', 'ligacao', 'mensagem', 'pagamento',
        'mudanca_responsavel', 'aprovacao', 'rejeicao',
        name='case_movimento_tipo', create_type=False
    )
    case_movimento_tipo.drop(op.get_bind(), checkfirst=True)
