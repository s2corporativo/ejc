"""099 — legal_docs: comprovante de protocolo (prova de tempestividade)

Contexto (auditoria):
    O peticionamento no EJC é MANUAL — o usuário exporta o PDF da peça e protocola
    no PJe/eproc por fora. Como nenhum modelo guardava o número/comprovante do
    protocolo, a PROVA DE TEMPESTIVIDADE ficava inteiramente fora do sistema.

    Esta migration adiciona à tabela `legal_docs` quatro colunas nullable para
    registrar, na própria peça, o comprovante de protocolo:
      - `numero_protocolo`   VARCHAR(120) — número/id do protocolo no tribunal;
      - `protocolado_em`     TIMESTAMPTZ  — data/hora do protocolo (tz-aware);
      - `protocolo_tribunal` VARCHAR(120) — tribunal/órgão onde foi protocolado;
      - `protocolo_comprovante_doc_id` VARCHAR(36) — id de um Document já anexado
        com o comprovante. String(36) SEM FK (mesmo padrão audit-actor de
        `deadlines.concluido_por`, migration 098): não impõe RESTRICT na exclusão
        do documento nem acopla a prova de tempestividade ao ciclo de vida do
        anexo.

    A LÓGICA de preenchimento vive no backend (routers/legal_docs.py, endpoint
    PATCH /legal-docs/{id}/protocolo) — fora do escopo desta migration, que só
    ajusta o schema.

Idempotente (ADD/DROP COLUMN IF [NOT] EXISTS), seguindo o padrão raw-SQL das
migrations recentes de coluna (059_archiving / 060_client_anonimizacao / 098).

Revision ID: 099_legal_doc_protocolo
Revises: 098_deadline_concluido_por
"""
from alembic import op

revision = "099_legal_doc_protocolo"
down_revision = "098_deadline_concluido_por"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE legal_docs "
        "ADD COLUMN IF NOT EXISTS numero_protocolo varchar(120)"
    )
    op.execute(
        "ALTER TABLE legal_docs "
        "ADD COLUMN IF NOT EXISTS protocolado_em timestamptz"
    )
    op.execute(
        "ALTER TABLE legal_docs "
        "ADD COLUMN IF NOT EXISTS protocolo_tribunal varchar(120)"
    )
    op.execute(
        "ALTER TABLE legal_docs "
        "ADD COLUMN IF NOT EXISTS protocolo_comprovante_doc_id varchar(36)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE legal_docs DROP COLUMN IF EXISTS protocolo_comprovante_doc_id")
    op.execute("ALTER TABLE legal_docs DROP COLUMN IF EXISTS protocolo_tribunal")
    op.execute("ALTER TABLE legal_docs DROP COLUMN IF EXISTS protocolado_em")
    op.execute("ALTER TABLE legal_docs DROP COLUMN IF EXISTS numero_protocolo")
