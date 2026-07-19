"""109 — DataJud como fonte cognitiva informativa, nunca prazo fatal automático.

O código legado podia criar ``deadlines`` pendentes a partir da data do
andamento no DataJud. Como o DataJud não comprova publicação/intimação nem termo
inicial, esses registros não podem continuar disparando alertas 7d/3d/1d.

A migração preserva a linha para auditoria, marca origem e ausência de
confirmação, e cancela SOMENTE registros automáticos ainda pendentes e sem
ciência humana registrada. Prazos concluídos, cancelados, vencidos ou com
``ciencia_confirmada=true`` não são alterados.

Revision ID: 109_datajud_cognitive_feed
Revises: 108_credential_vault
Create Date: 2026-07-19
"""
from alembic import op

revision = "109_datajud_cognitive_feed"
down_revision = "108_credential_vault"
branch_labels = None
depends_on = None

_MARCADOR = "[MIG109_DATAJUD_INFORMATIVO]"


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
                   '{_MARCADOR} Cancelado automaticamente: DataJud é fonte de '
                   'metadados e não comprova intimação, publicação ou termo '
                   'inicial. Recrie/confirme o prazo somente após conferência '
                   'no DJEN ou sistema judicial autenticado.'
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
    # Reversão explícita apenas das linhas identificadas por esta migração. O
    # downgrade reabre os registros por compatibilidade técnica, mas a revisão
    # humana continua obrigatória (confirmado permanece FALSE).
    op.execute(
        f"""
        UPDATE deadlines
           SET status = 'pendente',
               observacoes = REPLACE(
                   COALESCE(observacoes, ''),
                   E'\n{_MARCADOR} Cancelado automaticamente: DataJud é fonte de '
                   'metadados e não comprova intimação, publicação ou termo '
                   'inicial. Recrie/confirme o prazo somente após conferência '
                   'no DJEN ou sistema judicial autenticado.',
                   ''
               ),
               updated_at = NOW()
         WHERE status = 'cancelado'
           AND observacoes LIKE '%{_MARCADOR}%'
        """
    )
