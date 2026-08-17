import types
from pathlib import Path

import pytest
from fastapi import HTTPException


def _source(path: str) -> str:
    return (Path(__file__).parents[1] / path).read_text(encoding="utf-8")


def _function_source(source: str, name: str) -> str:
    start = source.index(f"async def {name}(")
    tail = source[start:]
    marker = tail.find("\n\n@router.")
    return tail if marker < 0 else tail[:marker]


def test_parseia_marcadores_estruturais_e_legados():
    from app.routers.legal_docs import _parse_score, _parse_veredito

    assert _parse_score("VALIDATION_SCORE:88") == 88
    assert _parse_veredito("VALIDATION_VERDICT:APTO PARA REVISAO") == "APTO PARA REVISAO"
    assert _parse_score("- score_confianca: 79") == 79
    assert _parse_veredito("- veredito: REVISAR ANTES DE USAR") == "REVISAR ANTES DE USAR"


def test_consulta_em_lote_nao_depende_de_prompt_textual():
    src = _source("app/routers/legal_docs.py")
    bloco = _function_source(src, "_validacoes_por_peca")
    assert "AILog.legal_doc_id.in_" in bloco
    assert "legal_doc_content_hash" in bloco
    assert "prompt_sanitizado.ilike" not in bloco
    assert "LEGAL_DOC_ID:" not in bloco


def test_edicao_invalida_revisao_e_protocolo_e_imutavel():
    src = _source("app/routers/legal_docs.py")
    bloco = _function_source(src, "atualizar")
    assert "Peça protocolada é imutável" in bloco
    assert "d.human_reviewed = False" in bloco
    assert 'mudancas["status"] = PecaStatus.em_revisao' in bloco
    assert "Conteúdo alterado exige novo ciclo" in bloco


def test_mutacoes_da_peca_usam_lock_pessimista():
    src = _source("app/routers/legal_docs.py")
    for nome in ("atualizar", "revisar", "aprovar", "registrar_protocolo"):
        bloco = _function_source(src, nome)
        assert ".with_for_update()" in bloco, nome


def test_ambos_pdfs_protocolaveis_usam_mesmo_gate():
    src = _source("app/routers/legal_docs.py")
    pdf = _function_source(src, "exportar_pdf")
    unico = _function_source(src, "documento_unico_impressao")
    assert "await _gates_exportacao_protocolo(db, d)" in pdf
    assert "await _gates_exportacao_protocolo(db, d)" in unico
    assert ".with_for_update()" in pdf
    assert ".with_for_update()" in unico


def test_nova_validacao_invalida_as_anteriores():
    src = _source("app/services/validador_juridico_service.py")
    assert "update(AILog)" in src
    assert "legal_doc_validation_current=False" in src
    assert "VALIDATION_SCORE:" in src
    assert "VALIDATION_VERDICT:" in src


def test_hitl_rejeita_validacao_de_versao_antiga():
    src = _source("app/routers/ai.py")
    bloco = _function_source(src, "atualizar_hitl")
    assert "log.legal_doc_validation_current" in bloco
    assert "log.legal_doc_content_hash != hash_atual" in bloco
    assert "Esta validação pertence a uma versão anterior" in bloco



def test_mutacoes_serializadas_e_pdf_falha_fechado_sem_hitl():
    src = _source("app/routers/legal_docs.py")
    for function_name in ("atualizar", "revisar", "registrar_protocolo"):
        bloco = _function_source(src, function_name)
        assert ".with_for_update()" in bloco

    gate = _function_source(src, "_gates_exportacao_protocolo")
    assert "d.ai_generated and not d.human_reviewed" in gate
    assert "revisão humana registrada" in gate

    atualizar = _function_source(src, "atualizar")
    assert "campos_imutaveis_protocolados" in atualizar
    assert '"status"' in atualizar


