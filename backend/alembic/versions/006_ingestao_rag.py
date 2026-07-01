"""006 — Infraestrutura de ingestão automática no RAG.

Adiciona à base de conhecimento (knowledge_docs) os campos de rastreabilidade
e deduplicação necessários para jobs automáticos (leis, jurisprudência, índices,
diários oficiais), e cria a tabela de controle `fontes_ingestao`.

- knowledge_docs.chave_origem   : chave estável da fonte (URN LexML, nº CNJ,
                                  código da norma, hash). Permite UPSERT idempotente.
- knowledge_docs.hash_conteudo  : SHA-1 do conteúdo normalizado — detecta alteração
                                  sem re-embeddar documento inalterado.
- knowledge_docs.atualizado_em  : data da última reingestão.
- fontes_ingestao               : 1 linha por fonte (slug), com última execução,
                                  status, contadores e erro — auditável no painel.

Índice único parcial em chave_origem (WHERE NOT NULL) impede duplicar o mesmo
documento de origem; documentos manuais (chave NULL) não são afetados.
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = "006_ingestao_rag"
down_revision = "005_posmortem"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Campos de rastreabilidade/dedup na base de conhecimento ──────────────
    op.add_column("knowledge_docs",
                  sa.Column("chave_origem", sa.String(255), nullable=True))
    op.add_column("knowledge_docs",
                  sa.Column("hash_conteudo", sa.String(40), nullable=True))
    op.add_column("knowledge_docs",
                  sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True))

    # Índice único parcial: a mesma chave de origem não pode ser ingerida 2x.
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_knowledge_docs_chave_origem
        ON knowledge_docs (chave_origem)
        WHERE chave_origem IS NOT NULL AND deleted_at IS NULL
    """)

    # ── Tabela de controle das fontes de ingestão ────────────────────────────
    op.create_table(
        "fontes_ingestao",
        sa.Column("slug",            sa.String(60),  primary_key=True),
        sa.Column("descricao",       sa.String(255), nullable=False),
        sa.Column("categoria_rag",   sa.String(50),  nullable=True),
        sa.Column("ativo",           sa.Boolean,     nullable=False, server_default=sa.true()),
        sa.Column("ultima_execucao", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultimo_status",   sa.String(20),  nullable=True),   # sucesso | erro | parcial
        sa.Column("registros_novos", sa.Integer,     nullable=False, server_default="0"),
        sa.Column("registros_total", sa.Integer,     nullable=False, server_default="0"),
        sa.Column("ultimo_erro",     sa.Text,        nullable=True),
        sa.Column("created_at",      sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("fontes_ingestao")
    op.execute("DROP INDEX IF EXISTS uq_knowledge_docs_chave_origem")
    op.drop_column("knowledge_docs", "atualizado_em")
    op.drop_column("knowledge_docs", "hash_conteudo")
    op.drop_column("knowledge_docs", "chave_origem")
