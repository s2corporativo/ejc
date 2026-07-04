"""069 — cria a tabela estilos_advogado (Aprendizado de Estilo por advogado)

Cria o novo model `EstiloAdvogado` (app/models/estilo_advogado.py), registrado em
app/models/__init__.py. Guarda o perfil de redação DESTILADO por advogado (tom,
formalidade, conectivos, estrutura, expressões recorrentes) a partir de peças
aprovadas; o perfil é reinjetado na etapa de redação do pipeline de peças
(opt-in por advogado via flag `ativo` + flag por request). Sem esta migration os
endpoints/serviço do módulo falhariam em runtime com "relation does not exist".

UNIQUE em user_id (um perfil por advogado) materializado como índice único
ux_estilos_advogado_user_id — isso também cobre o index=True do model.

FK user_id → users.id ON DELETE CASCADE: apagar o advogado remove seu perfil.

ADITIVO PURO e IDEMPOTENTE: CREATE TABLE IF NOT EXISTS + CREATE UNIQUE INDEX
IF NOT EXISTS; nenhuma tabela/objeto existente é tocado.

Revision ID: 069_estilos_advogado
Revises: 068_deep_research_jobs
Create Date: 2026-07-04
"""
from alembic import op

revision = "071_estilos_advogado"
down_revision = "070_deep_research_jobs"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS estilos_advogado (
            id            VARCHAR(36) PRIMARY KEY,
            user_id       VARCHAR(36) NOT NULL
                          REFERENCES users(id) ON DELETE CASCADE,
            perfil_estilo TEXT,
            n_amostras    INTEGER     NOT NULL DEFAULT 0,
            ativo         BOOLEAN     NOT NULL DEFAULT true,
            created_at    TIMESTAMPTZ DEFAULT now(),
            updated_at    TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    # UNIQUE (um perfil por advogado) + cobre o index=True do model.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_estilos_advogado_user_id "
        "ON estilos_advogado (user_id)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ux_estilos_advogado_user_id")
    op.execute("DROP TABLE IF EXISTS estilos_advogado")
