from types import SimpleNamespace

import pytest

from app.core import database
from app.models import ai_log
from app.routers import documents
from app.services import analise_estrategica


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


@pytest.mark.asyncio
async def test_hook_de_upload_envia_ocr_integral_para_analise(monkeypatch):
    capturado = {}

    async def _analisar_caso(**kwargs):
        capturado.update(kwargs)
        return {"sumario_fatos": "minuta"}

    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(analise_estrategica, "analisar_caso", _analisar_caso)
    monkeypatch.setattr(ai_log, "AILog", lambda **kwargs: kwargs)

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
