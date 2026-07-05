"""072 — LGPD como vertical de produto: ROPA (Registro de Operações de
Tratamento, art. 37) por cliente. Base do RIPD (art. 38).

Cria a tabela lgpd_registros_tratamento (FK clients, soft delete). Cada linha é
METADADO da operação — categorias de dados/titulares, NUNCA dados pessoais de
titular real (ver models/lgpd_tratamento.py). Por isso não há colunas de PII
cifrada aqui (diferente de socios_sociedade).

base_legal/risco como VARCHAR (validação de domínio no Pydantic) — mesmo
trade-off das demais tabelas raw-SQL do projeto (evita ENUM nativo em migration
idempotente).

ADITIVO PURO e IDEMPOTENTE: CREATE TABLE/INDEX IF NOT EXISTS; nenhuma tabela
existente é tocada.

Revision ID: 072_lgpd_registros
Revises: 071_sociedades_cliente
Create Date: 2026-07-05
"""
from alembic import op

revision = "072_lgpd_registros"
down_revision = "071_sociedades_cliente"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS lgpd_registros_tratamento (
            id                          VARCHAR(36)  PRIMARY KEY,
            client_id                   VARCHAR(36)  NOT NULL REFERENCES clients(id),
            nome_operacao               VARCHAR(255) NOT NULL,
            finalidade                  TEXT         NOT NULL,
            base_legal                  VARCHAR(30)  NOT NULL,
            categorias_dados            TEXT         NOT NULL,
            categorias_titulares        TEXT         NOT NULL,
            dados_sensiveis             BOOLEAN      NOT NULL DEFAULT FALSE,
            compartilhamento            TEXT,
            transferencia_internacional BOOLEAN      NOT NULL DEFAULT FALSE,
            paises_transferencia        TEXT,
            prazo_retencao              TEXT         NOT NULL,
            medidas_seguranca           TEXT         NOT NULL,
            risco                       VARCHAR(10)  NOT NULL DEFAULT 'baixo',
            created_at                  TIMESTAMPTZ  DEFAULT now(),
            updated_at                  TIMESTAMPTZ  DEFAULT now(),
            deleted_at                  TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lgpd_registros_tratamento_client_id "
        "ON lgpd_registros_tratamento (client_id)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS lgpd_registros_tratamento")
