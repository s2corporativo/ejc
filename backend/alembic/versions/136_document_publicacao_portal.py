"""Publicação explícita de documento no Portal do Cliente (Issue #698).

A migration 127_publicacao_explicita (Fase 0, auditoria 2026-07) estancou o
vazamento por CLASSIFICAÇÃO: mudou o default de `documents.confidencialidade`
de "normal" para "confidencial" e reclassificou em massa os documentos que
estavam "normal". Isso reduziu a EXPOSIÇÃO, mas não resolveu o desenho: o
Portal (`GET /portal/documentos`) continua derivando visibilidade
diretamente de `confidencialidade == normal` — reclassificar continua sendo
publicar, sem autor nem data. O Data Room já resolveu isso corretamente para
o link público (`DataRoomArquivo.publicado_externamente/publicado_por/
publicado_em`, Issue #547); esta migration traz o mesmo desenho para
`documents`, para o Portal do Cliente autenticado.

Adiciona a `documents`:
  - publicado_portal  BOOLEAN NOT NULL DEFAULT false  — ato explícito de
    publicação ao Portal, distinto de confidencialidade
  - publicado_por     VARCHAR(36) FK users.id NULL     — quem publicou
    (NULL quando o próprio cliente enviou o documento pelo Portal — ver
    app/routers/portal_documentos.py)
  - publicado_em      TIMESTAMPTZ NULL                 — quando

O gate de quem PODE publicar (`app.core.publicacao_externa
.pode_publicar_externamente`) e o filtro de visibilidade no Portal
(`confidencialidade == normal AND publicado_portal == true`) vivem no
código da aplicação, não aqui — esta migration só adiciona as colunas.

── DECISÃO PENDENTE DO TITULAR (regra 9 do CLAUDE.md: esta migration NÃO
decide sozinha) ──────────────────────────────────────────────────────────
Todo documento com confidencialidade='normal' HOJE nasce, após esta
migration, com publicado_portal=false (comportamento conservador: some do
Portal até publicação explícita). Duas opções para o titular decidir no
review do PR:

  (a) Publicar retroativamente — preserva o que o cliente já vê hoje, mas
      legitima qualquer exposição não intencional que a reclassificação em
      massa da 127 não tenha coberto (ex.: documento reclassificado de
      volta para "normal" depois da 127):
        UPDATE documents SET publicado_portal = true, publicado_por = NULL,
               publicado_em = now()
        WHERE confidencialidade = 'normal' AND publicado_portal = false
              AND deleted_at IS NULL;

  (b) Manter despublicado até ato explícito — mais correto (fecha o
      desenho que a Issue #698 aponta), mas remove do Portal, até o
      escritório clicar "publicar", qualquer documento que o cliente já
      enxergava.

Esta migration não escolhe — o número de documentos afetados pode ser
levantado a qualquer momento pelo titular com uma simples contagem manual
(consulta abaixo, sem efeito colateral) antes de decidir (a) ou (b):

    SELECT COUNT(*) FROM documents
    WHERE confidencialidade = 'normal' AND deleted_at IS NULL;

A decisão (a) ou (b) deve ser executada como backfill separado, declarado
e aprovado, não dentro desta migration.
"""
from alembic import op
import sqlalchemy as sa


revision = '136_document_publicacao_portal'
down_revision = '135_indice_risco_nivel_size'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'documents',
        sa.Column(
            'publicado_portal', sa.Boolean(), nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        'documents',
        sa.Column(
            'publicado_por', sa.String(length=36),
            sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True,
        ),
    )
    op.add_column(
        'documents',
        sa.Column('publicado_em', sa.DateTime(timezone=True), nullable=True),
    )
    # Sem diagnóstico SQL aqui: o gate de deploy exige upgrade() estritamente
    # op.* estático. A contagem de documentos afetados é levantada manualmente
    # (consulta no cabeçalho) antes da decisão do titular (a) ou (b).


def downgrade() -> None:
    op.drop_column('documents', 'publicado_em')
    op.drop_column('documents', 'publicado_por')
    op.drop_column('documents', 'publicado_portal')
