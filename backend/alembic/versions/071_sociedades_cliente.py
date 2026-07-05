"""071 — gestão societária de CLIENTES empresariais (vertical Empresarial)

Cria as três tabelas do módulo /empresarial/sociedades:
  • sociedades_cliente  — a sociedade do cliente (FK clients, soft delete);
  • socios_sociedade    — quadro societário. LGPD: documento do sócio segue o
    padrão Bloco 6a de clients (migration 061): documento_enc (Fernet) +
    documento_hash (índice cego HMAC) + documento_mascarado (exibição).
    NUNCA existe coluna de documento em texto puro;
  • eventos_societarios — trilha de eventos (alteração contratual, entrada/
    saída de sócio, aumento de capital, distribuição de lucros, ...).

NÃO confundir com office_partners (sócios do escritório — gestao_societaria).

tipo_societario/tipo como VARCHAR (validação de domínio no Pydantic) — evita
tipo ENUM nativo em migration idempotente, mesmo trade-off de outras tabelas
raw-SQL do projeto.

ADITIVO PURO e IDEMPOTENTE: CREATE TABLE/INDEX IF NOT EXISTS; nenhuma tabela
existente é tocada.

Revision ID: 071_sociedades_cliente
Revises: 070_ai_log_critica_adversarial
Create Date: 2026-07-05
"""
from alembic import op

revision = "071_sociedades_cliente"
down_revision = "070_ai_log_critica_adversarial"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sociedades_cliente (
            id              VARCHAR(36)  PRIMARY KEY,
            client_id       VARCHAR(36)  NOT NULL REFERENCES clients(id),
            razao_social    VARCHAR(255) NOT NULL,
            cnpj            VARCHAR(18),
            tipo_societario VARCHAR(20)  NOT NULL,
            capital_social  NUMERIC(15,2),
            created_at      TIMESTAMPTZ  DEFAULT now(),
            updated_at      TIMESTAMPTZ  DEFAULT now(),
            deleted_at      TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sociedades_cliente_client_id "
        "ON sociedades_cliente (client_id)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS socios_sociedade (
            id                  VARCHAR(36)  PRIMARY KEY,
            sociedade_id        VARCHAR(36)  NOT NULL
                                REFERENCES sociedades_cliente(id) ON DELETE CASCADE,
            nome                VARCHAR(255) NOT NULL,
            quotas              NUMERIC(18,2) NOT NULL DEFAULT 0,
            pro_labore          NUMERIC(15,2),
            administrador       BOOLEAN      NOT NULL DEFAULT FALSE,
            documento_enc       TEXT,
            documento_hash      VARCHAR(64),
            documento_mascarado VARCHAR(32),
            created_at          TIMESTAMPTZ  DEFAULT now(),
            updated_at          TIMESTAMPTZ  DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_socios_sociedade_sociedade_id "
        "ON socios_sociedade (sociedade_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_socios_sociedade_documento_hash "
        "ON socios_sociedade (documento_hash)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS eventos_societarios (
            id           VARCHAR(36) PRIMARY KEY,
            sociedade_id VARCHAR(36) NOT NULL
                         REFERENCES sociedades_cliente(id) ON DELETE CASCADE,
            tipo         VARCHAR(30) NOT NULL,
            descricao    TEXT,
            data_evento  DATE        NOT NULL,
            created_by   VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
            created_at   TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_eventos_societarios_sociedade_id "
        "ON eventos_societarios (sociedade_id)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS eventos_societarios")
    op.execute("DROP TABLE IF EXISTS socios_sociedade")
    op.execute("DROP TABLE IF EXISTS sociedades_cliente")
