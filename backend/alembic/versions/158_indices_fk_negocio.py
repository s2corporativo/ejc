"""Índices nas FKs de caminho de negócio + trigram em clients.nome / cases.titulo

Revision ID: 158_indices_fk_negocio
Revises: 157_ajuizamento_judicial
Create Date: 2026-09-06

Fecha DB-02 e DB-12 da auditoria de camadas de 06/09/2026
(docs/auditoria/relatorios/2026-09-06-auditoria-camadas.md, seção 2).

DB-02 — a recontagem por tabela+coluna (migrations e SQL cru incluídos)
achou 66 colunas FK sem índice. A migration 150 já decidiu, e esta mantém:
FKs de AUTORIA (`created_by`, `aprovado_por`, `alterado_por`…) ficam sem
índice de propósito — são trilha, escritas uma vez, nunca filtradas. Entram
aqui SOMENTE as doze que estão em caminho de negócio: percorridas ao listar
filhos de um pai (provas de uma tese, mensagens de um usuário, itens de um
checklist) ou varridas quando o pai é removido (`ON DELETE SET NULL/CASCADE`
sem índice no filho = seq scan a cada delete do pai). Conferido contra o
schema real (`pg_indexes`, PG16, `alembic upgrade head` do zero em 157):
nenhuma das doze tinha índice sob nome algum.

DB-12 — `clients.py:420-421` e `cases.py:142-144` filtram com `ILIKE
'%termo%'` em `nome` e `titulo`. O btree `ix_clients_nome` (migration 001)
não serve a `ILIKE` com curinga à esquerda; o único GIN trigram do banco era
o de `knowledge_chunks.conteudo` (009). A extensão `pg_trgm` existe desde a
009, então o índice GIN `gin_trgm_ops` é só uma declaração a mais.
`numero_processo`, citado no achado, fica de fora: `cases.py` compara por
igualdade normalizada, não por trigram.

Índice comum, não único (vários filhos por pai é o esperado). Escrita
LITERAL, sem laço — o gate de deploy (`tests/test_migrations_reais_passam_
no_gate.py`) reprova estrutura dinâmica em `upgrade()`.

Os catorze índices estão DECLARADOS NO ORM (`index=True` nas doze colunas;
`Index(..., postgresql_using="gin", postgresql_ops=...)` nos dois trigram),
pelo mesmo motivo da 155 e do #11: o autogenerate compara índices e, sem a
declaração, o próximo `alembic revision --autogenerate` proporia
`op.drop_index()` para todos.

ADITIVA E REVERSÍVEL: só cria índice. `downgrade()` remove exatamente os
catorze — e nada além (o btree `ix_clients_nome` da 001 permanece).

NOTA DE OPERAÇÃO (mesma da 155): `CREATE INDEX` comum trava escrita na
tabela durante a construção; no volume atual do EJC é instantâneo, como nas
migrations 115/150/155. GIN trigram é o mais caro dos catorze — em
`clients`/`cases` com dezenas de milhares de linhas ainda é questão de
segundos; na casa dos milhões, a construção passa a querer `CONCURRENTLY`,
que não cabe no formato transacional deste repositório.
"""
from alembic import op

revision = "158_indices_fk_negocio"
down_revision = "157_ajuizamento_judicial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── DB-02: FKs em caminho de negócio ────────────────────────────────────
    op.create_index("ix_judicial_filings_process_id", "judicial_filings", ["process_id"])
    op.create_index("ix_evidence_links_prova_id", "evidence_links", ["prova_id"])
    op.create_index("ix_evidence_links_tese_id", "evidence_links", ["tese_id"])
    op.create_index("ix_thesis_candidates_issue_id", "thesis_candidates", ["issue_id"])
    op.create_index("ix_thesis_candidates_tese_banco_id", "thesis_candidates", ["tese_banco_id"])
    op.create_index("ix_legal_chat_messages_user_id", "legal_chat_messages", ["user_id"])
    op.create_index("ix_diario_oficial_alertas_keyword_id", "diario_oficial_alertas", ["keyword_id"])
    op.create_index("ix_case_checklists_template_id", "case_checklists", ["template_id"])
    op.create_index("ix_case_checklist_items_template_item_id", "case_checklist_items", ["template_item_id"])
    op.create_index("ix_solicitacao_documento_itens_prova_id", "solicitacao_documento_itens", ["prova_id"])
    op.create_index("ix_document_hash_rescan_batches_caso_id", "document_hash_rescan_batches", ["caso_id"])
    op.create_index("ix_document_hash_rescan_batches_cliente_id", "document_hash_rescan_batches", ["cliente_id"])

    # ── DB-12: trigram para ILIKE '%termo%' (pg_trgm criada na 009) ─────────
    op.create_index(
        "ix_clients_nome_trgm",
        "clients",
        ["nome"],
        postgresql_using="gin",
        postgresql_ops={"nome": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_cases_titulo_trgm",
        "cases",
        ["titulo"],
        postgresql_using="gin",
        postgresql_ops={"titulo": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_cases_titulo_trgm", table_name="cases")
    op.drop_index("ix_clients_nome_trgm", table_name="clients")
    op.drop_index("ix_document_hash_rescan_batches_cliente_id", table_name="document_hash_rescan_batches")
    op.drop_index("ix_document_hash_rescan_batches_caso_id", table_name="document_hash_rescan_batches")
    op.drop_index("ix_solicitacao_documento_itens_prova_id", table_name="solicitacao_documento_itens")
    op.drop_index("ix_case_checklist_items_template_item_id", table_name="case_checklist_items")
    op.drop_index("ix_case_checklists_template_id", table_name="case_checklists")
    op.drop_index("ix_diario_oficial_alertas_keyword_id", table_name="diario_oficial_alertas")
    op.drop_index("ix_legal_chat_messages_user_id", table_name="legal_chat_messages")
    op.drop_index("ix_thesis_candidates_tese_banco_id", table_name="thesis_candidates")
    op.drop_index("ix_thesis_candidates_issue_id", table_name="thesis_candidates")
    op.drop_index("ix_evidence_links_tese_id", table_name="evidence_links")
    op.drop_index("ix_evidence_links_prova_id", table_name="evidence_links")
    op.drop_index("ix_judicial_filings_process_id", table_name="judicial_filings")
