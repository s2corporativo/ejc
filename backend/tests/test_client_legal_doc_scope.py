"""Contratos de segurança do vínculo Client -> LegalDoc."""
from __future__ import annotations

import inspect


def test_router_legal_docs_aplica_gate_transversal_de_client_id():
    from app.routers import legal_docs

    fonte = inspect.getsource(legal_docs)
    assert "_enforce_client_legal_doc_scope" in fonte
    assert "cliente_id_visivel" in fonte
    assert "dependencies=[Depends(_enforce_client_legal_doc_scope)]" in fonte
    assert "LegalDoc.client_id.in_(ids_clientes_visiveis(cu))" in fonte
    assert "LegalDoc.client_id.is_(None)" in fonte


def test_validacao_e_assinatura_herdam_escopo_do_cliente_avulso():
    from app.routers import legal_docs

    fonte = inspect.getsource(legal_docs)
    assert fonte.count('escopo_cli = getattr(d, "client_id", None)') == 2


def test_rag_herda_client_id_da_peca_avulsa():
    from app.services import case_intel

    fonte = inspect.getsource(case_intel.indexar_peca_rag)
    assert 'client_id = getattr(d, "client_id", None)' in fonte
    assert "elif client_id:" in fonte
    assert "client_id=client_id, case_id=d.case_id" in fonte


def test_template_admissao_nao_e_marcado_como_saida_llm():
    from app.services import geracao_documental_cliente

    fonte = inspect.getsource(geracao_documental_cliente.gerar_documentos_cliente)
    assert "ai_generated=False" in fonte
    assert "human_reviewed=False" in fonte
    assert "client_admission_kind=admission_kind" in fonte
