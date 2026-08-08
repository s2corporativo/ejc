"""FK legal_chat_messages.ai_log_id ganha ON DELETE SET NULL (F1a).

docs/PLANO_FUSAO_CASO_UNICO.md §4.3-6 — achado confirmado no código: essa é a
ÚNICA foreign key do sistema inteiro apontando para `ai_logs.id`
(`121_sala_juridica_chat.py`, sem `ondelete`). `services/scheduler.py::
_purgar_logs_ia` roda `DELETE FROM ai_logs WHERE created_at < :lim` cru — na
primeira mensagem da Sala Jurídica com mais de RETENCAO_IA_ANOS (default 2),
esse DELETE bate na FK sem ON DELETE, levanta IntegrityError, cai no
`except Exception` do job e a purga LGPD de logs de IA passa a falhar em
SILÊNCIO a partir dali (só um `logger.error`, sem alerta).

SET NULL é a política certa aqui: a mensagem da Sala não perde conteúdo
quando o log de auditoria da IA expira por retenção — só perde o vínculo de
rastreabilidade com aquele log específico, que já cumpriu sua janela legal.

O nome do constraint nasceu implícito (`sa.ForeignKey("ai_logs.id")` sem
`name=` em `121_sala_juridica_chat.py`) — o Postgres o batizou sozinho na
criação da tabela. Em vez de arriscar o nome padrão (`<tabela>_<coluna>_fkey`,
que nem sempre é literal), a migration descobre o nome real em
`information_schema` antes de derrubar o constraint — não quebra se algum dia
divergir.

Revision ID: 133_ai_log_fk_ondelete_set_null
Revises: 132_processo_eletronico_mni
Create Date: 2026-08-08
"""
from alembic import op
from sqlalchemy import text

revision = "133_ai_log_fk_ondelete_set_null"
down_revision = "132_processo_eletronico_mni"
branch_labels = None
depends_on = None

_TABELA = "legal_chat_messages"
_COLUNA = "ai_log_id"
_REFERENCIADA = "ai_logs"


def _nome_constraint(referenciada: str) -> str:
    conn = op.get_bind()
    row = conn.execute(
        text(
            """
            SELECT tc.constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON tc.constraint_name = ccu.constraint_name
             AND tc.table_schema = ccu.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_name = :tabela
              AND kcu.column_name = :coluna
              AND ccu.table_name = :referenciada
            """
        ),
        {"tabela": _TABELA, "coluna": _COLUNA, "referenciada": referenciada},
    ).fetchone()
    if row is None:
        raise RuntimeError(
            f"FK de {_TABELA}.{_COLUNA} -> {referenciada}.id não encontrada — "
            "schema divergente do esperado, corrija a migration antes de aplicar."
        )
    return row[0]


def upgrade() -> None:
    nome = _nome_constraint(_REFERENCIADA)
    op.drop_constraint(nome, _TABELA, type_="foreignkey")
    op.create_foreign_key(
        nome, _TABELA, _REFERENCIADA, [_COLUNA], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    nome = _nome_constraint(_REFERENCIADA)
    op.drop_constraint(nome, _TABELA, type_="foreignkey")
    op.create_foreign_key(nome, _TABELA, _REFERENCIADA, [_COLUNA], ["id"])
