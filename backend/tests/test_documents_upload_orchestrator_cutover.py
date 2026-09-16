"""Cutover do POST /documents/upload para a ingestão streaming canônica."""
from __future__ import annotations

import io
import inspect
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException, UploadFile
from starlette.datastructures import Headers

from app.routers import documents
from app.services.document_upload_stream import UploadExcedeLimiteError
from app.services.document_version_service import DocumentoAnteriorObsoletoError


def _upload(nome: str = "contrato.pdf") -> UploadFile:
    return UploadFile(
        file=io.BytesIO(b"%PDF-1.4 conteudo de teste"),
        filename=nome,
        headers=Headers({"content-type": "application/pdf"}),
    )


def _user():
    return SimpleNamespace(id="u1", role=SimpleNamespace(value="advogado"))


def _resultado(*, nfe=None, ocr_text=None):
    return SimpleNamespace(
        documento=SimpleNamespace(id="doc-novo", ocr_text=ocr_text),
        extracao=SimpleNamespace(nfe=nfe),
    )


class _Rows:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _DB:
    def __init__(self, values=()):
        self.values = list(values)
        self.executed = 0

    async def execute(self, _stmt):
        self.executed += 1
        if not self.values:
            raise AssertionError("consulta inesperada no DB fake")
        return _Rows(self.values.pop(0))


def test_router_nao_materializa_upload_em_memoria():
    fonte = inspect.getsource(documents.upload)
    assert "await file.read()" not in fonte
    assert "ingerir_documento_local(" in fonte
    assert "hashlib.sha256" not in fonte


@pytest.mark.asyncio
async def test_upload_delega_stream_e_preserva_nfe_no_contrato(monkeypatch, tmp_path):
    observado = {}

    async def _ingerir(db, upload, **kwargs):
        observado.update({"db": db, "upload": upload, **kwargs})
        return _resultado(nfe={"numero": "123"})

    monkeypatch.setattr(documents, "ingerir_documento_local", _ingerir)
    monkeypatch.setattr(documents.settings, "UPLOAD_DIR", str(tmp_path))

    db = _DB()
    arquivo = _upload("nfe.pdf")
    resposta = await documents.upload(
        background_tasks=BackgroundTasks(),
        file=arquivo,
        titulo="NF-e recebida",
        tipo=None,
        confidencialidade="normal",
        case_id=None,
        client_id=None,
        db=db,
        cu=_user(),
    )

    assert observado["upload"] is arquivo
    assert observado["filename"] == "nfe.pdf"
    assert observado["dados"].titulo == "NF-e recebida"
    assert observado["dados"].uploaded_by == "u1"
    assert observado["dados"].documento_anterior_id is None
    assert resposta == {
        "id": "doc-novo",
        "detail": "Documento enviado",
        "nfe": {"numero": "123"},
    }
    assert db.executed == 0


@pytest.mark.asyncio
async def test_mesmo_titulo_no_caso_vira_predecessor_explicitamente(
    monkeypatch, tmp_path
):
    caso = SimpleNamespace(client_id="client-1")
    capturado = {}

    async def _acesso(_db, _cu, _case_id):
        return caso

    async def _lock(_db, *, case_id, titulo):
        capturado["lock"] = (case_id, titulo)

    async def _ingerir(_db, _upload_obj, **kwargs):
        capturado["dados"] = kwargs["dados"]
        return _resultado()

    async def _status(*args, **kwargs):
        capturado["status"] = (args, kwargs)

    from app.services import status_transicao

    monkeypatch.setattr(documents, "verificar_acesso_caso", _acesso)
    monkeypatch.setattr(documents, "bloquear_versionamento_por_titulo", _lock)
    monkeypatch.setattr(documents, "ingerir_documento_local", _ingerir)
    monkeypatch.setattr(status_transicao, "avancar_status_pos_commit", _status)
    monkeypatch.setattr(documents.settings, "UPLOAD_DIR", str(tmp_path))

    db = _DB(["doc-anterior"])
    await documents.upload(
        background_tasks=BackgroundTasks(),
        file=_upload(),
        titulo="  Contrato social  ",
        tipo=None,
        confidencialidade="normal",
        case_id="case-1",
        client_id="client-1",
        db=db,
        cu=_user(),
    )

    dados = capturado["dados"]
    assert dados.case_id == "case-1"
    assert dados.client_id == "client-1"
    assert dados.documento_anterior_id == "doc-anterior"
    assert dados.titulo == "Contrato social"
    assert capturado["lock"] == ("case-1", "Contrato social")
    assert db.executed == 1
    assert "status" in capturado


@pytest.mark.asyncio
async def test_concorrencia_de_versao_vira_409_sem_vazar_erro_interno(
    monkeypatch, tmp_path
):
    caso = SimpleNamespace(client_id="client-1")

    async def _acesso(_db, _cu, _case_id):
        return caso

    async def _ingerir(*args, **kwargs):
        raise DocumentoAnteriorObsoletoError("detalhe interno do predecessor")

    async def _lock(*args, **kwargs):
        return None

    monkeypatch.setattr(documents, "verificar_acesso_caso", _acesso)
    monkeypatch.setattr(documents, "bloquear_versionamento_por_titulo", _lock)
    monkeypatch.setattr(documents, "ingerir_documento_local", _ingerir)
    monkeypatch.setattr(documents.settings, "UPLOAD_DIR", str(tmp_path))

    with pytest.raises(HTTPException) as exc:
        await documents.upload(
            background_tasks=BackgroundTasks(),
            file=_upload(),
            titulo="Contrato social",
            tipo=None,
            confidencialidade="normal",
            case_id="case-1",
            client_id="client-1",
            db=_DB(["doc-anterior"]),
            cu=_user(),
        )

    assert exc.value.status_code == 409
    assert "Conflito de versionamento documental" in exc.value.detail
    assert "detalhe interno" not in exc.value.detail


@pytest.mark.asyncio
async def test_limite_streaming_mapeia_para_413(monkeypatch, tmp_path):
    async def _ingerir(*args, **kwargs):
        raise UploadExcedeLimiteError(1024)

    monkeypatch.setattr(documents, "ingerir_documento_local", _ingerir)
    monkeypatch.setattr(documents.settings, "UPLOAD_DIR", str(tmp_path))

    with pytest.raises(HTTPException) as exc:
        await documents.upload(
            background_tasks=BackgroundTasks(),
            file=_upload(),
            titulo="Arquivo grande",
            tipo=None,
            confidencialidade="normal",
            case_id=None,
            client_id=None,
            db=_DB(),
            cu=_user(),
        )

    assert exc.value.status_code == 413
    assert "Arquivo excede" in exc.value.detail
