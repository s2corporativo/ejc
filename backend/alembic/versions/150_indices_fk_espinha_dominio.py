"""Índices nas FKs que apontam para a espinha do domínio

Revision ID: 150_indices_fk_espinha_dominio
Revises: 149_documents_sha256_integridade
Create Date: 2026-08-22

Achado da auditoria funcional de 22/08/2026 (Issue #1237), prioridade 15 (§71).

A anotação anterior dizia "6 tabelas periféricas sem índice de FK, impacto não
medido — todas vazias". Medido no schema real (147 migrations do zero), são
**74** FKs de coluna única sem índice. A anotação errou por mais de uma ordem
de grandeza — mais um caso de item registrado carregando o tamanho que o
problema tinha aos olhos de quem passou correndo por ele.

Mas indexar as 74 seria pior que o problema. A distribuição decide:

    50 -> users          (created_by, aprovado_por, alterado_por…)
     4 -> documents
     4 -> cases
     1 -> clients
    15 -> tabelas de template/apoio

As 50 que apontam para `users` são TRILHA: escritas uma vez, praticamente nunca
usadas como filtro. Indexá-las custaria escrita em 50 tabelas para uma consulta
que não existe. Ficam de fora, deliberadamente.

Esta migration cobre as 9 que apontam para a espinha do domínio — `cases`,
`clients`, `documents`. São as percorridas em toda listagem escopada a um caso,
cliente ou documento, e as varridas quando o pai é removido. Índice comum, não
único: vários filhos por pai é o esperado.

Aditiva e reversível. Escrita LITERAL, sem laço e sem introspecção: o gate real
de deploy (`tests/test_migrations_reais_passam_no_gate.py`) reprova `For`, `If`,
`Assign` e `op.get_bind`, porque migration que se monta em tempo de execução não
é conferível estaticamente antes de produção. A primeira versão desta migration
usava um `for` sobre uma lista de tuplas e foi reprovada — a repetição explícita
é o formato que o repositório sabe revisar.

Renumerada de 148 para 150 ao mesclar a `main` em 2026-08-23, na mesma
colisão de numeração que renumerou a migration anterior desta cadeia (147
ocupada por `147_pendencia_impacto_providencia`).
"""
from alembic import op

revision = "150_indices_fk_espinha_dominio"
down_revision = "149_documents_sha256_integridade"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_centro_custos_comprovante_id", "centro_custos", ["comprovante_id"])
    op.create_index("ix_contratos_societarios_case_id", "contratos_societarios", ["case_id"])
    op.create_index("ix_contratos_societarios_client_id", "contratos_societarios", ["client_id"])
    op.create_index("ix_contratos_societarios_documento_id", "contratos_societarios", ["documento_id"])
    op.create_index("ix_diario_oficial_alertas_case_id", "diario_oficial_alertas", ["case_id"])
    op.create_index("ix_diario_oficial_keywords_case_id", "diario_oficial_keywords", ["case_id"])
    op.create_index("ix_documents_versao_anterior_id", "documents", ["versao_anterior_id"])
    op.create_index("ix_inadimplencia_alerts_case_id", "inadimplencia_alerts", ["case_id"])
    op.create_index("ix_solicitacao_documento_itens_documento_id", "solicitacao_documento_itens", ["documento_id"])


def downgrade() -> None:
    op.drop_index("ix_solicitacao_documento_itens_documento_id", table_name="solicitacao_documento_itens")
    op.drop_index("ix_inadimplencia_alerts_case_id", table_name="inadimplencia_alerts")
    op.drop_index("ix_documents_versao_anterior_id", table_name="documents")
    op.drop_index("ix_diario_oficial_keywords_case_id", table_name="diario_oficial_keywords")
    op.drop_index("ix_diario_oficial_alertas_case_id", table_name="diario_oficial_alertas")
    op.drop_index("ix_contratos_societarios_documento_id", table_name="contratos_societarios")
    op.drop_index("ix_contratos_societarios_client_id", table_name="contratos_societarios")
    op.drop_index("ix_contratos_societarios_case_id", table_name="contratos_societarios")
    op.drop_index("ix_centro_custos_comprovante_id", table_name="centro_custos")
