"""Política de extensão/MIME do GED — fonte neutra e paridade durante cutover."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.services.document_content_policy import (
    EXTENSOES_PERMITIDAS,
    MIME_POR_EXTENSAO,
    exigir_extensao_permitida,
    extensao_normalizada,
    validar_conteudo,
)


def test_extensao_e_normalizada_sem_usar_nome_como_path():
    assert extensao_normalizada("PETICAO.PDF") == ".pdf"
    assert extensao_normalizada("../../cliente/arquivo.DOCX") == ".docx"
    assert extensao_normalizada(None) == ""


def test_extensao_fora_da_allowlist_falha_fechado():
    with pytest.raises(HTTPException) as exc:
        exigir_extensao_permitida("arquivo.exe")
    assert exc.value.status_code == 422
    assert ".exe" in str(exc.value.detail)


def test_magic_bytes_prevalecem_sobre_content_type_do_cliente():
    with patch(
        "app.services.document_content_policy.magic.from_buffer",
        return_value="application/pdf",
    ):
        assert validar_conteudo(".pdf", b"%PDF-1.7") == "application/pdf"

    with patch(
        "app.services.document_content_policy.magic.from_buffer",
        return_value="text/html",
    ):
        with pytest.raises(HTTPException) as exc:
            validar_conteudo(".pdf", b"<html></html>")
        assert exc.value.status_code == 415


def test_politica_neutra_permanece_em_paridade_com_ged_legacy():
    """Trava temporária até documents.py consumir diretamente o service.

    Enquanto o monólito GED ainda define as constantes antigas, qualquer drift
    entre as duas fontes deve falhar explicitamente em vez de mudar Portal/Raio-X
    silenciosamente. Esta prova pode ser removida no cutover em que o router
    passar a importar a política canônica.
    """
    from app.routers import documents

    assert EXTENSOES_PERMITIDAS == documents.EXTENSOES_PERMITIDAS
    assert set(MIME_POR_EXTENSAO) == set(documents.MIME_POR_EXTENSAO)
    for ext, mimes in MIME_POR_EXTENSAO.items():
        assert set(mimes) == set(documents.MIME_POR_EXTENSAO[ext])


def test_consumidores_nao_importam_mais_validacao_do_router():
    backend = Path(__file__).parents[1]
    for rel in (
        "app/services/upload_lote_service.py",
        "app/routers/portal_documentos.py",
    ):
        source = (backend / rel).read_text(encoding="utf-8")
        assert "from app.routers.documents import" not in source
        assert "_validar_conteudo" not in source
        assert "document_content_policy" in source


def test_portal_nao_grava_nome_do_item_no_worm_de_upload():
    source = (
        Path(__file__).parents[1] / "app/routers/portal_documentos.py"
    ).read_text(encoding="utf-8")
    trecho_audit = source.split("await criar_audit_log(", 1)[1].split(
        "await db.commit()", 1
    )[0]
    assert "detalhes=" not in trecho_audit
    assert '"documento_id": doc_id' in trecho_audit
    assert "item.nome" not in trecho_audit
