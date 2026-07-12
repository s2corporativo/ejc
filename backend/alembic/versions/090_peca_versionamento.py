"""090 — Versionamento/controle de peças (código estável por ramo)

Adiciona a `legal_docs`:
  - `area`        VARCHAR(40)  — ramo do direito da geração (chave AREAS_DIREITO)
  - `codigo_peca` VARCHAR(30)  — identificador estável EJC-<SIGLA>-<NNN>

Cria a tabela de contador atômico por ramo:
  - `peca_codigo_contador (area PK, ultimo NOT NULL DEFAULT 0)`
    alimenta o UPSERT ... RETURNING de app.services.peca_numeracao
    (numeração sem corrida entre requisições simultâneas).

O código/rodapé é injetado apenas no RENDER (PDF/DOCX) — nunca no texto da IA
(Regra 9 do padrão-ouro). Peças antigas ficam com `codigo_peca` NULL e o render
degrada sem quebrar.

ADITIVO PURO e IDEMPOTENTE: ADD COLUMN/CREATE TABLE/INDEX IF NOT EXISTS; nenhum
dado existente é tocado.

Revision ID: 090_peca_versionamento
Revises: 089_fichas_triagem
Create Date: 2026-07-12
"""
from alembic import op

revision = "090_peca_versionamento"
down_revision = "089_fichas_triagem"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE legal_docs ADD COLUMN IF NOT EXISTS area VARCHAR(40)")
    op.execute("ALTER TABLE legal_docs ADD COLUMN IF NOT EXISTS codigo_peca VARCHAR(30)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_legal_docs_codigo_peca "
        "ON legal_docs (codigo_peca)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS peca_codigo_contador (
            area   VARCHAR(40) PRIMARY KEY,
            ultimo INTEGER     NOT NULL DEFAULT 0
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS peca_codigo_contador")
    op.execute("DROP INDEX IF EXISTS ix_legal_docs_codigo_peca")
    op.execute("ALTER TABLE legal_docs DROP COLUMN IF EXISTS codigo_peca")
    op.execute("ALTER TABLE legal_docs DROP COLUMN IF EXISTS area")
