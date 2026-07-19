"""089 — Ficha de Triagem pré-peça (gate de qualidade da Jornada do Caso)

Cria a tabela `fichas_triagem`: uma ficha CORRENTE por caso (UNIQUE case_id),
enquadramento processual + tutela + mapa probatório + valor/risco + pedidos,
`confianca` (JSONB) do pré-preenchimento por IA e `status` (rascunho|confirmada).

A peça só é gerada (POST /pecas/gerar) quando existe ficha `confirmada` para o
caso (FICHA_TRIAGEM_OBRIGATORIA) — evita "bom modelo no caso errado".

`status`/`risco_processual` como VARCHAR (validação de domínio no Pydantic) —
mesmo trade-off das demais tabelas raw-SQL (evita ENUM nativo em migration
idempotente, ver 073_provas).

ADITIVO PURO e IDEMPOTENTE: CREATE TABLE/INDEX IF NOT EXISTS; nenhuma tabela
existente é tocada.

Revision ID: 089_fichas_triagem
Revises: 088_refresh_token_graca_rotacao
Create Date: 2026-07-12
"""
from alembic import op

revision = "089_fichas_triagem"
down_revision = "088_refresh_token_graca_rotacao"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fichas_triagem (
            id                    VARCHAR(36)  PRIMARY KEY,
            case_id               VARCHAR(36)  NOT NULL UNIQUE REFERENCES cases(id),
            competencia           TEXT,
            rito                  TEXT,
            legitimidade_ativa    TEXT,
            legitimidade_passiva  TEXT,
            prescricao_decadencia TEXT,
            tutela_urgencia       BOOLEAN      NOT NULL DEFAULT FALSE,
            tutela_fundamento     TEXT,
            provas_disponiveis    TEXT,
            provas_faltantes      TEXT,
            valor_causa           VARCHAR(120),
            risco_processual      VARCHAR(10),
            risco_nota            TEXT,
            pedidos_principais    TEXT,
            pedidos_subsidiarios  TEXT,
            confianca             JSONB,
            status                VARCHAR(20)  NOT NULL DEFAULT 'rascunho',
            created_by            VARCHAR(36),
            created_at            TIMESTAMPTZ  DEFAULT now(),
            updated_at            TIMESTAMPTZ  DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fichas_triagem_case_id "
        "ON fichas_triagem (case_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fichas_triagem_status "
        "ON fichas_triagem (status)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS fichas_triagem")
