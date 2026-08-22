"""documents.sha256 — integridade do arquivo juntado

Revision ID: 147_documents_sha256_integridade
Revises: 146_case_sigilo_reforcado
Create Date: 2026-08-22

Achado da auditoria funcional de 22/08/2026 (Issue #1237), prioridade 8 do
prompt-mestre (documentos).

O EJC é um sistema de PROVA DOCUMENTAL: o hash é o que sustenta a afirmação de
que o arquivo juntado hoje é o mesmo que foi carregado. A maquinaria de SHA-256
já existia inteira — `document_hash_service.calcular_sha256_local`, a variante
remota via rclone, `document_rescan_service` e a task de backfill
`tasks/rescan_tasks.agendar_rescan` (migration 142). Faltava o começo: o
upload direto (`POST /documents/upload`) não calculava nada, e a tabela
`documents` não tinha onde guardar. O SHA-256 existente vive em
`document_intake_items`, que só o fluxo de intake alimenta — documento juntado
pela tela ficava sem nenhuma evidência de integridade.

Puramente aditiva: coluna nullable, sem backfill nesta migration. Registros
anteriores ficam com `sha256 IS NULL`, que é a verdade — não havia hash. O
backfill é trabalho do rescan já existente, que sabe ler arquivo local e
remoto; forçá-lo aqui exigiria I/O de arquivo dentro de uma migration.

Índice: `sha256` é caminho natural para detectar duplicata e para conferência
de integridade em lote. Índice comum (não único): dois documentos idênticos
juntados em casos diferentes são legítimos.

Sem guarda de idempotência por introspecção: a primeira versão desta migration
usava `op.get_bind()` + `if coluna not in ...`, e o GATE REAL DE DEPLOY do
repositório (`tests/test_migrations_reais_passam_no_gate.py`) a reprovou —
`op.get_bind`, `If` e `Assign` exigem revisão humana porque migration que
ramifica em tempo de execução não pode ser conferida estaticamente antes de ir
para produção. O gate está certo, e o Alembic já garante execução única pela
tabela de versão. Declarativa é o formato que o repositório revisa.
"""
from alembic import op
import sqlalchemy as sa

revision = "147_documents_sha256_integridade"
down_revision = "146_case_sigilo_reforcado"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("sha256", sa.String(64), nullable=True))
    op.create_index("ix_documents_sha256", "documents", ["sha256"])


def downgrade() -> None:
    op.drop_index("ix_documents_sha256", table_name="documents")
    op.drop_column("documents", "sha256")
