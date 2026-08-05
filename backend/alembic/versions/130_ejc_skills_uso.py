"""Contador de uso das AI Skills (Bloco 4 — enxugar catálogo).

`docs/auditoria/plano-lancamento-v3.md` (Bloco 4) pede: "AS 163 SKILLS DE IA:
mantenha no catálogo apenas as que têm uso registrado nos logs. Arquive o
resto." Hoje isso é impossível de cumprir: `ejc_skills` não tem nenhum
contador de execução, e `AILog` (a tabela de log de uso de IA) não grava
QUAL skill foi executada — toda execução de skill vira `tipo_uso='outro'`,
indistinguível de qualquer outra chamada de IA. Não há como inferir uso
retroativo a partir do log existente.

Esta migration só adiciona a contagem (mesmo padrão de
`PromptJuridico.vezes_executado`/`ultima_execucao`, já usado na Biblioteca
de Prompts Jurídicos) — não arquiva nada. O arquivamento por falta de uso
só pode acontecer depois que dado real se acumular em produção; decidir
isso a partir de zero dado seria arquivar às cegas.
"""
from alembic import op
import sqlalchemy as sa


revision = '130_ejc_skills_uso'
down_revision = '127_publicacao_explicita'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'ejc_skills',
        sa.Column('vezes_executado', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'ejc_skills',
        sa.Column('ultima_execucao', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('ejc_skills', 'ultima_execucao')
    op.drop_column('ejc_skills', 'vezes_executado')
