"""legal_doc_revisao — histórico imutável de revisões de conteúdo da peça.

DOC-056: até aqui, editar o `conteudo` de uma LegalDoc incrementava `versao`
mas SOBRESCREVIA o texto, sem qualquer histórico — a versão anterior (v1) era
perdida. Esta tabela guarda, ANTES de cada sobrescrita, o conteúdo anterior
como registro append-only (imutável), tornando cada versão recuperável e
amarrando a validação jurídica ao `content_hash` da revisão (DOC-068).

Colunas:
  - id            (PK, VARCHAR 36)
  - legal_doc_id  (FK legal_docs.id, NOT NULL) — peça de origem.
  - revisao       (INT, NOT NULL) — número da versão preservada (v anterior).
  - conteudo      (TEXT, NOT NULL) — snapshot do conteúdo daquela versão.
  - content_hash  (VARCHAR 64) — sha256 hex do conteúdo (amarra validação).
  - origem        (VARCHAR 40) — 'edicao_manual', 'geracao_ia', etc.
  - gerado_por    (FK users.id) — autor da revisão (trilha de autoria).
  - criado_em     (TIMESTAMPTZ, default now()).
  - imutavel      (BOOL, default true) — marca append-only.
Índice único (legal_doc_id, revisao): uma linha por versão de cada peça.

Aditiva: cria tabela nova (não altera schema existente). DDL idempotente
(IF NOT EXISTS) — segura para re-execução no boot (RUN_MIGRATIONS=1).

Revision ID: 125_legal_doc_revisao
Revises: 124_data_room_token_hash
Create Date: 2026-07-26
"""
from alembic import op

revision = "125_legal_doc_revisao"
down_revision = "124_data_room_token_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS legal_doc_revisoes (
            id            VARCHAR(36) PRIMARY KEY,
            legal_doc_id  VARCHAR(36) NOT NULL REFERENCES legal_docs(id),
            revisao       INTEGER NOT NULL,
            conteudo      TEXT NOT NULL,
            content_hash  VARCHAR(64),
            origem        VARCHAR(40),
            gerado_por    VARCHAR(36) REFERENCES users(id),
            criado_em     TIMESTAMPTZ NOT NULL DEFAULT now(),
            imutavel      BOOLEAN NOT NULL DEFAULT true
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_legal_doc_revisoes_legal_doc_id "
        "ON legal_doc_revisoes (legal_doc_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_legal_doc_revisoes_doc_revisao "
        "ON legal_doc_revisoes (legal_doc_id, revisao)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS legal_doc_revisoes")
