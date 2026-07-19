"""102_matriz_teses — FASE 3 do Orquestrador Jurídico.

Matriz de Teses estruturada (tese × fato × prova × precedente):
  • legal_issues       — questões jurídicas decompostas do caso (origem ia|manual);
  • thesis_candidates  — teses candidatas com score DETERMINÍSTICO `forca`
                         (0-100, calculado no service — nunca nota de LLM) e
                         status HITL (candidata|aprovada|descartada);
  • authority_records  — precedentes com origem REAL (RAG/verificador), trecho
                         obrigatório; "verificada" exige fonte_oficial (service);
  • evidence_links     — vínculos fato × prova × tese × pedido.

Índices por case_id em todas as tabelas (lookup padrão da matriz).

Revision ID: 102_matriz_teses
Revises: 101_case_intelligence_snapshot
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "102_matriz_teses"
down_revision = "101_case_intelligence_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "legal_issues",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("questao", sa.Text(), nullable=False),
        sa.Column("area", sa.String(60)),
        sa.Column("prioridade", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("origem", sa.String(10), nullable=False, server_default="ia"),
        sa.Column("criado_por", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_legal_issues_case_id", "legal_issues", ["case_id"])

    op.create_table(
        "thesis_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("issue_id", sa.String(36), sa.ForeignKey("legal_issues.id")),
        sa.Column("tese", sa.Text(), nullable=False),
        sa.Column("fundamento", sa.Text()),
        sa.Column("fatos_relacionados", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("provas", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("precedentes", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("vulnerabilidades", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("forca", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(15), nullable=False, server_default="candidata"),
        sa.Column("criado_por", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("aprovado_por", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("aprovado_em", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_thesis_candidates_case_id", "thesis_candidates", ["case_id"])

    op.create_table(
        "authority_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id")),
        sa.Column("tribunal", sa.String(60)),
        sa.Column("processo_ref", sa.String(120)),
        sa.Column("orgao", sa.String(120)),
        sa.Column("data_julgamento", sa.String(40)),
        sa.Column("tema", sa.String(300)),
        sa.Column("trecho", sa.Text(), nullable=False),
        sa.Column("fonte_oficial", sa.String(500)),
        sa.Column("status_verificacao", sa.String(20), nullable=False,
                  server_default="nao_verificada"),
        sa.Column("favoravel", sa.Boolean()),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_authority_records_case_id", "authority_records", ["case_id"])

    op.create_table(
        "evidence_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("fato", sa.Text(), nullable=False),
        sa.Column("prova_id", sa.String(36), sa.ForeignKey("provas.id")),
        sa.Column("tese_id", sa.String(36), sa.ForeignKey("thesis_candidates.id")),
        sa.Column("pedido", sa.Text()),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_evidence_links_case_id", "evidence_links", ["case_id"])


def downgrade() -> None:
    op.drop_table("evidence_links")
    op.drop_table("authority_records")
    op.drop_table("thesis_candidates")
    op.drop_table("legal_issues")
