"""067 — cria tabelas dos módulos v4 (Data Room e Banco de Teses v4)

Correção de drift model↔banco detectado pelo test_metadata_bate_com_banco_real:
os routers `data_room_v4` e `teses_v4` (montados em main.py) definem os models
`DataRoomSala` (dataroom_salas) e `TeseJuridica` (teses_juridicas_v4), mas
nenhuma migration criava essas tabelas — os endpoints desses módulos falhariam
em runtime com "relation does not exist". Esta migration cria as duas tabelas
exatamente conforme os models inline (app/routers/data_room_v4.py e
app/routers/teses_v4.py).

ADITIVO PURO e IDEMPOTENTE: CREATE TABLE IF NOT EXISTS; nenhuma tabela existente
é tocada.

Revision ID: 067_v4_dataroom_teses
Revises: 066_ai_log_feedback
Create Date: 2026-07-04
"""
from alembic import op

revision = "067_v4_dataroom_teses"
down_revision = "066_ai_log_feedback"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dataroom_salas (
            id          VARCHAR(36)  PRIMARY KEY,
            nome        VARCHAR(255) NOT NULL,
            descricao   TEXT,
            client_id   VARCHAR(36),
            expira_em   TIMESTAMPTZ,
            publica     BOOLEAN      DEFAULT FALSE,
            created_at  TIMESTAMPTZ  DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS teses_juridicas_v4 (
            id            VARCHAR(36)      PRIMARY KEY,
            titulo        VARCHAR(255)     NOT NULL,
            descricao     TEXT             NOT NULL,
            fundamentacao TEXT             NOT NULL,
            jurisprudencia TEXT,
            taxa_sucesso  DOUBLE PRECISION DEFAULT 0.0,
            area_juridica VARCHAR(50)      NOT NULL,
            tribunal      VARCHAR(100),
            magistrado    VARCHAR(100),
            vencedora     BOOLEAN          DEFAULT FALSE,
            created_at    TIMESTAMPTZ      DEFAULT now()
        )
        """
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS teses_juridicas_v4")
    op.execute("DROP TABLE IF EXISTS dataroom_salas")
