"""068 — cria a tabela deep_research_jobs (Deep Research jurídica persistida)

Cria o novo model `DeepResearchJob` (app/models/deep_research.py), registrado em
app/models/__init__.py. É o job PERSISTIDO da Deep Research multi-etapa que roda
em background (fastapi.BackgroundTasks) enquanto o cliente faz polling do status
/progresso. Sem esta migration os endpoints do módulo (app/routers/deep_research.py)
falhariam em runtime com "relation does not exist".

Cria também o enum PG `deepresearchstatus` (em_andamento/concluido/erro), que o
model referencia via SAEnum(name="deepresearchstatus").

case_id é String(36) SEM FK física (espelha AILog.case_id): consultas avulsas de
triagem podem não estar vinculadas a um caso — FK lógica, coerente com o padrão
do projeto.

ADITIVO PURO e IDEMPOTENTE: CREATE TYPE condicional + CREATE TABLE IF NOT EXISTS;
nenhuma tabela/tipo existente é tocado.

Revision ID: 068_deep_research_jobs
Revises: 067_v4_dataroom_teses
Create Date: 2026-07-04
"""
from alembic import op

revision = "070_deep_research_jobs"
down_revision = "069_api_keys"
branch_labels = None
depends_on = None


def upgrade():
    # Enum PG idempotente (CREATE TYPE não suporta IF NOT EXISTS diretamente).
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_type WHERE typname = 'deepresearchstatus'
            ) THEN
                CREATE TYPE deepresearchstatus AS ENUM (
                    'em_andamento', 'concluido', 'erro'
                );
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS deep_research_jobs (
            id                 VARCHAR(36)  PRIMARY KEY,
            user_id            VARCHAR(36)  NOT NULL REFERENCES users(id),
            case_id            VARCHAR(36),
            pergunta           TEXT         NOT NULL,
            tese               TEXT,
            nivel_inteligencia VARCHAR(20)  NOT NULL DEFAULT 'alto',
            status             deepresearchstatus NOT NULL DEFAULT 'em_andamento',
            progresso          INTEGER      NOT NULL DEFAULT 0,
            etapa_atual        VARCHAR(120),
            etapas_json        TEXT,
            resultado_json     TEXT,
            erro_mensagem      TEXT,
            total_subquestoes  INTEGER      NOT NULL DEFAULT 0,
            total_chamadas_ia  INTEGER      NOT NULL DEFAULT 0,
            created_at         TIMESTAMPTZ  DEFAULT now(),
            updated_at         TIMESTAMPTZ  DEFAULT now(),
            concluido_em       TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_deep_research_jobs_user_id "
        "ON deep_research_jobs (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_deep_research_jobs_case_id "
        "ON deep_research_jobs (case_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_deep_research_jobs_status "
        "ON deep_research_jobs (status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_deep_research_jobs_created_at "
        "ON deep_research_jobs (created_at)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS deep_research_jobs")
    op.execute("DROP TYPE IF EXISTS deepresearchstatus")
