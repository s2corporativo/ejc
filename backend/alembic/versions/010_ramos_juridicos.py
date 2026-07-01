"""010 — tabelas especializadas por ramo jurídico

Cria 6 tabelas satélite (1-1 com cases): empresarial, cível, penal,
trabalhista, administrativo e bancário. Aditiva e reversível.

Revision ID: 010_ramos_juridicos
Revises: 009_rag_trgm_index
"""
from alembic import op
import sqlalchemy as sa

revision = "010_ramos_juridicos"
down_revision = "009_rag_trgm_index"
branch_labels = None
depends_on = None

ENUM_OPTS = {"schema": None, "create_type": True}


def upgrade() -> None:
    # ── 1. EMPRESARIAL ────────────────────────────────────────────────────────
    op.create_table("empresarial_cases",
        sa.Column("id",      sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("tipo",   sa.String(40), nullable=False, server_default="contrato_empresarial"),
        sa.Column("status", sa.String(30), nullable=False, server_default="diagnostico"),
        sa.Column("cnpj_empresa",           sa.String(18),   nullable=True),
        sa.Column("tipo_societario",         sa.String(50),   nullable=True),
        sa.Column("capital_social",          sa.Numeric(16,2), nullable=True),
        sa.Column("nire",                    sa.String(20),   nullable=True),
        sa.Column("data_distribuicao_rj",    sa.Date(), nullable=True),
        sa.Column("data_aprovacao_plano",    sa.Date(), nullable=True),
        sa.Column("valor_passivo_total",     sa.Numeric(16,2), nullable=True),
        sa.Column("numero_credores",         sa.Integer(), nullable=True),
        sa.Column("ato_concentracao_notificado", sa.Boolean(), default=False),
        sa.Column("data_notificacao_cade",   sa.Date(), nullable=True),
        sa.Column("valor_operacao",          sa.Numeric(16,2), nullable=True),
        sa.Column("numero_processo_inpi",    sa.String(30), nullable=True),
        sa.Column("tipo_pi",                 sa.String(30), nullable=True),
        sa.Column("num_reclamacoes_trabalhistas", sa.Integer(), nullable=True),
        sa.Column("valor_passivo_trabalhista", sa.Numeric(16,2), nullable=True),
        sa.Column("regime_tributario",       sa.String(30), nullable=True),
        sa.Column("debito_fiscal_total",     sa.Numeric(16,2), nullable=True),
        sa.Column("em_parcelamento",         sa.Boolean(), default=False),
        sa.Column("data_encerramento_estimado", sa.Date(), nullable=True),
        sa.Column("honorarios_tipo",         sa.String(30), nullable=True),
        sa.Column("observacoes",             sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_empresarial_case_id", "empresarial_cases", ["case_id"], unique=True)

    # ── 2. CÍVEL ──────────────────────────────────────────────────────────────
    op.create_table("civel_cases",
        sa.Column("id",      sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("tipo",   sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pre_processual"),
        sa.Column("valor_causa",         sa.Numeric(14,2), nullable=True),
        sa.Column("competencia",         sa.String(60),    nullable=True),
        sa.Column("polo_ativo",          sa.String(20),    nullable=True),
        sa.Column("tutela_urgencia",     sa.Boolean(), default=False),
        sa.Column("data_tutela",         sa.Date(), nullable=True),
        sa.Column("regime_bens",         sa.String(40), nullable=True),
        sa.Column("filhos_menores",      sa.Integer(), default=0),
        sa.Column("guarda_tipo",         sa.String(30), nullable=True),
        sa.Column("alimentos_valor",     sa.Numeric(12,2), nullable=True),
        sa.Column("alimentos_percentual",sa.Numeric(5,2),  nullable=True),
        sa.Column("data_separacao",      sa.Date(), nullable=True),
        sa.Column("tipo_imovel",         sa.String(40), nullable=True),
        sa.Column("matricula_imovel",    sa.String(30), nullable=True),
        sa.Column("area_m2",             sa.Numeric(10,2), nullable=True),
        sa.Column("valor_imovel",        sa.Numeric(14,2), nullable=True),
        sa.Column("data_posse",          sa.Date(), nullable=True),
        sa.Column("anos_posse",          sa.Numeric(4,1),  nullable=True),
        sa.Column("fornecedor",          sa.String(255),   nullable=True),
        sa.Column("numero_contrato",     sa.String(60),    nullable=True),
        sa.Column("valor_pedido",        sa.Numeric(12,2), nullable=True),
        sa.Column("dano_moral_pedido",   sa.Numeric(12,2), nullable=True),
        sa.Column("data_fato",           sa.Date(), nullable=True),
        sa.Column("protocolo_procon",    sa.String(60), nullable=True),
        sa.Column("data_citacao",        sa.Date(), nullable=True),
        sa.Column("data_contestacao",    sa.Date(), nullable=True),
        sa.Column("data_audiencia",      sa.Date(), nullable=True),
        sa.Column("resultado",           sa.Text(), nullable=True),
        sa.Column("observacoes",         sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_civel_case_id", "civel_cases", ["case_id"], unique=True)

    # ── 3. PENAL ──────────────────────────────────────────────────────────────
    op.create_table("penal_cases",
        sa.Column("id",      sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("tipo_crime", sa.String(40), nullable=False),
        sa.Column("fase",       sa.String(40), nullable=False, server_default="investigacao"),
        sa.Column("numero_bo",  sa.String(40), nullable=True),
        sa.Column("numero_ip",  sa.String(40), nullable=True),
        sa.Column("delegacia",  sa.String(100), nullable=True),
        sa.Column("data_fato",  sa.Date(), nullable=True),
        sa.Column("local_fato", sa.String(255), nullable=True),
        sa.Column("polo",       sa.String(20), nullable=True),
        sa.Column("preso",      sa.Boolean(), default=False),
        sa.Column("tipo_prisao", sa.String(30), nullable=True),
        sa.Column("data_prisao", sa.Date(), nullable=True),
        sa.Column("data_alvara", sa.Date(), nullable=True),
        sa.Column("fianca_valor",sa.Numeric(14,2), nullable=True),
        sa.Column("artigo_imputado", sa.String(100), nullable=True),
        sa.Column("pena_min_anos",   sa.Numeric(3,1), nullable=True),
        sa.Column("pena_max_anos",   sa.Numeric(3,1), nullable=True),
        sa.Column("pena_aplicada",   sa.String(60), nullable=True),
        sa.Column("sursis",          sa.Boolean(), default=False),
        sa.Column("pena_alternativa",sa.Boolean(), default=False),
        sa.Column("anpp_proposto",   sa.Boolean(), default=False),
        sa.Column("anpp_aceito",     sa.Boolean(), nullable=True),
        sa.Column("anpp_condicoes",  sa.Text(), nullable=True),
        sa.Column("data_denuncia",   sa.Date(), nullable=True),
        sa.Column("prazo_resposta_acusacao", sa.Date(), nullable=True),
        sa.Column("data_audiencia",  sa.Date(), nullable=True),
        sa.Column("resultado",       sa.Text(), nullable=True),
        sa.Column("observacoes",     sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_penal_case_id", "penal_cases", ["case_id"], unique=True)
    op.create_index("ix_penal_fase", "penal_cases", ["fase"])

    # ── 4. TRABALHISTA ────────────────────────────────────────────────────────
    op.create_table("trabalhista_cases",
        sa.Column("id",      sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("tipo", sa.String(40), nullable=False),
        sa.Column("fase", sa.String(40), nullable=False, server_default="pre_processual"),
        sa.Column("polo", sa.String(20), nullable=True),
        sa.Column("salario_base",         sa.Numeric(12,2), nullable=True),
        sa.Column("data_admissao",         sa.Date(), nullable=True),
        sa.Column("data_demissao",         sa.Date(), nullable=True),
        sa.Column("tipo_rescisao",         sa.String(40), nullable=True),
        sa.Column("cargo",                 sa.String(100), nullable=True),
        sa.Column("cbo",                   sa.String(10),  nullable=True),
        sa.Column("regime_contratacao",    sa.String(30),  nullable=True),
        sa.Column("valor_causa_estimado",  sa.Numeric(14,2), nullable=True),
        sa.Column("horas_extras_semana",   sa.Numeric(4,1), nullable=True),
        sa.Column("adicional_percentual",  sa.Numeric(5,2), nullable=True),
        sa.Column("data_acidente",         sa.Date(), nullable=True),
        sa.Column("cat_emitida",           sa.Boolean(), nullable=True),
        sa.Column("cid",                   sa.String(10), nullable=True),
        sa.Column("afastamento_dias",      sa.Integer(), nullable=True),
        sa.Column("sequela_permanente",    sa.Boolean(), default=False),
        sa.Column("dano_moral_pedido",     sa.Numeric(14,2), nullable=True),
        sa.Column("dano_moral_concedido",  sa.Numeric(14,2), nullable=True),
        sa.Column("deposito_recursal",     sa.Numeric(12,2), nullable=True),
        sa.Column("valor_acordo",          sa.Numeric(14,2), nullable=True),
        sa.Column("valor_condenacao",      sa.Numeric(14,2), nullable=True),
        sa.Column("prazo_recurso_ordinario", sa.Date(), nullable=True),
        sa.Column("data_audiencia_inaugural", sa.Date(), nullable=True),
        sa.Column("resultado",   sa.Text(), nullable=True),
        sa.Column("observacoes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_trabalhista_case_id", "trabalhista_cases", ["case_id"], unique=True)

    # ── 5. ADMINISTRATIVO ─────────────────────────────────────────────────────
    op.create_table("admin_cases",
        sa.Column("id",      sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("tipo",   sa.String(50), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="prazo_recurso"),
        sa.Column("numero_auto_infracao",  sa.String(50), nullable=True),
        sa.Column("orgao_autuador",        sa.String(100), nullable=True),
        sa.Column("data_infracao",         sa.Date(), nullable=True),
        sa.Column("data_notificacao",      sa.Date(), nullable=True),
        sa.Column("codigo_infracao",       sa.String(20), nullable=True),
        sa.Column("valor_multa_original",  sa.Numeric(12,2), nullable=True),
        sa.Column("valor_com_desconto",    sa.Numeric(12,2), nullable=True),
        sa.Column("pontuacao_cnh",         sa.Integer(), nullable=True),
        sa.Column("suspensao_cnh",         sa.Boolean(), default=False),
        sa.Column("prazo_recurso_1a_inst", sa.Date(), nullable=True),
        sa.Column("prazo_recurso_2a_inst", sa.Date(), nullable=True),
        sa.Column("protocolo_recurso",     sa.String(60), nullable=True),
        sa.Column("data_ato_coator",       sa.Date(), nullable=True),
        sa.Column("prazo_ms",              sa.Date(), nullable=True),
        sa.Column("autoridade_coatora",    sa.String(100), nullable=True),
        sa.Column("numero_pad",            sa.String(40), nullable=True),
        sa.Column("cargo_servidor",        sa.String(100), nullable=True),
        sa.Column("penalidade_imputada",   sa.String(60), nullable=True),
        sa.Column("resultado",   sa.Text(), nullable=True),
        sa.Column("observacoes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_admin_case_id", "admin_cases", ["case_id"], unique=True)

    # ── 6. BANCÁRIO ───────────────────────────────────────────────────────────
    op.create_table("bancario_cases",
        sa.Column("id",      sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("tipo",   sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="analise_contrato"),
        sa.Column("instituicao_financeira",  sa.String(100), nullable=True),
        sa.Column("numero_contrato",         sa.String(60),  nullable=True),
        sa.Column("modalidade_credito",      sa.String(50),  nullable=True),
        sa.Column("data_contrato",           sa.Date(), nullable=True),
        sa.Column("valor_contratado",        sa.Numeric(14,2), nullable=True),
        sa.Column("valor_pago",              sa.Numeric(14,2), nullable=True),
        sa.Column("taxa_mensal_contratada",  sa.Numeric(7,4), nullable=True),
        sa.Column("taxa_mensal_legal",       sa.Numeric(7,4), nullable=True),
        sa.Column("cet_contratado",          sa.Numeric(7,4), nullable=True),
        sa.Column("spread_excessivo",        sa.Boolean(), default=False),
        sa.Column("saldo_devedor_declarado", sa.Numeric(14,2), nullable=True),
        sa.Column("saldo_devedor_revisado",  sa.Numeric(14,2), nullable=True),
        sa.Column("valor_cobrado_indevido",  sa.Numeric(14,2), nullable=True),
        sa.Column("negativado",              sa.Boolean(), default=False),
        sa.Column("orgao_negativacao",       sa.String(40),  nullable=True),
        sa.Column("data_negativacao",        sa.Date(), nullable=True),
        sa.Column("valor_negativado",        sa.Numeric(12,2), nullable=True),
        sa.Column("dano_moral_pedido",       sa.Numeric(12,2), nullable=True),
        sa.Column("superendividamento",      sa.Boolean(), default=False),
        sa.Column("renda_mensal",            sa.Numeric(12,2), nullable=True),
        sa.Column("total_dividas",           sa.Numeric(14,2), nullable=True),
        sa.Column("minimo_existencial",      sa.Boolean(), default=False),
        sa.Column("data_notificacao_ba",     sa.Date(), nullable=True),
        sa.Column("prazo_purga",             sa.Date(), nullable=True),
        sa.Column("bem_garantia",            sa.String(255), nullable=True),
        sa.Column("resultado",   sa.Text(), nullable=True),
        sa.Column("observacoes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_bancario_case_id", "bancario_cases", ["case_id"], unique=True)


def downgrade() -> None:
    for tbl in ["bancario_cases","admin_cases","trabalhista_cases",
                "penal_cases","civel_cases","empresarial_cases"]:
        op.drop_table(tbl)
