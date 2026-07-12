"""085 — NFS-e (Nota Fiscal de Serviço) emitida via provedor (GATED)

Tabela `notas_fiscais_servico` — persiste cada NFS-e emitida (ou tentada) a
partir de um honorário/recebível (fee_id) ou avulsa. O módulo nasce DESLIGADO
(NFSE_ENABLED=false) e em HOMOLOGAÇÃO; ver services/nfse/ e docs/NFSE_VIABILIDADE.md.

`status`/`ambiente`/`provider` como VARCHAR com validação de domínio na aplicação
(NFSeStatus) — mesmo trade-off idempotente das migrations 073/084 (evita ENUM
nativo). UNIQUE(provider, referencia) = idempotência (uma nota por referência).

ADITIVO PURO e IDEMPOTENTE: CREATE TABLE/INDEX IF NOT EXISTS.

Revision ID: 085_nfse
Revises: 084_automacoes_cliente
Create Date: 2026-07-12
"""
from alembic import op

revision = "085_nfse"
down_revision = "084_automacoes_cliente"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS notas_fiscais_servico (
            id            VARCHAR(36)  PRIMARY KEY,
            fee_id        VARCHAR(36)  REFERENCES fees(id),
            client_id     VARCHAR(36)  REFERENCES clients(id),
            provider      VARCHAR(30)  NOT NULL DEFAULT 'nuvemfiscal',
            provider_id   VARCHAR(64),
            referencia    VARCHAR(80),
            ambiente      VARCHAR(20)  NOT NULL DEFAULT 'homologacao',
            status        VARCHAR(20)  NOT NULL DEFAULT 'processando',
            numero        VARCHAR(30),
            chave_acesso  VARCHAR(60),
            valor         NUMERIC(14,2),
            descricao     TEXT,
            xml_url       VARCHAR(500),
            pdf_url       VARCHAR(500),
            mensagem_erro TEXT,
            created_by    VARCHAR(36),
            created_at    TIMESTAMPTZ  DEFAULT now(),
            updated_at    TIMESTAMPTZ  DEFAULT now(),
            CONSTRAINT uq_notas_fiscais_servico_provider_referencia
                UNIQUE (provider, referencia)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notas_fiscais_servico_fee_id "
        "ON notas_fiscais_servico (fee_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notas_fiscais_servico_client_id "
        "ON notas_fiscais_servico (client_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notas_fiscais_servico_provider_id "
        "ON notas_fiscais_servico (provider_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notas_fiscais_servico_status "
        "ON notas_fiscais_servico (status)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS notas_fiscais_servico")
