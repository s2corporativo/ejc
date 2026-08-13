"""Contrato do hook de análise documental — OCR integral, sem cortes.

O router legado ainda é grande e sensível; o app aplica, no startup, uma
substituição explícita do hook de background para enviar `ocr_text` completo
ao pipeline moderno, centralizado em `document_analysis_hook`. Este teste
protege a correção contra regressão.
"""

from types import SimpleNamespace

import pytest

from app.core import database
from app.models import ai_log
from app.routers import documents
from app.services import event_subscribers
from app.services import document_analysis_hook


class _Result:
    def fetchone(self):
        return SimpleNamespace(
            titulo="Caso de teste",
            area="civel",
            numero_processo="",
            client_id="cliente-1",
        )


class _FakeSession:
    def __init__(self):
        self.added = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, *_args, **_kwargs):
        return _Result()

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        return None


async def _stub_snapshot(*args, **kwargs):
    return None


@pytest.mark.asyncio
async def test_hook_de_upload_envia_ocr_integral_para_analise(monkeypatch):
    capturado = {}

    async def _analisar_caso(**kwargs):
        capturado.update(kwargs)
        return {"sumario_fatos": "minuta"}

    # O hook centralizado resolve TODAS as dependências pelo módulo próprio —
    # o monkeypatch precisa cobrir o namespace de `document_analysis_hook`,
    # não apenas o módulo de origem (`database`/`ai_log`).
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(document_analysis_hook, "AsyncSessionLocal",
                        lambda: _FakeSession())
    monkeypatch.setattr(document_analysis_hook, "analisar_caso", _analisar_caso)
    monkeypatch.setattr(document_analysis_hook, "_gravar_snapshot_documento",
                        _stub_snapshot)
    monkeypatch.setattr(ai_log, "AILog", lambda **kwargs: kwargs)
    monkeypatch.setattr(document_analysis_hook, "classificar_risco_ia",
                        lambda *a, **k: "baixo")

    # Garante o contrato vigente: o boot instala o hook centralizado
    # (document_analysis_hook.analisar_documento_bg) no símbolo legado do router.
    event_subscribers._install_document_analysis_hook()

    ocr_longo = (
        "INICIO DOS FATOS\n"
        + "A" * 7000
        + "\nPEDIDOS E PROVAS NO MEIO\n"
        + "B" * 7000
        + "\nFINAL COM PRAZO E DOCUMENTOS FALTANTES"
    )

    await documents._analisar_doc_bg(
        case_id="caso-1",
        ocr_text=ocr_longo,
        doc_id="doc-1",
        user_id="usuario-1",
    )

    assert capturado["texto_documento"] == ocr_longo
    assert len(capturado["texto_documento"]) > 14_000
    assert "PEDIDOS E PROVAS NO MEIO" in capturado["texto_documento"]
    assert capturado["case_id"] == "caso-1"
    assert capturado["scope_client_id"] == "cliente-1"
