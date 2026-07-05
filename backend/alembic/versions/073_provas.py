"""073 — Gestão de Provas por caso (acervo probatório estruturado)

Cria a tabela `provas` (FK cases, soft delete). Cada prova é CASO-scoped e pode,
opcionalmente, apontar para um Document do GED (document_id) e/ou sustentar uma
Tese/pedido (tese_id). `ordem` define a sequência dos anexos no "Documento Único
de Anexos" (Visual Law).

`tipo` como VARCHAR (validação de domínio no Pydantic, enum TipoProva) — mesmo
trade-off das demais tabelas raw-SQL do projeto (evita ENUM nativo em migration
idempotente).

ADITIVO PURO e IDEMPOTENTE: CREATE TABLE/INDEX IF NOT EXISTS; nenhuma tabela
existente é tocada.

Revision ID: 073_provas
Revises: 072_lgpd_registros
Create Date: 2026-07-05
"""
from alembic import op

revision = "073_provas"
down_revision = "072_lgpd_registros"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS provas (
            id            VARCHAR(36)  PRIMARY KEY,
            case_id       VARCHAR(36)  NOT NULL REFERENCES cases(id),
            tipo          VARCHAR(20)  NOT NULL DEFAULT 'documental',
            titulo        VARCHAR(255) NOT NULL,
            descricao     TEXT,
            document_id   VARCHAR(36)  REFERENCES documents(id),
            tese_id       VARCHAR(36)  REFERENCES teses(id),
            fato_probando TEXT,
            ordem         INTEGER      NOT NULL DEFAULT 0,
            created_by    VARCHAR(36),
            created_at    TIMESTAMPTZ  DEFAULT now(),
            updated_at    TIMESTAMPTZ  DEFAULT now(),
            deleted_at    TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_provas_case_id ON provas (case_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_provas_document_id ON provas (document_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_provas_tese_id ON provas (tese_id)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS provas")
