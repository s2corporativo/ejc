"""052 — workflow BPM: cria workflow_templates, workflow_etapas, case_workflows, workflow_historico

O model app/models/workflow.py existia mas as tabelas nunca foram migradas.
O router workflow (montado na fase1) falhava com UndefinedTableError. Esta
migration cria o schema BPM completo + enum workflowstatus.

Revision ID: 052_workflow_tables
Revises: 051_ejc_skills
Create Date: 2026-06-27
"""
from alembic import op

revision = "052_workflow_tables"
down_revision = "051_ejc_skills"
branch_labels = None
depends_on = None


def upgrade():
    # Enum de status (idempotente — não falha se já existir)
    op.execute("""
    DO $$ BEGIN
        CREATE TYPE workflowstatus AS ENUM ('ativo','pausado','concluido','cancelado');
    EXCEPTION WHEN duplicate_object THEN null;
    END $$;
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS workflow_templates (
        id            VARCHAR(36)  PRIMARY KEY DEFAULT gen_random_uuid()::text,
        nome          VARCHAR(200) NOT NULL,
        descricao     TEXT,
        area_juridica VARCHAR(60),
        is_default    BOOLEAN      NOT NULL DEFAULT FALSE,
        created_by    VARCHAR(36)  REFERENCES users(id) ON DELETE SET NULL,
        created_at    TIMESTAMP WITH TIME ZONE DEFAULT now(),
        updated_at    TIMESTAMP WITH TIME ZONE DEFAULT now(),
        deleted_at    TIMESTAMP WITH TIME ZONE
    );
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS workflow_etapas (
        id              VARCHAR(36)  PRIMARY KEY DEFAULT gen_random_uuid()::text,
        template_id     VARCHAR(36)  NOT NULL REFERENCES workflow_templates(id) ON DELETE CASCADE,
        nome            VARCHAR(100) NOT NULL,
        descricao       TEXT,
        ordem           INTEGER      NOT NULL DEFAULT 0,
        sla_dias_uteis  INTEGER,
        cor             VARCHAR(20),
        obrigatoria     BOOLEAN      NOT NULL DEFAULT TRUE,
        acao_automatica VARCHAR(50)
    );
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS case_workflows (
        id             VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
        case_id        VARCHAR(36) NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
        template_id    VARCHAR(36) NOT NULL REFERENCES workflow_templates(id) ON DELETE RESTRICT,
        etapa_atual_id VARCHAR(36) REFERENCES workflow_etapas(id) ON DELETE SET NULL,
        status         workflowstatus NOT NULL DEFAULT 'ativo',
        iniciado_em    TIMESTAMP WITH TIME ZONE DEFAULT now(),
        concluido_em   TIMESTAMP WITH TIME ZONE,
        created_by     VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL
    );
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS workflow_historico (
        id               VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
        case_workflow_id VARCHAR(36) NOT NULL REFERENCES case_workflows(id) ON DELETE CASCADE,
        etapa_id         VARCHAR(36) REFERENCES workflow_etapas(id) ON DELETE SET NULL,
        iniciado_em      TIMESTAMP WITH TIME ZONE DEFAULT now(),
        concluido_em     TIMESTAMP WITH TIME ZONE,
        responsavel_id   VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
        observacao       TEXT,
        sla_respeitado   BOOLEAN
    );
    """)

    op.execute("CREATE INDEX IF NOT EXISTS ix_case_workflows_case_id ON case_workflows(case_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_workflow_etapas_template_id ON workflow_etapas(template_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_workflow_historico_cwid ON workflow_historico(case_workflow_id);")


def downgrade():
    op.execute("DROP TABLE IF EXISTS workflow_historico;")
    op.execute("DROP TABLE IF EXISTS case_workflows;")
    op.execute("DROP TABLE IF EXISTS workflow_etapas;")
    op.execute("DROP TABLE IF EXISTS workflow_templates;")
    op.execute("DROP TYPE IF EXISTS workflowstatus;")
