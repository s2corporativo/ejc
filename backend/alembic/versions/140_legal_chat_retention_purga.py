"""140 — Adiciona retention_until em legal_chat_sessions (paridade Raio-X).

Contexto (F4 do plano de fusão Casos/Raio-X/Sala Jurídica, Issue #798):
RaioXAnalise já tinha `retention_until` — um PISO mínimo de retenção ("não
excluir antes disso"), não um teto que dispara purga. LegalChatSession não
tinha nenhum campo equivalente. Sem ele, o job de purga de análises
preliminares abandonadas (services/scheduler.py::_purgar_analises_preliminares_abandonadas)
não tinha como aplicar o mesmo piso de segurança às sessões da Sala.

Backfill: sessões existentes recebem `created_at + 90 dias`, o mesmo default
aplicado a partir de agora na criação (routers/legal_chat.py::criar_sessao) —
consistente com o default de `RaioXAnalise.retention_days` (schemas/raio_x.py).
Idempotente: reexecutar com a coluna já populada é no-op (UPDATE só afeta
`retention_until IS NULL`).

downgrade: remove a coluna. Não há perda de dado relevante — `retention_until`
é um piso de purga, não informação de negócio; nenhuma FK ou índice depende
dela.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "140_legal_chat_retention_purga"
down_revision = "138_consolida_fontes_ingestao"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "legal_chat_sessions",
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE legal_chat_sessions "
        "SET retention_until = created_at + INTERVAL '90 days' "
        "WHERE retention_until IS NULL"
    )


def downgrade() -> None:
    op.drop_column("legal_chat_sessions", "retention_until")
