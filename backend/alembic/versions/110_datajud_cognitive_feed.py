"""110 — DataJud como fonte informativa, nunca prazo fatal automático.

Revision ID: 110_datajud_cognitive_feed
Revises: 109_rag_scope_cliente
Create Date: 2026-07-19
"""
from alembic import op

revision = "110_datajud_cognitive_feed"
down_revision = "109_rag_scope_cliente"
branch_labels = None
depends_on = None

_MARCADOR = "[MIG110_DATAJUD_INFORMATIVO]"
_MENSAGEM = (
    f"{_MARCADOR} Cancelado automaticamente: DataJud fornece metadados e não "
    "comprova intimação, publicação ou termo inicial. Recrie/confirme o prazo "
    "somente após conferência no DJEN ou sistema judicial autenticado."
)


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE deadlines
           SET origem = 'datajud',
               confirmado = FALSE,
               status = 'cancelado',
               observacoes = CONCAT_WS(
                   E'\n',
                   NULLIF(observacoes, ''),
                   '{_MENSAGEM}'
               ),
               updated_at = NOW()
         WHERE status = 'pendente'
           AND COALESCE(ciencia_confirmada, FALSE) = FALSE
           AND (
                origem = 'datajud'
                OR referencia_datajud IS NOT NULL
                OR descricao LIKE '[ALERTA AUTOMÁTICO — DataJud]%'
           )
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE deadlines
           SET status = 'pendente',
               observacoes = NULLIF(
                   BTRIM(
                       REPLACE(
                           REPLACE(COALESCE(observacoes, ''), E'\n{_MENSAGEM}', ''),
                           '{_MENSAGEM}',
                           ''
                       )
                   ),
                   ''
               ),
               updated_at = NOW()
         WHERE status = 'cancelado'
           AND observacoes LIKE '%{_MARCADOR}%'
        """
    )