def test_orquestrador_nao_depende_de_filtro_textual_legado():
    src = _source("app/services/legal_case_orchestrator.py")
    assert "_VALIDACAO_TIPO_FILTRO" not in src
    assert "AILog.legal_doc_id" in src
    assert "AILog.legal_doc_content_hash" in src


# ── Achado #672 (homologação dinâmica, parte-13 §3.2): sem provedor de IA
# elegível, /validar deixava o RuntimeError do ai_gateway subir cru como 500
# genérico — e como a chamada nunca completava, ai_log_id nunca era gravado,
# travando /aprovar em "sem_validacao" para sempre, sem explicar por quê. ──

class _Res:
    def __init__(self, one=None):
        self._one = one

    def scalar_one_or_none(self):
        return self._one


class _FakeDB:
    def __init__(self, doc):
        self._doc = doc

    async def execute(self, *a, **k):
        return _Res(self._doc)


def _doc_sem_caso():
    return types.SimpleNamespace(
        id="doc-1", deleted_at=None, case_id=None,
        conteudo="rascunho fictício", tipo_peca=None, titulo="Peça de teste",
        status=None,
    )


def test_revisar_exige_papel_juridico_e_gate_de_citacoes():
    """Fix #984: /revisar exige requer_advogado e aplica o gate antialucinação
    (aplicar_gate_hitl) antes de registrar a aprovação — mesma garantia do
    conferir-e-assinar. Citação bloqueante → 409; verificação fora → 503."""
    src = _source("app/routers/legal_docs.py")
    bloco = _function_source(src, "revisar")
    assert "requer_advogado(" in bloco, "revisar deve exigir papel jurídico"
    assert "aplicar_gate_hitl" in bloco, "revisar deve rodar o gate de citações"
    assert "_ultima_validacao_peca" in bloco, "revisar deve achar o AILog corrente"


async def test_revisar_sem_papel_juridico_rejeita_com_403(monkeypatch):
    """Fix #984 (execução): não-advogado recebe 403 no /revisar."""
    from app.routers import legal_docs

    def fake_requer_advogado(u, detail=None):
        raise HTTPException(status_code=403, detail=detail)

    monkeypatch.setattr(legal_docs, "requer_advogado", fake_requer_advogado)

    async def _nada(*a, **k):
        raise AssertionError("não deve prosseguir além do gate de papel")

    for alvo in ("get_db", "verificar_acesso_caso", "criar_audit_log"):
        monkeypatch.setattr(legal_docs, alvo, _nada)

    cu = types.SimpleNamespace(id="u-2", role=types.SimpleNamespace(value="estagiario"))
    with pytest.raises(HTTPException) as exc:
        await legal_docs.revisar(
            "doc-x", legal_docs.LegalDocRevisao(aprovado=True, notas="ok"),
            background=types.SimpleNamespace(add_task=lambda *a: None),
            db=types.SimpleNamespace(execute=lambda *a: _Res(None),
                                     commit=_nada, refresh=_nada),
            cu=cu,
        )
    assert exc.value.status_code == 403


async def test_validar_sem_provedor_de_ia_nao_estoura_500_cru(monkeypatch):
    from app.routers import legal_docs

    async def fake_validar(*a, **k):
        raise RuntimeError(
            "Todos os provedores falharam para task=auditoria_peca. "
            "Último erro: Nenhum provedor disponível"
        )

    monkeypatch.setattr(legal_docs, "validar_rascunho_juridico", fake_validar)
    db = _FakeDB(_doc_sem_caso())
    cu = types.SimpleNamespace(id="u-1", role=types.SimpleNamespace(value="advogado"))

    with pytest.raises(HTTPException) as exc_info:
        await legal_docs.validar_peca_juridica("doc-1", db=db, cu=cu)

    erro = exc_info.value
    # Erro tratado (503, mensagem leiga) — não o 500 genérico do handler global.
    assert erro.status_code == 503
    for jargao in ("task=", "provedores", "RuntimeError"):
        assert jargao not in erro.detail
