"""Publicação explícita de documentos no portal (Fase 0, estancar riscos).

Auditoria identificou que documentos eram publicados ao cliente por OMISSÃO:
- Default confidencialidade="normal" no upload
- Portal filtra `confidencialidade=="normal"` e expõe automaticamente
- Resultado: documento estratégico, anotação interna, proposta da parte contrária
  ficam visíveis ao cliente SEM ação explícita

Correção: inverter o modelo de publicação.
- Default confidencialidade→"confidencial" (documentos nascem RESTRITIVOS)
- Portal continua filtrando `confidencialidade=="normal"`
- Usuário precisa EXPLICITAMENTE marcar documento como "normal" para publicar
- Existe hoje um documento bem-formado que merecia estar "normal"? A migração
  não o toca (não há forma de distinguir default de explicit); após a correção
  o usuário o reclassifica — custo de uma ação manual.

Reversibilidade: downgrade troca default de volta, mas não undo da reclassificação
que usuários podem ter feito entre upgrade e downgrade. Em produção, não fazer
downgrade sem conversa.

Janela: nenhum cliente real está usando o portal — reclassificação manual é zero-cost.
"""
from alembic import op
import sqlalchemy as sa


revision = '127_publicacao_explicita'
down_revision = '126_case_status_quatro_estados'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Reclassificar documentos existentes com "normal" para "confidencial"
    # para refletir a nova política de publicação explícita.
    op.execute(
        sa.text(
            "UPDATE documents SET confidencialidade = 'confidencial' "
            "WHERE confidencialidade = 'normal'"
        )
    )

    # Mudar DEFAULT de coluna existente. PostgreSQL infere o tipo do enum
    # pela definição da coluna; não precisa type cast explícito.
    op.execute(
        sa.text(
            "ALTER TABLE documents ALTER COLUMN confidencialidade SET DEFAULT 'confidencial'"
        )
    )


def downgrade() -> None:
    # Restaurar default anterior
    op.execute(
        sa.text(
            "ALTER TABLE documents ALTER COLUMN confidencialidade SET DEFAULT 'normal'"
        )
    )

    # Desfazer a reclassificação (volta "confidencial" → "normal")
    op.execute(
        sa.text(
            "UPDATE documents SET confidencialidade = 'normal' "
            "WHERE confidencialidade = 'confidencial'"
        )
    )
