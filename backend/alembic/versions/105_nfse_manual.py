"""105 — campos de NFS-e manual em notas_fiscais_servico

Modo manual de NFS-e: a nota pode ser registrada/gerida sem provedor externo,
com dados informados pelo usuário e arquivos armazenados localmente:
  • data_emissao / competencia — datas informadas manualmente (DATE);
  • motivo_cancelamento — justificativa textual do cancelamento manual;
  • pdf_path / xml_path — caminhos locais dos arquivos, complementando
    pdf_url/xml_url (que permanecem para o fluxo via provedor, migration 085).

Todas as colunas são NULLABLE — notas emitidas via provedor não as preenchem.

ADITIVO PURO e IDEMPOTENTE: ADD COLUMN IF NOT EXISTS — mesmo padrão das
migrations 085/087.

Revision ID: 105_nfse_manual
Revises: 104_merge_entrada_orquestrador
Create Date: 2026-07-18
"""
from alembic import op

revision = "105_nfse_manual"
down_revision = "104_merge_entrada_orquestrador"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE notas_fiscais_servico "
        "ADD COLUMN IF NOT EXISTS data_emissao DATE"
    )
    op.execute(
        "ALTER TABLE notas_fiscais_servico "
        "ADD COLUMN IF NOT EXISTS competencia DATE"
    )
    op.execute(
        "ALTER TABLE notas_fiscais_servico "
        "ADD COLUMN IF NOT EXISTS motivo_cancelamento TEXT"
    )
    op.execute(
        "ALTER TABLE notas_fiscais_servico "
        "ADD COLUMN IF NOT EXISTS pdf_path VARCHAR(500)"
    )
    op.execute(
        "ALTER TABLE notas_fiscais_servico "
        "ADD COLUMN IF NOT EXISTS xml_path VARCHAR(500)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE notas_fiscais_servico DROP COLUMN IF EXISTS xml_path"
    )
    op.execute(
        "ALTER TABLE notas_fiscais_servico DROP COLUMN IF EXISTS pdf_path"
    )
    op.execute(
        "ALTER TABLE notas_fiscais_servico "
        "DROP COLUMN IF EXISTS motivo_cancelamento"
    )
    op.execute(
        "ALTER TABLE notas_fiscais_servico DROP COLUMN IF EXISTS competencia"
    )
    op.execute(
        "ALTER TABLE notas_fiscais_servico DROP COLUMN IF EXISTS data_emissao"
    )
