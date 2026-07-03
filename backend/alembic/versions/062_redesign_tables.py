"""057 — redesign: module_help, area_modulos_mapping, document_types_master,
tabela_oab_honorarios

Tabelas de configuração/master data do redesign EJC (auditoria pré-redesign
2026-07-03, seção 3 "Tabelas AUSENTES"):

  1. module_help            — ajuda contextual por módulo (rota do frontend),
                              atualizável sem redeploy (resolve F4/R1).
  2. area_modulos_mapping   — matriz área do direito → módulos/ferramentas,
                              configurável (resolve R6 — hoje hardcoded).
  3. document_types_master  — tipos de documento p/ importação/classificação
                              com schema de campos de extração (resolve B5/R3).
  4. tabela_oab_honorarios  — referência OAB/MG estruturada e VERSIONADA por
                              vigência (resolve R5 — hoje só em RAG). `fonte`
                              é NOT NULL: nenhum item entra sem citação da
                              fonte oficial (regra: nunca inventar valores).

Totalmente IDEMPOTENTE (CREATE TABLE/INDEX IF NOT EXISTS), no padrão das
migrações 052/056. Models correspondentes: app/models/redesign.py.

Revision ID: 057_redesign_tables
Revises: 056_processes_is_principal
Create Date: 2026-07-03
"""
from alembic import op

revision = "062_redesign_tables"
down_revision = "061_client_pii_encriptado"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. module_help — ajuda contextual por módulo ─────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS module_help (
        id             VARCHAR(36)  PRIMARY KEY DEFAULT gen_random_uuid()::text,
        module_key     VARCHAR(60)  NOT NULL,
        titulo         VARCHAR(200) NOT NULL,
        conteudo_md    TEXT         NOT NULL,
        ordem          INTEGER      NOT NULL DEFAULT 0,
        ativo          BOOLEAN      NOT NULL DEFAULT TRUE,
        atualizado_por VARCHAR(36)  REFERENCES users(id) ON DELETE SET NULL,
        created_at     TIMESTAMP WITH TIME ZONE DEFAULT now(),
        updated_at     TIMESTAMP WITH TIME ZONE DEFAULT now()
    );
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_module_help_module_key "
        "ON module_help(module_key);"
    )

    # ── 2. area_modulos_mapping — matriz área → módulos/ferramentas ─────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS area_modulos_mapping (
        id                    VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
        area_juridica         VARCHAR(50) NOT NULL,
        module_key            VARCHAR(60) NOT NULL,
        habilitado            BOOLEAN     NOT NULL DEFAULT TRUE,
        ordem                 INTEGER     NOT NULL DEFAULT 0,
        ferramentas           JSONB,
        workflow_template_id  VARCHAR(36) REFERENCES workflow_templates(id)  ON DELETE SET NULL,
        checklist_template_id VARCHAR(36) REFERENCES checklist_templates(id) ON DELETE SET NULL,
        created_at            TIMESTAMP WITH TIME ZONE DEFAULT now(),
        updated_at            TIMESTAMP WITH TIME ZONE DEFAULT now()
    );
    """)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_area_modulos_area_module "
        "ON area_modulos_mapping(area_juridica, module_key);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_area_modulos_area "
        "ON area_modulos_mapping(area_juridica);"
    )

    # ── 3. document_types_master — tipos de documento (import/classificação) ─
    op.execute("""
    CREATE TABLE IF NOT EXISTS document_types_master (
        id                VARCHAR(36)  PRIMARY KEY DEFAULT gen_random_uuid()::text,
        tipo_key          VARCHAR(50)  NOT NULL UNIQUE,
        nome              VARCHAR(120) NOT NULL,
        descricao         TEXT,
        categoria         VARCHAR(50)  NOT NULL DEFAULT 'outro'
                          CHECK (categoria IN ('juridico','fiscal','administrativo','pessoal','outro')),
        campos_extracao   JSONB,
        extensoes_aceitas JSONB,
        ativo             BOOLEAN      NOT NULL DEFAULT TRUE,
        ordem             INTEGER      NOT NULL DEFAULT 0,
        created_at        TIMESTAMP WITH TIME ZONE DEFAULT now(),
        updated_at        TIMESTAMP WITH TIME ZONE DEFAULT now()
    );
    """)

    # ── 4. tabela_oab_honorarios — referência OAB/MG versionada ─────────────
    # fonte NOT NULL: item só entra citando documento/URL oficial da OAB/MG.
    op.execute("""
    CREATE TABLE IF NOT EXISTS tabela_oab_honorarios (
        id              VARCHAR(36)  PRIMARY KEY DEFAULT gen_random_uuid()::text,
        item_codigo     VARCHAR(30)  NOT NULL,
        descricao       VARCHAR(300) NOT NULL,
        area_juridica   VARCHAR(50),
        valor_minimo    NUMERIC(12,2),
        percentual      NUMERIC(5,2),
        unidade         VARCHAR(30),
        vigencia_inicio DATE,   -- nullable: a edição/vigência da tabela pode ser
                                -- desconhecida na importação; a fonte a documenta
        vigencia_fim    DATE,
        fonte           VARCHAR(300) NOT NULL,
        observacoes     TEXT,
        ativo           BOOLEAN      NOT NULL DEFAULT TRUE,
        created_at      TIMESTAMP WITH TIME ZONE DEFAULT now(),
        updated_at      TIMESTAMP WITH TIME ZONE DEFAULT now()
    );
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tabela_oab_honorarios_area_ativo "
        "ON tabela_oab_honorarios(area_juridica, ativo);"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tabela_oab_honorarios;")
    op.execute("DROP TABLE IF EXISTS document_types_master;")
    op.execute("DROP TABLE IF EXISTS area_modulos_mapping;")
    op.execute("DROP TABLE IF EXISTS module_help;")
