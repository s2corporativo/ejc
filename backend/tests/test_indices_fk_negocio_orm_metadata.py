"""Os índices das migrations 158 e 160 estão declarados no METADATA do ORM.

Mesmo motivo de `test_indices_listagem_orm_metadata.py` (migration 155): o
autogenerate compara índices e, sem a declaração no model, o próximo
`alembic revision --autogenerate` proporia `op.drop_index()` para todos —
desfazendo em silêncio os índices de FK (DB-02), os trigram (DB-12) e os
parciais de soft-delete (DB-05). Sem banco, de propósito.
"""
from __future__ import annotations

import pytest

_FK = {
    "judicial_filings": "ix_judicial_filings_process_id",
    "evidence_links": ("ix_evidence_links_prova_id", "ix_evidence_links_tese_id"),
    "thesis_candidates": ("ix_thesis_candidates_issue_id", "ix_thesis_candidates_tese_banco_id"),
    "legal_chat_messages": "ix_legal_chat_messages_user_id",
    "diario_oficial_alertas": "ix_diario_oficial_alertas_keyword_id",
    "case_checklists": "ix_case_checklists_template_id",
    "case_checklist_items": "ix_case_checklist_items_template_item_id",
    "solicitacao_documento_itens": "ix_solicitacao_documento_itens_prova_id",
    "document_hash_rescan_batches": (
        "ix_document_hash_rescan_batches_caso_id",
        "ix_document_hash_rescan_batches_cliente_id",
    ),
}
_TRGM = {"clients": ("ix_clients_nome_trgm", "nome"), "cases": ("ix_cases_titulo_trgm", "titulo")}
_PARCIAIS = {
    "atendimentos": "ix_atendimentos_vivos_client_data",
    "case_partes": "ix_case_partes_vivas_case",
}


def _indices(tabela: str) -> dict:
    import app.main  # noqa: F401 — popula Base.metadata com todos os models
    from app.core.database import Base

    return {ix.name: ix for ix in Base.metadata.tables[tabela].indexes}


@pytest.mark.parametrize("tabela", sorted(_FK))
def test_indices_de_fk_da_158_declarados_no_orm(tabela):
    esperados = _FK[tabela]
    esperados = (esperados,) if isinstance(esperados, str) else esperados
    declarados = _indices(tabela)
    faltando = [n for n in esperados if n not in declarados]
    assert not faltando, f"{tabela}: índices da migration 158 fora do ORM: {faltando}"
    for n in esperados:
        assert not declarados[n].unique


@pytest.mark.parametrize("tabela", sorted(_TRGM))
def test_indices_trigram_da_158_sao_gin_trgm_no_orm(tabela):
    nome, coluna = _TRGM[tabela]
    ix = _indices(tabela)[nome]
    pg = ix.dialect_options.get("postgresql", {})
    assert pg.get("using") == "gin"
    assert pg.get("ops", {}).get(coluna) == "gin_trgm_ops"


@pytest.mark.parametrize("tabela", sorted(_PARCIAIS))
def test_indices_parciais_da_160_declarados_com_predicado(tabela):
    ix = _indices(tabela)[_PARCIAIS[tabela]]
    predicado = ix.dialect_options.get("postgresql", {}).get("where")
    assert predicado is not None
    assert "deleted_at IS NULL" in str(predicado)


def test_case_partes_e_atendimentos_tem_deleted_at_e_pii_cifrada():
    from app.models.atendimento import Atendimento
    from app.models.case_parte import CaseParte

    assert "deleted_at" in Atendimento.__table__.columns
    cols = CaseParte.__table__.columns
    assert {"deleted_at", "cpf_cnpj", "cpf_cnpj_enc", "cpf_cnpj_hash"} <= set(cols.keys())
    assert "ix_case_partes_cpf_cnpj_hash" in _indices("case_partes")
