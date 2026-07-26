"""122 — publicação explícita no Portal + hash SHA-256 de documentos

Introduz:
  • documents.sha256           — hash SHA-256 (hex) do conteúdo na ingestão (DOC-022)
  • documents.portal_visible   — publicação EXPLÍCITA no Portal do Cliente
                                 (DOC-049/050/SYS-064; NÃO usar confidencialidade
                                 como se fosse publicação). Default false.
  • documents.publicado_em/por, revogado_em/por — trilha de publicação/revogação.
  • case_movimentos.portal_visible + publicado_em/por — movimentações internas
    NÃO aparecem no Portal por padrão (SYS-021/SYS-022, fail-closed).

Todas as colunas são ADITIVAS e idempotentes (verifica existência antes de
adicionar) — nada quebra dados/rotas existentes; docs/movimentos antigos ficam
NULL/false (não publicados).

Revision ID: 122_documentos_publicacao_hash
Revises: 121_sala_juridica_chat
Create Date: 2026-07-26
"""
from alembic import op
import sqlalchemy as sa

revision = "122_documentos_publicacao_hash"
down_revision = "121_sala_juridica_chat"
branch_labels = None
depends_on = None


def _colunas(insp, tabela: str) -> set[str]:
    return {c["name"] for c in insp.get_columns(tabela)}


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # ── documents ────────────────────────────────────────────────────────────
    cols_docs = _colunas(insp, "documents")

    if "sha256" not in cols_docs:
        op.add_column("documents", sa.Column("sha256", sa.String(64), nullable=True))
        op.create_index("ix_documents_sha256", "documents", ["sha256"])

    if "portal_visible" not in cols_docs:
        op.add_column(
            "documents",
            sa.Column("portal_visible", sa.Boolean(), nullable=False,
                      server_default=sa.false()),
        )
        op.create_index("ix_documents_portal_visible", "documents", ["portal_visible"])

    if "publicado_em" not in cols_docs:
        op.add_column("documents",
                      sa.Column("publicado_em", sa.DateTime(timezone=True), nullable=True))
    if "publicado_por" not in cols_docs:
        op.add_column("documents",
                      sa.Column("publicado_por", sa.String(36),
                                sa.ForeignKey("users.id"), nullable=True))
    if "revogado_em" not in cols_docs:
        op.add_column("documents",
                      sa.Column("revogado_em", sa.DateTime(timezone=True), nullable=True))
    if "revogado_por" not in cols_docs:
        op.add_column("documents",
                      sa.Column("revogado_por", sa.String(36),
                                sa.ForeignKey("users.id"), nullable=True))

    # ── case_movimentos ──────────────────────────────────────────────────────
    cols_mov = _colunas(insp, "case_movimentos")

    if "portal_visible" not in cols_mov:
        op.add_column(
            "case_movimentos",
            sa.Column("portal_visible", sa.Boolean(), nullable=False,
                      server_default=sa.false()),
        )
        op.create_index("ix_case_movimentos_portal_visible",
                        "case_movimentos", ["portal_visible"])

    if "publicado_em" not in cols_mov:
        op.add_column("case_movimentos",
                      sa.Column("publicado_em", sa.DateTime(timezone=True), nullable=True))
    if "publicado_por" not in cols_mov:
        op.add_column("case_movimentos",
                      sa.Column("publicado_por", sa.String(36),
                                sa.ForeignKey("users.id"), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    cols_mov = _colunas(insp, "case_movimentos")
    if "publicado_por" in cols_mov:
        op.drop_column("case_movimentos", "publicado_por")
    if "publicado_em" in cols_mov:
        op.drop_column("case_movimentos", "publicado_em")
    if "portal_visible" in cols_mov:
        op.drop_index("ix_case_movimentos_portal_visible", table_name="case_movimentos")
        op.drop_column("case_movimentos", "portal_visible")

    cols_docs = _colunas(insp, "documents")
    if "revogado_por" in cols_docs:
        op.drop_column("documents", "revogado_por")
    if "revogado_em" in cols_docs:
        op.drop_column("documents", "revogado_em")
    if "publicado_por" in cols_docs:
        op.drop_column("documents", "publicado_por")
    if "publicado_em" in cols_docs:
        op.drop_column("documents", "publicado_em")
    if "portal_visible" in cols_docs:
        op.drop_index("ix_documents_portal_visible", table_name="documents")
        op.drop_column("documents", "portal_visible")
    if "sha256" in cols_docs:
        op.drop_index("ix_documents_sha256", table_name="documents")
        op.drop_column("documents", "sha256")
