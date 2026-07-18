"""100 — scheduler_heartbeat: heartbeat honesto dos jobs do APScheduler

Contexto (achado nº 1 da auditoria):
    Os jobs do scheduler (captura DJEN, sync DataJud, monitor Diário Oficial,
    alertas de prazo/audiência) rodam in-process no APScheduler SEM registro de
    "última execução". O painel de status-captura derivava saúde do
    `max(created_at)` da tabela de intimações (última linha INSERIDA, não última
    EXECUÇÃO) e ficava verde mesmo com o scheduler morto. Sem heartbeat, uma
    parada silenciosa do scheduler é indetectável.

    Esta tabela grava UMA linha por job (PK = job_name) atualizada por UPSERT ao
    final de cada execução: `last_run_at` (quando REALMENTE rodou) e
    `last_status` ('ok'/'erro'). A Central de Diagnóstico e o status-captura
    passam a reportar defasagem quando `now - last_run_at` excede a cadência
    esperada do job.

ADITIVO PURO e IDEMPOTENTE: CREATE TABLE IF NOT EXISTS; nenhuma tabela existente
é tocada (mesmo padrão raw-SQL de 089_fichas_triagem).

Revision ID: 100_scheduler_heartbeat
Revises: 099_legal_doc_protocolo
Create Date: 2026-07-18
"""
from alembic import op

revision = "100_scheduler_heartbeat"
down_revision = "099_legal_doc_protocolo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduler_heartbeat (
            job_name    VARCHAR(80)  PRIMARY KEY,
            last_run_at TIMESTAMPTZ  NOT NULL,
            last_status VARCHAR(20)  NOT NULL,
            detail      TEXT,
            updated_at  TIMESTAMPTZ  DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scheduler_heartbeat")
