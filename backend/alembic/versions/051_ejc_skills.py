"""051 — ejc_skills: tabela de skills de IA parametrizadas

Revision ID: 051_ejc_skills
Revises: 050_novos_modulos
Create Date: 2026-06-27
"""
from alembic import op

revision = "051_ejc_skills"
down_revision = "050_novos_modulos"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE IF NOT EXISTS ejc_skills (
        id                    VARCHAR(36)  PRIMARY KEY DEFAULT gen_random_uuid()::text,
        name                  VARCHAR(100) NOT NULL UNIQUE,
        display_name          VARCHAR(200) NOT NULL,
        description           TEXT,
        system_prompt         TEXT         NOT NULL,
        engine                VARCHAR(20)  NOT NULL DEFAULT 'groq'
                                CHECK (engine IN ('anthropic','groq','ollama')),
        area                  VARCHAR(50)  NOT NULL DEFAULT 'juridico',
        active                BOOLEAN      NOT NULL DEFAULT TRUE,
        requires_case         BOOLEAN      NOT NULL DEFAULT FALSE,
        requires_human_review BOOLEAN      NOT NULL DEFAULT TRUE,
        oab_restricted        BOOLEAN      NOT NULL DEFAULT FALSE,
        version               INTEGER      NOT NULL DEFAULT 1,
        created_at            TIMESTAMP WITH TIME ZONE DEFAULT now(),
        updated_at            TIMESTAMP WITH TIME ZONE DEFAULT now()
    );
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS ejc_skills;")
