"""084 — Automações voltadas ao cliente (DataJud sync, solicitação de
documentos e régua de cobrança)

Schema das 4 automações do escritório (canais: e-mail + sino; WhatsApp fora
de escopo):

1. `cases.datajud_ultimo_andamento_em` (TIMESTAMPTZ NULL) — marcador explícito
   do último andamento oficial visto pelo sync diário do DataJud
   (services/datajud_sync_service.py). Complementa o dedup [dj:<hash>] de
   case_movimentos.

2. `solicitacoes_documentos` + `solicitacao_documento_itens` — pedido formal
   de documentos ao cliente (routers/solicitacoes_documentos.py, advogado) com
   upload pelo Portal do Cliente (routers/portal_documentos.py). Status da
   solicitação: pendente | parcial | atendida; do item: pendente | enviado.

3. `fee_cobranca_envios` — registro idempotente dos degraus da régua de
   cobrança ao cliente (d-3 | d+1 | d+7 | d+15 | escalado_advogado), no máximo
   um envio por (fee, degrau) — UNIQUE(fee_id, degrau)
   (services/cobranca_cliente_service.py).

ADITIVO PURO e IDEMPOTENTE: ADD COLUMN/CREATE TABLE/INDEX IF NOT EXISTS —
mesmo padrão das migrations 071-083. `status`/`degrau` como VARCHAR com
validação de domínio na aplicação (trade-off padrão do projeto: evita ENUM
nativo em migration idempotente, ver 073).

Revision ID: 084_automacoes_cliente
Revises: 083_case_area_ramos
Create Date: 2026-07-11
"""
from alembic import op

revision = "084_automacoes_cliente"
down_revision = "083_case_area_ramos"
branch_labels = None
depends_on = None


def upgrade():
    # ── 1. Marcador do último andamento DataJud visto (sync → notificação) ──
    op.execute(
        "ALTER TABLE cases ADD COLUMN IF NOT EXISTS "
        "datajud_ultimo_andamento_em TIMESTAMPTZ NULL"
    )

    # ── 2. Solicitação de documentos ao cliente ──────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS solicitacoes_documentos (
            id         VARCHAR(36)  PRIMARY KEY,
            case_id    VARCHAR(36)  NOT NULL REFERENCES cases(id),
            client_id  VARCHAR(36)  NOT NULL REFERENCES clients(id),
            mensagem   TEXT,
            status     VARCHAR(20)  NOT NULL DEFAULT 'pendente',
            created_by VARCHAR(36),
            created_at TIMESTAMPTZ  DEFAULT now(),
            updated_at TIMESTAMPTZ  DEFAULT now(),
            deleted_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_solicitacoes_documentos_case_id "
        "ON solicitacoes_documentos (case_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_solicitacoes_documentos_client_id "
        "ON solicitacoes_documentos (client_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS solicitacao_documento_itens (
            id             VARCHAR(36)  PRIMARY KEY,
            solicitacao_id VARCHAR(36)  NOT NULL REFERENCES solicitacoes_documentos(id),
            prova_id       VARCHAR(36)  REFERENCES provas(id),
            nome           VARCHAR(255) NOT NULL,
            descricao      TEXT,
            status         VARCHAR(20)  NOT NULL DEFAULT 'pendente',
            documento_id   VARCHAR(36)  REFERENCES documents(id),
            enviado_em     TIMESTAMPTZ,
            created_at     TIMESTAMPTZ  DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_solicitacao_documento_itens_solicitacao_id "
        "ON solicitacao_documento_itens (solicitacao_id)"
    )

    # ── 3. Régua de cobrança ao cliente — registro de degraus enviados ──────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fee_cobranca_envios (
            id         VARCHAR(36) PRIMARY KEY,
            fee_id     VARCHAR(36) NOT NULL REFERENCES fees(id),
            degrau     VARCHAR(20) NOT NULL,
            enviado_em TIMESTAMPTZ DEFAULT now(),
            CONSTRAINT uq_fee_cobranca_envios_fee_degrau UNIQUE (fee_id, degrau)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fee_cobranca_envios_fee_id "
        "ON fee_cobranca_envios (fee_id)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS fee_cobranca_envios")
    op.execute("DROP TABLE IF EXISTS solicitacao_documento_itens")
    op.execute("DROP TABLE IF EXISTS solicitacoes_documentos")
    op.execute("ALTER TABLE cases DROP COLUMN IF EXISTS datajud_ultimo_andamento_em")
