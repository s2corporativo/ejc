"""Coluna ``documento_visualizado_em`` em ``signature_requests`` (ASS-01).

Issue #1081 (auditoria ago/2026): o POST ``/signatures/{sig_id}/assinar``
aceitava a assinatura mesmo sem nenhuma visualização prévia do documento —
a checagem de "documento aberto" vivia só no frontend (PortalAssinaturas.tsx).
O consentimento informado com valor probatório (MP 2.200-2/2001, art. 10
§2º) exige que o pré-requisito seja cumprido e provado no SERVIDOR.

Migration puramente aditiva: coluna ``timestamp nullable``; não altera
linhas existentes nem interfere no gate de deploy (catraca 132+).

**Homologação M02/M11 (16/08/2026):** o widening de ``alembic_version.version_num``
para ``varchar(128)`` (migration ``144a`` criada na correção da cadeia)
foi consolidado aqui, com ``down_revision`` retornando a ``142`` — o guard
de numeração ``test_migration_numbering_guard.py`` rejeita prefixo não
numérico (``144a``). Semântica preservada: widening roda ANTES do corpo
de ``143``, exatamente onde a ``144a`` era aplicada (``down_revision = 142``).
O ``upgrade()`` abaixo é idempotente para widening já aplicado; o ``downgrade()``
desta migration passa o widening para ``144`` (que o executa, pois ``143``
tem ``revision_id`` de 35 caracteres — estreitar antes rejeitaria a própria
transação de downgrade).
"""
from alembic import op
import sqlalchemy as sa

revision = "143_signature_documento_visualizado"
down_revision = "142_document_hash_rescan"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Widening consolidado da antiga 144a (homologação M02/M11): rodar ANTES da
    # criação da coluna abaixo. PostgreSQL aceita widening já aplicado (no-op
    # seguro); sem widening aqui, a gravação da revision_id de 35 caracteres
    # desta migration estouraria o varchar(32) em instalações limpas.
    op.alter_column(
        "alembic_version",
        "version_num",
        type_=sa.String(128),
        existing_type=sa.String(32),
    )
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
    # O widening NÃO é revertido aqui: a migration ``144`` (que segue esta na
    # cadeia) executa o widening no upgrade, e estreitar ANTES da gravação da
    # revision_id de 35 caracteres de ``143`` (destino do downgrade) rejeitaria
    # a transação — bug reproduzido no Módulo 02, 15/08/2026. Downgrade de
    # coluna abaixo permanece intacto.
    op.drop_column("signature_requests", "documento_visualizado_em")
