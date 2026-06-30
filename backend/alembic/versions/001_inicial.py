"""EJC v3.0 — schema inicial consolidado

Revision ID: 001_inicial
Revises:
Create Date: 2026-06-12

Cria TODAS as tabelas do EJC em uma única migration limpa:
extensão pgvector, 17 tabelas, índices (incl. HNSW para busca semântica).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
import pgvector.sqlalchemy

revision = "001_inicial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Extensão pgvector (imagem pgvector/pgvector:pg16) ──────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── users ───────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("role", sa.Enum(
            "superadmin", "admin", "socio", "advogado", "advogado_auxiliar",
            "estagiario", "secretaria", "financeiro", "cliente_externo",
            name="userrole"), nullable=False, server_default="advogado"),
        sa.Column("phone", sa.String(30)),
        sa.Column("oab_number", sa.String(50)),
        sa.Column("avatar_url", sa.String(500)),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )

    # ── refresh_tokens (revogáveis) ─────────────────────────────────────
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("jti", sa.String(36), nullable=False, unique=True, index=True),
        sa.Column("revoked", sa.Boolean, server_default="false"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── clients ─────────────────────────────────────────────────────────
    op.create_table(
        "clients",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tipo", sa.Enum("PF", "PJ", name="clienttipo"), nullable=False, server_default="PF"),
        sa.Column("status", sa.Enum("lead", "ativo", "inativo", "arquivado", name="clientstatus"),
                  nullable=False, server_default="ativo"),
        sa.Column("nome", sa.String(255), index=True),
        sa.Column("cpf", sa.String(14), index=True),
        sa.Column("data_nascimento", sa.String(10)),
        sa.Column("profissao", sa.String(100)),
        sa.Column("razao_social", sa.String(255), index=True),
        sa.Column("cnpj", sa.String(18), index=True),
        sa.Column("nome_fantasia", sa.String(255)),
        sa.Column("email", sa.String(255)),
        sa.Column("telefone", sa.String(20)),
        sa.Column("whatsapp", sa.String(20)),
        sa.Column("cep", sa.String(9)),
        sa.Column("logradouro", sa.String(255)),
        sa.Column("numero", sa.String(20)),
        sa.Column("complemento", sa.String(100)),
        sa.Column("bairro", sa.String(100)),
        sa.Column("cidade", sa.String(100), server_default="Betim"),
        sa.Column("estado", sa.String(2), server_default="MG"),
        sa.Column("origem", sa.Enum(
            "indicacao", "google", "instagram", "site", "whatsapp", "outro",
            name="clientorigem")),
        sa.Column("observacoes", sa.Text),
        sa.Column("responsavel_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )

    # ── cases ───────────────────────────────────────────────────────────
    op.create_table(
        "cases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("numero_interno", sa.String(20), unique=True, index=True),
        sa.Column("titulo", sa.String(255), nullable=False),
        sa.Column("area", sa.Enum(
            "civil", "trabalhista", "consumidor", "familia", "ambiental",
            "criminal", "previdenciario", "empresarial", "tributario",
            name="casearea"), nullable=False, index=True),
        sa.Column("status", sa.Enum(
            "triagem", "ativo", "suspenso", "acordo", "encerrado", "arquivado",
            name="casestatus"), nullable=False, server_default="triagem", index=True),
        sa.Column("fase", sa.Enum(
            "pre_processual", "conhecimento", "recursal", "execucao", "administrativo",
            name="casefase"), nullable=False, server_default="pre_processual"),
        sa.Column("prioridade", sa.Enum(
            "baixa", "media", "alta", "critica",
            name="caseprioridade"), nullable=False, server_default="media"),
        sa.Column("risco", sa.String(20)),
        sa.Column("numero_processo", sa.String(30), index=True),
        sa.Column("tribunal", sa.String(20)),
        sa.Column("comarca", sa.String(100)),
        sa.Column("vara", sa.String(100)),
        sa.Column("parte_contraria", sa.String(255)),
        sa.Column("valor_causa", sa.Numeric(14, 2)),
        sa.Column("descricao_fatos", sa.Text),
        sa.Column("tese_principal", sa.Text),
        sa.Column("pontos_fortes", sa.Text),
        sa.Column("pontos_fracos", sa.Text),
        sa.Column("observacoes", sa.Text),
        sa.Column("tipo_acao_prescricao", sa.String(100)),
        sa.Column("data_prescricao", sa.DateTime(timezone=True)),
        sa.Column("causa_interruptiva", sa.String(255)),
        sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id"), nullable=False, index=True),
        sa.Column("advogado_responsavel_id", sa.String(36), sa.ForeignKey("users.id"), index=True),
        sa.Column("advogado_auxiliar_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("data_encerramento", sa.DateTime(timezone=True)),
        sa.Column("resultado", sa.String(50)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )

    # ── case_movimentos ─────────────────────────────────────────────────
    op.create_table(
        "case_movimentos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False, index=True),
        sa.Column("tipo", sa.String(30), nullable=False),
        sa.Column("descricao", sa.Text, nullable=False),
        sa.Column("data_evento", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by", sa.String(36)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── deadlines ───────────────────────────────────────────────────────
    op.create_table(
        "deadlines",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("titulo", sa.String(255), nullable=False),
        sa.Column("descricao", sa.Text),
        sa.Column("tipo", sa.Enum(
            "processual", "administrativo", "interno", "audiencia", "prescricao",
            name="deadlinetipo"), nullable=False, server_default="processual"),
        sa.Column("prioridade", sa.Enum(
            "baixa", "media", "alta", "critica",
            name="deadlineprioridade"), nullable=False, server_default="media"),
        sa.Column("status", sa.Enum(
            "pendente", "concluido", "vencido", "cancelado",
            name="deadlinestatus"), nullable=False, server_default="pendente", index=True),
        sa.Column("data_prazo", sa.Date, nullable=False, index=True),
        sa.Column("data_intimacao", sa.Date),
        sa.Column("data_conclusao", sa.DateTime(timezone=True)),
        sa.Column("base_legal", sa.String(255)),
        sa.Column("ciencia_confirmada", sa.Boolean, server_default="false"),
        sa.Column("ciencia_confirmada_em", sa.DateTime(timezone=True)),
        sa.Column("ciencia_confirmada_por", sa.String(36)),
        sa.Column("alerta_7d_enviado", sa.Boolean, server_default="false"),
        sa.Column("alerta_3d_enviado", sa.Boolean, server_default="false"),
        sa.Column("alerta_1d_enviado", sa.Boolean, server_default="false"),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), index=True),
        sa.Column("responsavel_id", sa.String(36), sa.ForeignKey("users.id"), index=True),
        sa.Column("observacoes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )

    # ── documents ───────────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("titulo", sa.String(255), nullable=False),
        sa.Column("descricao", sa.Text),
        sa.Column("tipo", sa.String(50)),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("filepath", sa.String(500), nullable=False),
        sa.Column("mimetype", sa.String(100)),
        sa.Column("size_bytes", sa.Integer),
        sa.Column("ocr_text", sa.Text),
        sa.Column("confidencialidade", sa.Enum(
            "normal", "interno", "restrito", "confidencial", "segredo_justica",
            name="docconfidencialidade"), nullable=False, server_default="normal", index=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), index=True),
        sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id"), index=True),
        sa.Column("uploaded_by", sa.String(36)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )

    # ── legal_docs (HITL) ───────────────────────────────────────────────
    op.create_table(
        "legal_docs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("titulo", sa.String(255), nullable=False),
        sa.Column("tipo_peca", sa.Enum(
            "peticao_inicial", "contestacao", "recurso", "contrarrazoes",
            "parecer", "contrato", "procuracao", "notificacao_extrajudicial",
            "defesa_ambiental", "outro", name="pecatipo"), nullable=False),
        sa.Column("status", sa.Enum(
            "rascunho", "em_revisao", "corrigida", "aprovada", "final", "protocolada",
            name="pecastatus"), nullable=False, server_default="rascunho", index=True),
        sa.Column("conteudo", sa.Text, nullable=False),
        sa.Column("versao", sa.Integer, server_default="1"),
        sa.Column("ai_generated", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("human_reviewed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("revisor_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("revisado_em", sa.DateTime(timezone=True)),
        sa.Column("notas_revisao", sa.Text),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), index=True),
        sa.Column("created_by", sa.String(36)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )

    # ── fees + fee_payments ─────────────────────────────────────────────
    op.create_table(
        "fees",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tipo", sa.Enum(
            "fixo", "exito", "misto", "por_hora", "custas_despesas",
            name="feetipo"), nullable=False, server_default="fixo"),
        sa.Column("status", sa.Enum(
            "pendente", "pago", "atrasado", "cancelado",
            name="feestatus"), nullable=False, server_default="pendente", index=True),
        sa.Column("descricao", sa.String(255), nullable=False),
        sa.Column("valor", sa.Numeric(14, 2)),
        sa.Column("percentual_exito", sa.Numeric(5, 2)),
        sa.Column("data_vencimento", sa.Date, index=True),
        sa.Column("data_pagamento", sa.Date),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), index=True),
        sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id"), nullable=False, index=True),
        sa.Column("observacoes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "fee_payments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("fee_id", sa.String(36), sa.ForeignKey("fees.id"), nullable=False, index=True),
        sa.Column("valor", sa.Numeric(14, 2), nullable=False),
        sa.Column("data_pagamento", sa.Date, nullable=False),
        sa.Column("forma", sa.String(30)),
        sa.Column("comprovante_doc_id", sa.String(36)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── environmental_cases ─────────────────────────────────────────────
    op.create_table(
        "environmental_cases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"),
                  nullable=False, unique=True, index=True),
        sa.Column("orgao_autuador", sa.Enum(
            "IBAMA", "IEF_MG", "SEMAD_MG", "FEAM_MG", "IGAM_MG", "ICMBio",
            "municipal", "outro", name="orgaoautuador"), nullable=False),
        sa.Column("numero_auto", sa.String(50), nullable=False, index=True),
        sa.Column("data_lavratura", sa.Date),
        sa.Column("data_ciencia", sa.Date),
        sa.Column("especie_infracao", sa.Text),
        sa.Column("dispositivo_infringido", sa.String(255)),
        sa.Column("valor_multa", sa.Numeric(14, 2)),
        sa.Column("prazo_defesa_dias", sa.Numeric(3, 0), server_default="20"),
        sa.Column("data_prazo_defesa", sa.Date, index=True),
        sa.Column("status_defesa", sa.Enum(
            "aguardando_ciencia", "prazo_correndo", "elaborando", "protocolada",
            "julgada", "recurso", "conversao_multa", "encerrado",
            name="statusdefesa"), nullable=False,
            server_default="aguardando_ciencia", index=True),
        sa.Column("conversao_solicitada", sa.DateTime(timezone=True)),
        sa.Column("valor_multa_convertida", sa.Numeric(14, 2)),
        sa.Column("servico_ambiental", sa.Text),
        sa.Column("area_degradada_ha", sa.Numeric(10, 2)),
        sa.Column("bioma", sa.String(50)),
        sa.Column("coordenadas", sa.String(100)),
        sa.Column("embargo", sa.String(20)),
        sa.Column("resultado_julgamento", sa.Text),
        sa.Column("observacoes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )

    # ── audit_logs (imutável) ───────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), index=True),
        sa.Column("user_role", sa.String(30)),
        sa.Column("ip", sa.String(45)),
        sa.Column("acao", sa.String(30), nullable=False, index=True),
        sa.Column("entidade", sa.String(50), nullable=False, index=True),
        sa.Column("registro_id", sa.String(36), index=True),
        sa.Column("dados_antes", JSONB),
        sa.Column("dados_depois", JSONB),
        sa.Column("detalhes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), index=True),
    )

    # ── ai_logs ─────────────────────────────────────────────────────────
    op.create_table(
        "ai_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"),
                  nullable=False, index=True),
        sa.Column("case_id", sa.String(36), index=True),
        sa.Column("tipo_uso", sa.Enum(
            "analise_caso", "redacao_peca", "consulta_rag", "resumo_documento",
            "outro", name="aitipouso"), nullable=False),
        sa.Column("modelo", sa.String(50), nullable=False),
        sa.Column("prompt_sanitizado", sa.Text, nullable=False),
        sa.Column("pii_removida", sa.Boolean, server_default="false"),
        sa.Column("resposta", sa.Text),
        sa.Column("fontes_rag", sa.Text),
        sa.Column("tokens_input", sa.Integer),
        sa.Column("tokens_output", sa.Integer),
        sa.Column("status_hitl", sa.Enum(
            "gerado", "revisado", "aplicado", "descartado",
            name="aistatushitl"), nullable=False,
            server_default="gerado", index=True),
        sa.Column("revisado_por", sa.String(36)),
        sa.Column("revisado_em", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), index=True),
    )

    # ── notifications ───────────────────────────────────────────────────
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"),
                  nullable=False, index=True),
        sa.Column("titulo", sa.String(255), nullable=False),
        sa.Column("mensagem", sa.Text, nullable=False),
        sa.Column("tipo", sa.String(30), nullable=False),
        sa.Column("link", sa.String(255)),
        sa.Column("lida", sa.Boolean, server_default="false", index=True),
        sa.Column("lida_em", sa.DateTime(timezone=True)),
        sa.Column("whatsapp_enviado", sa.Boolean, server_default="false"),
        sa.Column("email_enviado", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), index=True),
    )

    # ── feriados ────────────────────────────────────────────────────────
    op.create_table(
        "feriados",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("data", sa.Date, nullable=False, unique=True, index=True),
        sa.Column("nome", sa.String(100), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("movel", sa.Boolean, server_default="false"),
    )

    # ── procuracoes ─────────────────────────────────────────────────────
    op.create_table(
        "procuracoes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id"),
                  nullable=False, index=True),
        sa.Column("tipo_poderes", sa.String(30), nullable=False,
                  server_default="ad_judicia"),
        sa.Column("poderes_especiais", sa.Text),
        sa.Column("permite_substabelecimento", sa.Boolean, server_default="true"),
        sa.Column("data_outorga", sa.Date, nullable=False),
        sa.Column("data_validade", sa.Date, index=True),
        sa.Column("foro_restrito", sa.String(100)),
        sa.Column("document_id", sa.String(36)),
        sa.Column("alerta_30d_enviado", sa.Boolean, server_default="false"),
        sa.Column("revogada", sa.Boolean, server_default="false"),
        sa.Column("revogada_em", sa.Date),
        sa.Column("observacoes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )

    # ── knowledge_docs + knowledge_chunks (RAG) ─────────────────────────
    op.create_table(
        "knowledge_docs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("titulo", sa.String(500), nullable=False),
        sa.Column("categoria", sa.String(50), nullable=False, index=True),
        sa.Column("fonte", sa.String(255)),
        sa.Column("tribunal", sa.String(20)),
        sa.Column("extra", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("doc_id", sa.String(36),
                  sa.ForeignKey("knowledge_docs.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("conteudo", sa.Text, nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(768)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Índice HNSW para busca semântica rápida (cosine)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_embedding
        ON knowledge_chunks
        USING hnsw (embedding vector_cosine_ops)
    """)

    # Índice GIN para busca textual nos chunks (fallback sem embeddings)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_conteudo_trgm
        ON knowledge_chunks USING gin (to_tsvector('portuguese', conteudo))
    """)


def downgrade() -> None:
    for t in [
        "knowledge_chunks", "knowledge_docs", "procuracoes", "feriados",
        "notifications", "ai_logs", "audit_logs", "environmental_cases",
        "fee_payments", "fees", "legal_docs", "documents", "deadlines",
        "case_movimentos", "cases", "clients", "refresh_tokens", "users",
    ]:
        op.drop_table(t)
    for e in [
        "userrole", "clienttipo", "clientstatus", "clientorigem",
        "casearea", "casestatus", "casefase", "caseprioridade",
        "deadlinetipo", "deadlinestatus", "deadlineprioridade",
        "docconfidencialidade", "pecatipo", "pecastatus",
        "feetipo", "feestatus", "orgaoautuador", "statusdefesa",
        "aitipouso", "aistatushitl",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {e}")
