from pathlib import Path


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
