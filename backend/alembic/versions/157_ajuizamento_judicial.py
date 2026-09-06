"""157 — núcleo de ajuizamento e integração judicial.

Cria as tabelas próprias do fluxo de protocolo (perfis de integração por
tribunal, ajuizamentos, transições de estado, tentativas idempotentes,
registro de protocolos, eventos de sincronização e cache TPU). Todas
referenciam as entidades canônicas existentes (clients, cases, users,
legal_docs, processes) — nenhuma duplica cadastro.

Expand-only: nenhuma tabela existente é alterada. Nenhum segredo é
persistido (perfis guardam só referência ao cofre). Downgrade remove apenas
o que esta migration criou.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "157_ajuizamento_judicial"
down_revision = "156_case_despesas_processuais"
branch_labels = None
depends_on = None


def _ts(nome: str, **kw):
    return sa.Column(nome, sa.DateTime(timezone=True), **kw)


def upgrade() -> None:
    op.create_table(
        "judicial_integration_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tribunal_code", sa.String(10), nullable=False),
        sa.Column("tribunal_nome", sa.String(120), nullable=True),
        sa.Column("segment", sa.String(30), nullable=False),
        sa.Column("degree", sa.String(10), nullable=False, server_default="1"),
        sa.Column("system", sa.String(20), nullable=False),
        sa.Column("environment", sa.String(20), nullable=False, server_default="homologacao"),
        sa.Column("integration_type", sa.String(30), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=True),
        sa.Column("api_version", sa.String(20), nullable=True),
        sa.Column("auth_type", sa.String(30), nullable=False, server_default="none"),
        sa.Column("client_id_ref", sa.String(120), nullable=True),
        sa.Column("certificate_ref", sa.String(120), nullable=True),
        sa.Column("certificate_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("filing_supported", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("append_petition_supported", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("process_query_supported", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("movement_query_supported", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("document_download_supported", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notice_query_supported", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("callback_supported", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("authorized", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("production_endpoint_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("credentials_valid", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("homologation_checklist", sa.JSON(), nullable=True),
        _ts("homologated_at", nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="REQUIRES_AUTHORIZATION"),
        sa.Column("documentation_url", sa.String(500), nullable=True),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        _ts("created_at", server_default=sa.func.now()),
        _ts("updated_at", server_default=sa.func.now()),
        sa.UniqueConstraint(
            "tribunal_code", "system", "degree", "environment",
            name="uq_judicial_profile_tribunal_sistema_grau_ambiente",
        ),
    )
    op.create_index(
        "ix_judicial_integration_profiles_tribunal_code",
        "judicial_integration_profiles", ["tribunal_code"],
    )

    op.create_table(
        "judicial_filings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column(
            "profile_id", sa.String(36),
            sa.ForeignKey("judicial_integration_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("peticao_legal_doc_id", sa.String(36), sa.ForeignKey("legal_docs.id"), nullable=True),
        sa.Column("estado", sa.String(30), nullable=False, server_default="DRAFT"),
        sa.Column("tribunal_code", sa.String(10), nullable=True),
        sa.Column("system", sa.String(20), nullable=True),
        sa.Column("segment", sa.String(30), nullable=True),
        sa.Column("degree", sa.String(10), nullable=True),
        sa.Column("environment", sa.String(20), nullable=True),
        sa.Column("jurisdicao", sa.String(120), nullable=True),
        sa.Column("codigo_localidade", sa.String(20), nullable=True),
        sa.Column("competencia", sa.String(120), nullable=True),
        sa.Column("competencia_codigo", sa.String(20), nullable=True),
        sa.Column("classe_codigo", sa.String(20), nullable=True),
        sa.Column("classe_nome", sa.String(200), nullable=True),
        sa.Column("assuntos", sa.JSON(), nullable=True),
        sa.Column("valor_causa", sa.Numeric(14, 2), nullable=True),
        sa.Column("nivel_sigilo", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("gratuidade", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("tutela", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("prioridade", sa.String(40), nullable=True),
        sa.Column("caracteristicas", sa.JSON(), nullable=True),
        sa.Column("documentos", sa.JSON(), nullable=True),
        sa.Column("advogados", sa.JSON(), nullable=True),
        sa.Column("canonico", sa.JSON(), nullable=True),
        sa.Column("canonico_hash", sa.String(64), nullable=True),
        sa.Column("preflight", sa.JSON(), nullable=True),
        sa.Column("assinatura", sa.JSON(), nullable=True),
        sa.Column("aprovado_por", sa.String(36), nullable=True),
        _ts("aprovado_em", nullable=True),
        sa.Column("assinado_por", sa.String(36), nullable=True),
        _ts("assinado_em", nullable=True),
        _ts("protocolado_em", nullable=True),
        sa.Column("numero_cnj", sa.String(30), nullable=True),
        sa.Column("process_id", sa.String(36), sa.ForeignKey("processes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ultimo_erro", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        _ts("created_at", server_default=sa.func.now()),
        _ts("updated_at", server_default=sa.func.now()),
        _ts("deleted_at", nullable=True),
    )
    op.create_index("ix_judicial_filings_case_id", "judicial_filings", ["case_id"])
    op.create_index("ix_judicial_filings_client_id", "judicial_filings", ["client_id"])
    op.create_index("ix_judicial_filings_profile_id", "judicial_filings", ["profile_id"])
    op.create_index(
        "ix_judicial_filings_peticao_legal_doc_id", "judicial_filings", ["peticao_legal_doc_id"]
    )
    op.create_index("ix_judicial_filings_estado", "judicial_filings", ["estado"])
    op.create_index("ix_judicial_filings_numero_cnj", "judicial_filings", ["numero_cnj"])

    op.create_table(
        "judicial_filing_transicoes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("filing_id", sa.String(36), sa.ForeignKey("judicial_filings.id"), nullable=False),
        sa.Column("de_estado", sa.String(30), nullable=True),
        sa.Column("para_estado", sa.String(30), nullable=False),
        sa.Column("ator_id", sa.String(36), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=True),
        _ts("created_at", server_default=sa.func.now()),
    )
    op.create_index("ix_judicial_filing_transicoes_filing_id", "judicial_filing_transicoes", ["filing_id"])

    op.create_table(
        "judicial_filing_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("filing_id", sa.String(36), sa.ForeignKey("judicial_filings.id"), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("connector", sa.String(20), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=True),
        sa.Column("response_hash", sa.String(64), nullable=True),
        sa.Column("estado", sa.String(30), nullable=False),
        sa.Column("detalhe", sa.Text(), nullable=True),
        sa.Column("external_protocol", sa.String(120), nullable=True),
        sa.Column("external_process_id", sa.String(120), nullable=True),
        _ts("iniciada_em", server_default=sa.func.now()),
        _ts("concluida_em", nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.UniqueConstraint("idempotency_key", name="uq_judicial_attempt_idempotency"),
    )
    op.create_index("ix_judicial_filing_attempts_filing_id", "judicial_filing_attempts", ["filing_id"])
    op.create_index("ix_judicial_attempts_filing_numero", "judicial_filing_attempts", ["filing_id", "numero"])

    op.create_table(
        "judicial_protocols",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("filing_id", sa.String(36), sa.ForeignKey("judicial_filings.id"), nullable=False),
        sa.Column(
            "attempt_id", sa.String(36),
            sa.ForeignKey("judicial_filing_attempts.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("tribunal", sa.String(10), nullable=True),
        sa.Column("system", sa.String(20), nullable=False),
        sa.Column("environment", sa.String(20), nullable=True),
        sa.Column("connector", sa.String(20), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.Column("external_protocol", sa.String(120), nullable=True),
        sa.Column("external_process_id", sa.String(120), nullable=True),
        sa.Column("cnj_number", sa.String(30), nullable=True),
        sa.Column("distribution_unit", sa.String(200), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("receipt_document_id", sa.String(36), nullable=True),
        sa.Column("request_hash", sa.String(64), nullable=True),
        sa.Column("response_hash", sa.String(64), nullable=True),
        _ts("submitted_at", nullable=True),
        _ts("confirmed_at", nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        _ts("created_at", server_default=sa.func.now()),
    )
    op.create_index("ix_judicial_protocols_case_id", "judicial_protocols", ["case_id"])
    op.create_index("ix_judicial_protocols_filing_id", "judicial_protocols", ["filing_id"])
    op.create_index("ix_judicial_protocols_cnj_number", "judicial_protocols", ["cnj_number"])
    op.create_index("ix_judicial_protocols_case_cnj", "judicial_protocols", ["case_id", "cnj_number"])

    op.create_table(
        "judicial_sync_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column(
            "filing_id", sa.String(36),
            sa.ForeignKey("judicial_filings.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("cnj_number", sa.String(30), nullable=True),
        sa.Column("fonte", sa.String(20), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False),
        sa.Column("movimentos_novos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("detalhe", sa.Text(), nullable=True),
        _ts("created_at", server_default=sa.func.now()),
    )
    op.create_index("ix_judicial_sync_events_case_id", "judicial_sync_events", ["case_id"])
    op.create_index("ix_judicial_sync_events_filing_id", "judicial_sync_events", ["filing_id"])
    op.create_index("ix_judicial_sync_events_cnj_number", "judicial_sync_events", ["cnj_number"])

    op.create_table(
        "judicial_tpu_itens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tipo", sa.String(12), nullable=False),
        sa.Column("codigo", sa.String(20), nullable=False),
        sa.Column("descricao", sa.String(400), nullable=False),
        sa.Column("situacao", sa.String(20), nullable=False, server_default="ativo"),
        sa.Column("pai_codigo", sa.String(20), nullable=True),
        sa.Column("versao", sa.String(40), nullable=True),
        sa.Column("origem", sa.String(40), nullable=False, server_default="cnj_sgt"),
        _ts("sincronizado_em", server_default=sa.func.now()),
        sa.UniqueConstraint("tipo", "codigo", name="uq_judicial_tpu_tipo_codigo"),
    )
    op.create_index("ix_judicial_tpu_itens_tipo", "judicial_tpu_itens", ["tipo"])


def downgrade() -> None:
    op.drop_index("ix_judicial_tpu_itens_tipo", table_name="judicial_tpu_itens")
    op.drop_table("judicial_tpu_itens")
    op.drop_index("ix_judicial_sync_events_cnj_number", table_name="judicial_sync_events")
    op.drop_index("ix_judicial_sync_events_filing_id", table_name="judicial_sync_events")
    op.drop_index("ix_judicial_sync_events_case_id", table_name="judicial_sync_events")
    op.drop_table("judicial_sync_events")
    op.drop_index("ix_judicial_protocols_case_cnj", table_name="judicial_protocols")
    op.drop_index("ix_judicial_protocols_cnj_number", table_name="judicial_protocols")
    op.drop_index("ix_judicial_protocols_filing_id", table_name="judicial_protocols")
    op.drop_index("ix_judicial_protocols_case_id", table_name="judicial_protocols")
    op.drop_table("judicial_protocols")
    op.drop_index("ix_judicial_attempts_filing_numero", table_name="judicial_filing_attempts")
    op.drop_index("ix_judicial_filing_attempts_filing_id", table_name="judicial_filing_attempts")
    op.drop_table("judicial_filing_attempts")
    op.drop_index("ix_judicial_filing_transicoes_filing_id", table_name="judicial_filing_transicoes")
    op.drop_table("judicial_filing_transicoes")
    op.drop_index("ix_judicial_filings_numero_cnj", table_name="judicial_filings")
    op.drop_index("ix_judicial_filings_estado", table_name="judicial_filings")
    op.drop_index("ix_judicial_filings_peticao_legal_doc_id", table_name="judicial_filings")
    op.drop_index("ix_judicial_filings_profile_id", table_name="judicial_filings")
    op.drop_index("ix_judicial_filings_client_id", table_name="judicial_filings")
    op.drop_index("ix_judicial_filings_case_id", table_name="judicial_filings")
    op.drop_table("judicial_filings")
    op.drop_index(
        "ix_judicial_integration_profiles_tribunal_code",
        table_name="judicial_integration_profiles",
    )
    op.drop_table("judicial_integration_profiles")
