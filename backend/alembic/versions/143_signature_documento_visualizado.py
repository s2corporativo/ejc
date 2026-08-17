"""Coluna ``documento_visualizado_em`` em ``signature_requests`` (ASS-01).

Issue #1081 (auditoria ago/2026): o POST ``/signatures/{sig_id}/assinar``
aceitava a assinatura mesmo sem nenhuma visualização prévia do documento —
a checagem de "documento aberto" vivia só no frontend (PortalAssinaturas.tsx).
O consentimento informado com valor probatório (MP 2.200-2/2001, art. 10
§2º) exige que o pré-requisito seja cumprido e provado no SERVIDOR.

Migration puramente aditiva: coluna ``timestamp nullable``; não altera
linhas existentes nem interfere no gate de deploy (catraca 132+).

A capacidade da tabela interna ``alembic_version`` para este revision_id longo
é garantida de forma idempotente por ``alembic/env.py`` antes da execução da
cadeia, sem inserir uma revision intermediária fora da numeração canônica.
"""

from alembic import op
import sqlalchemy as sa

revision = "143_signature_documento_visualizado"
down_revision = "142_document_hash_rescan"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "signature_requests",
        sa.Column(
            "documento_visualizado_em",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    # Coluna sem dados semânticos vinculados (só registra a 1ª visualização
    # a partir da aplicação). Perder o histórico de visualizações é o único
    # efeito do rollback — nenhuma outra tabela referencia a coluna.
    op.drop_column("signature_requests", "documento_visualizado_em")
