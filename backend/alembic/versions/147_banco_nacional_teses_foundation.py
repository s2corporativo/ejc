"""147_banco_nacional_teses_foundation

Fundação canônica do Banco Nacional de Teses Jurídicas.

A migração é aditiva e não altera as tabelas legadas `teses`,
`jurisprudencias_internas` ou a matriz por caso. Cria a camada de fonte,
snapshot, precedente, tese, versões, relações, eventos de validação e
checkpoints de ingestão. Nenhuma coleta é executada por esta migração.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "147_banco_nacional_teses"
down_revision = "146_case_sigilo_reforcado"
branch_labels = None
depends_on = None


def _json_default(valor: str) -> sa.TextClause:
    return sa.text(f"'{valor}'::jsonb")


def upgrade() -> None:
    op.create_table(
        "legal_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("nome", sa.String(255), nullable=False),
        sa.Column("categoria", sa.String(40), nullable=False),
        sa.Column("autoridade", sa.String(255)),
        sa.Column("tipo_acesso", sa.String(40), nullable=False),
        sa.Column("url_base", sa.Text(), nullable=False),
        sa.Column("url_validacao", sa.Text()),
        sa.Column("url_termos", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False, server_default="ativo"),
        sa.Column("exige_autenticacao", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("permite_uso_derivado", sa.Boolean()),
        sa.Column("ultima_verificacao", sa.DateTime(timezone=True)),
        sa.Column("observacoes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("slug", name="uq_legal_sources_slug"),
    )
    op.create_index("ix_legal_sources_slug", "legal_sources", ["slug"])
    op.create_index("ix_legal_sources_status", "legal_sources", ["status"])

    op.create_table(
        "legal_source_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("legal_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chave_origem", sa.String(500), nullable=False),
        sa.Column("versao", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("titulo", sa.String(500)),
        sa.Column("conteudo_normalizado", sa.Text(), nullable=False),
        sa.Column("hash_conteudo", sa.String(64), nullable=False),
        sa.Column("url_origem", sa.Text()),
        sa.Column("data_publicacao", sa.Date()),
        sa.Column("capturado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="capturado"),
        sa.Column("vigente", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("metadados", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_id", "chave_origem", "hash_conteudo", name="uq_legal_source_snapshot_origin_hash"),
    )
    op.create_index("ix_legal_source_snapshots_source_id", "legal_source_snapshots", ["source_id"])
    op.create_index("ix_legal_source_snapshots_chave_origem", "legal_source_snapshots", ["chave_origem"])
    op.create_index("ix_legal_source_snapshots_hash_conteudo", "legal_source_snapshots", ["hash_conteudo"])
    op.create_index("ix_legal_source_snapshots_status", "legal_source_snapshots", ["status"])
    op.create_index("ix_legal_source_snapshots_vigente", "legal_source_snapshots", ["vigente"])

    op.create_table(
        "legal_precedents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("legal_sources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("snapshot_id", sa.String(36), sa.ForeignKey("legal_source_snapshots.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("chave_origem", sa.String(500), nullable=False),
        sa.Column("tribunal", sa.String(60)),
        sa.Column("instancia", sa.String(40)),
        sa.Column("orgao_julgador", sa.String(160)),
        sa.Column("classe_processual", sa.String(120)),
        sa.Column("numero_processo", sa.String(80)),
        sa.Column("relator", sa.String(200)),
        sa.Column("data_julgamento", sa.Date()),
        sa.Column("data_publicacao", sa.Date()),
        sa.Column("ementa", sa.Text()),
        sa.Column("fundamento_relevante", sa.Text()),
        sa.Column("resultado", sa.String(30)),
        sa.Column("tema", sa.String(300)),
        sa.Column("url_oficial", sa.Text()),
        sa.Column("hash_conteudo", sa.String(64)),
        sa.Column("status", sa.String(20), nullable=False, server_default="nao_validado"),
        sa.Column("publicidade", sa.String(20), nullable=False, server_default="publico"),
        sa.Column("dados_minimizados", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("observacoes_validacao", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_id", "chave_origem", name="uq_legal_precedent_source_origin"),
    )
    op.create_index("ix_legal_precedents_source_id", "legal_precedents", ["source_id"])
    op.create_index("ix_legal_precedents_snapshot_id", "legal_precedents", ["snapshot_id"])
    op.create_index("ix_legal_precedents_tribunal", "legal_precedents", ["tribunal"])
    op.create_index("ix_legal_precedents_instancia", "legal_precedents", ["instancia"])
    op.create_index("ix_legal_precedents_numero_processo", "legal_precedents", ["numero_processo"])
    op.create_index("ix_legal_precedents_data_julgamento", "legal_precedents", ["data_julgamento"])
    op.create_index("ix_legal_precedents_tema", "legal_precedents", ["tema"])
    op.create_index("ix_legal_precedents_hash_conteudo", "legal_precedents", ["hash_conteudo"])
    op.create_index("ix_legal_precedents_status", "legal_precedents", ["status"])

    op.create_table(
        "legal_theses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("chave_canonica", sa.String(180), nullable=False),
        sa.Column("titulo", sa.String(500), nullable=False),
        sa.Column("area", sa.String(80), nullable=False),
        sa.Column("subarea", sa.String(120)),
        sa.Column("instituto", sa.String(120)),
        sa.Column("tema", sa.String(200)),
        sa.Column("subtema", sa.String(200)),
        sa.Column("situacao_fatica", sa.Text()),
        sa.Column("tipo", sa.String(30), nullable=False, server_default="material"),
        sa.Column("lado", sa.String(10), nullable=False, server_default="ambos"),
        sa.Column("parte_favorecida", sa.String(80)),
        sa.Column("procedimento", sa.String(100)),
        sa.Column("instancia", sa.String(40)),
        sa.Column("tese_principal", sa.Text(), nullable=False),
        sa.Column("fundamento_resumido", sa.Text()),
        sa.Column("argumento_juridico", sa.Text()),
        sa.Column("raciocinio_juridico", sa.Text()),
        sa.Column("pressupostos", postgresql.JSONB(), nullable=False, server_default=_json_default("[]")),
        sa.Column("fatos_necessarios", postgresql.JSONB(), nullable=False, server_default=_json_default("[]")),
        sa.Column("elementos_demonstrar", postgresql.JSONB(), nullable=False, server_default=_json_default("[]")),
        sa.Column("fatos_impeditivos", postgresql.JSONB(), nullable=False, server_default=_json_default("[]")),
        sa.Column("excecoes", postgresql.JSONB(), nullable=False, server_default=_json_default("[]")),
        sa.Column("fundamentacao_legal", postgresql.JSONB(), nullable=False, server_default=_json_default("[]")),
        sa.Column("estrategia", postgresql.JSONB(), nullable=False, server_default=_json_default("{}")),
        sa.Column("provas_necessarias", postgresql.JSONB(), nullable=False, server_default=_json_default("[]")),
        sa.Column("documentos_necessarios", postgresql.JSONB(), nullable=False, server_default=_json_default("[]")),
        sa.Column("argumento_adversario", sa.Text()),
        sa.Column("resposta_adversaria", sa.Text()),
        sa.Column("riscos", postgresql.JSONB(), nullable=False, server_default=_json_default("[]")),
        sa.Column("score_forca", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(30), nullable=False, server_default="coletada"),
        sa.Column("versao", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("vigente", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("origem", sa.String(30), nullable=False, server_default="coleta"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("revisado_por", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("criada_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("revisada_em", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("chave_canonica", name="uq_legal_thesis_canonical_key"),
    )
    op.create_index("ix_legal_theses_chave_canonica", "legal_theses", ["chave_canonica"])
    op.create_index("ix_legal_theses_area", "legal_theses", ["area"])
    op.create_index("ix_legal_theses_subarea", "legal_theses", ["subarea"])
    op.create_index("ix_legal_theses_instituto", "legal_theses", ["instituto"])
    op.create_index("ix_legal_theses_tema", "legal_theses", ["tema"])
    op.create_index("ix_legal_theses_lado", "legal_theses", ["lado"])
    op.create_index("ix_legal_theses_score_forca", "legal_theses", ["score_forca"])
    op.create_index("ix_legal_theses_status", "legal_theses", ["status"])
    op.create_index("ix_legal_theses_vigente", "legal_theses", ["vigente"])

    op.create_table(
        "legal_thesis_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("thesis_id", sa.String(36), sa.ForeignKey("legal_theses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("versao", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("motivo_alteracao", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("thesis_id", "versao", name="uq_legal_thesis_version"),
    )
    op.create_index("ix_legal_thesis_versions_thesis_id", "legal_thesis_versions", ["thesis_id"])

    op.create_table(
        "legal_thesis_precedents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("thesis_id", sa.String(36), sa.ForeignKey("legal_theses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("precedent_id", sa.String(36), sa.ForeignKey("legal_precedents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("relacao", sa.String(30), nullable=False),
        sa.Column("trecho_relevante", sa.Text()),
        sa.Column("observacao", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("thesis_id", "precedent_id", name="uq_legal_thesis_precedent"),
    )
    op.create_index("ix_legal_thesis_precedents_thesis_id", "legal_thesis_precedents", ["thesis_id"])
    op.create_index("ix_legal_thesis_precedents_precedent_id", "legal_thesis_precedents", ["precedent_id"])

    op.create_table(
        "legal_thesis_relations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_thesis_id", sa.String(36), sa.ForeignKey("legal_theses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_thesis_id", sa.String(36), sa.ForeignKey("legal_theses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relacao", sa.String(30), nullable=False),
        sa.Column("justificativa", sa.Text()),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_thesis_id", "target_thesis_id", "relacao", name="uq_legal_thesis_relation"),
    )
    op.create_index("ix_legal_thesis_relations_source", "legal_thesis_relations", ["source_thesis_id"])
    op.create_index("ix_legal_thesis_relations_target", "legal_thesis_relations", ["target_thesis_id"])

    op.create_table(
        "legal_thesis_validation_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("thesis_id", sa.String(36), sa.ForeignKey("legal_theses.id", ondelete="CASCADE")),
        sa.Column("precedent_id", sa.String(36), sa.ForeignKey("legal_precedents.id", ondelete="SET NULL")),
        sa.Column("snapshot_id", sa.String(36), sa.ForeignKey("legal_source_snapshots.id", ondelete="SET NULL")),
        sa.Column("acao", sa.String(30), nullable=False),
        sa.Column("status_anterior", sa.String(30)),
        sa.Column("status_novo", sa.String(30)),
        sa.Column("justificativa", sa.Text(), nullable=False),
        sa.Column("reviewer_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_legal_thesis_validation_events_thesis", "legal_thesis_validation_events", ["thesis_id"])
    op.create_index("ix_legal_thesis_validation_events_precedent", "legal_thesis_validation_events", ["precedent_id"])
    op.create_index("ix_legal_thesis_validation_events_snapshot", "legal_thesis_validation_events", ["snapshot_id"])

    op.create_table(
        "legal_ingestion_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("legal_sources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("lote_codigo", sa.String(100), nullable=False),
        sa.Column("status", sa.String(25), nullable=False, server_default="em_processamento"),
        sa.Column("iniciado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finalizado_em", sa.DateTime(timezone=True)),
        sa.Column("itens_consultados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("itens_importados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicidades", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("descartados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("erro", sa.Text()),
        sa.Column("checkpoint", postgresql.JSONB()),
        sa.Column("executado_por", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_legal_ingestion_runs_source_id", "legal_ingestion_runs", ["source_id"])
    op.create_index("ix_legal_ingestion_runs_lote_codigo", "legal_ingestion_runs", ["lote_codigo"])
    op.create_index("ix_legal_ingestion_runs_status", "legal_ingestion_runs", ["status"])


def downgrade() -> None:
    op.drop_table("legal_ingestion_runs")
    op.drop_table("legal_thesis_validation_events")
    op.drop_table("legal_thesis_relations")
    op.drop_table("legal_thesis_precedents")
    op.drop_table("legal_thesis_versions")
    op.drop_table("legal_theses")
    op.drop_table("legal_precedents")
    op.drop_table("legal_source_snapshots")
    op.drop_table("legal_sources")
