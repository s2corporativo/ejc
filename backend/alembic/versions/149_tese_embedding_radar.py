"""tese_embedding_radar

Revision ID: 149_tese_embedding_radar
Revises: 148_banco_teses_juridicas
Create Date: 2026-08-24 03:00:00.000000

Camada 2 (semântica) do Radar Jurisprudencial (PR 4 da série de consolidação
do Banco de Teses — ver docs/decisoes/ADR_BANCO_TESES_CANONICO_2026-08-24.md).

Adiciona `teses.embedding vector(1024)` (mesma dimensão de
`knowledge_chunks.embedding`, migração 096 — modelo multilingual-e5-large,
configurável por `EMBEDDINGS_DIM`) + índice HNSW cosine, mesmo padrão de
`096_rag_embedding_1024.py`. Coluna NULLABLE: nenhuma tese existente quebra;
teses sem embedding simplesmente não entram na Camada 2 até serem
(re)computadas por `app/services/radar_jurisprudencial_embedding.py`.

Não é a mesma coisa que `KnowledgeChunk.embedding` (RAG de perguntas/
respostas) — este vetor é do TEXTO DA TESE (título+descrição+fundamentação+
jurisprudência), usado só para comparar contra a decisão nova varrida pelo
radar. Nunca exposto em resposta de API (dado técnico interno, mesma decisão
já tomada para `KnowledgeChunk.embedding`).

`ADD COLUMN` via `op.add_column` (nullable, allowlisted pelo classificador de
compatibilidade de deploy). O índice HNSW usa `op.execute` com
`CREATE INDEX IF NOT EXISTS` — o único padrão de `op.execute` que o mesmo
classificador reconhece como expand-only seguro
(`scripts/check_migration_compatibility.py::_is_safe_expand_ddl`), o mesmo
padrão já usado pela migração 096.
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = '149_tese_embedding_radar'
down_revision = '148_banco_teses_juridicas'
branch_labels = None
depends_on = None

_HNSW = "ix_teses_embedding_hnsw"


def upgrade() -> None:
    op.add_column("teses", sa.Column("embedding", Vector(1024), nullable=True))
    # Nome do índice literal (não f-string): o classificador de compatibilidade
    # de deploy só reconhece `op.execute` como expand-only seguro quando o SQL
    # é uma string literal estática (ast.Constant) — precisa bater com o SQL
    # abaixo se `_HNSW` mudar.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_teses_embedding_hnsw ON teses "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_teses_embedding_hnsw")
    op.drop_column("teses", "embedding")
