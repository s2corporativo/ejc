"""095 — índice GIN full-text (portuguese) para a perna FTS do RAG híbrido.

Auditoria de IA 2026-07-17 (achado A-3): a perna lexical do RRF usava só pg_trgm
(similaridade de trigramas de caractere). Este índice habilita a perna FULL-TEXT
(tsvector 'portuguese' + ts_rank_cd), melhor para termos raros e citações exatas
(art./súmula/nº CNJ). A perna FTS em ai_service._fundir_lexical é gated por
RAG_FTS_ENABLED (default OFF) — LIGUE a flag só DEPOIS que este índice existir,
senão a consulta FTS varre a tabela inteira (lenta).

Índice de EXPRESSÃO imutável (config 'portuguese' literal). Criado CONCURRENTLY
(sem travar escrita na tabela) dentro de autocommit_block — mesmo padrão da 094.

Revision ID: 095_rag_fts_gin_index
Revises: 094_case_area_taxonomia
"""
from alembic import op

revision = "095_rag_fts_gin_index"
down_revision = "094_case_area_taxonomia"
branch_labels = None
depends_on = None

_INDEX = "ix_knowledge_chunks_fts_pt"


def upgrade() -> None:
    # CONCURRENTLY não pode rodar em transação → autocommit_block (idem 094).
    with op.get_context().autocommit_block():
        op.execute(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {_INDEX} "
            "ON knowledge_chunks USING GIN "
            "(to_tsvector('portuguese', conteudo))"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {_INDEX}")
