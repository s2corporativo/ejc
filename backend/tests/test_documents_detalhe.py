"""GET /documents/{doc_id} — detalhe de documento (pente fino E2E 30/08 §5.1).

A releitura direta de um documento respondia 405 (só havia list/download/
PATCH/DELETE). O detalhe usa o MESMO caminho de autorização do download
(_verificar_acesso_documento + cofre por confidencialidade) e devolve o MESMO
shape do item da listagem — nunca `filepath`/paths internos de storage.

Padrão vizinho: test_documents_drive_delete.py (_FakeDB + TestClient +
dependency_overrides, sem harness de banco).
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.document import DocConfidencialidade, Document
from app.models.user import UserRole
from app.routers import documents as documents_router


class _Res:
    def __init__(self, valor=None):
        self._valor = valor

    def scalar_one_or_none(self):
        return self._valor


class _FakeDB:
    def __init__(self, results):
        self.results = list(results)

    async def execute(self, stmt, *args, **kwargs):
        del stmt, args, kwargs
        assert self.results, "execute inesperado no fake de detalhe de documento"
        return self.results.pop(0)


_CREATED_AT = datetime(2026, 8, 30, 12, 0, 0, tzinfo=timezone.utc)


def _doc(**kwargs) -> Document:
    base = dict(
        id="doc-1",
        titulo="Contrato social",
        tipo="contrato",
        filename="contrato.pdf",
        filepath="2026/08/doc-1.pdf",
        mimetype="application/pdf",
        size_bytes=1234,
        confidencialidade=DocConfidencialidade.normal,
        case_id=None,
        client_id=None,
        uploaded_by="u1",
        deleted_at=None,
        created_at=_CREATED_AT,
    )
    base.update(kwargs)
    return Document(**base)


def _client(db: _FakeDB, *, user_id="u1", role=UserRole.admin) -> TestClient:
    app = FastAPI()
    app.include_router(documents_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=user_id,
        role=role,
        client_id=None,
    )
    return TestClient(app)


def test_detalhe_200_devolve_shape_da_listagem_sem_path_de_storage():
    doc = _doc()
    response = _client(_FakeDB([_Res(doc)])).get("/documents/doc-1")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "id",
        "titulo",
        "tipo",
        "filename",
        "size_bytes",
        "confidencialidade",
        "case_id",
        "created_at",
    }
    assert body["id"] == "doc-1"
    assert body["titulo"] == "Contrato social"
    assert body["tipo"] == "contrato"
    assert body["filename"] == "contrato.pdf"
    assert body["size_bytes"] == 1234
    assert body["confidencialidade"] == "normal"
    assert body["case_id"] is None
    # Nunca vazar caminho físico/interno de storage.
    assert "filepath" not in body
    assert "2026/08" not in response.text


def test_detalhe_404_para_inexistente_ou_soft_deletado():
    # A query do router filtra deleted_at IS NULL: doc apagado e doc
    # inexistente caem no MESMO retorno vazio → 404 uniforme.
    response = _client(_FakeDB([_Res(None)])).get("/documents/nao-existe")

    assert response.status_code == 404
    assert response.json()["detail"] == "Documento não encontrado"


def test_detalhe_403_para_caso_sem_acesso():
    doc = _doc(case_id="c1")
    caso_de_outro = SimpleNamespace(
        id="c1",
        advogado_responsavel_id="outro-advogado",
        advogado_auxiliar_id=None,
    )
    db = _FakeDB([_Res(doc), _Res(caso_de_outro)])

    response = _client(db, user_id="u2", role=UserRole.advogado).get("/documents/doc-1")

    assert response.status_code == 403


def test_detalhe_403_cofre_para_restrito_abaixo_de_socio():
    # Uploader passa no gate de ownership, mas restrito+ exige socio+ (cofre) —
    # mesmo comportamento do download.
    doc = _doc(confidencialidade=DocConfidencialidade.restrito, uploaded_by="u2")
    db = _FakeDB([_Res(doc)])

    response = _client(db, user_id="u2", role=UserRole.advogado).get("/documents/doc-1")

    assert response.status_code == 403
    assert "restrito" in response.json()["detail"].lower()


def test_rotas_estaticas_declaradas_antes_do_detalhe():
    """FastAPI casa rotas na ordem de declaração: /tipos e GET / precisam vir
    ANTES de GET /{doc_id} para não serem capturadas pelo parâmetro."""
    ordem = [
        (getattr(r, "path", ""), tuple(sorted(getattr(r, "methods", None) or [])))
        for r in documents_router.router.routes
    ]
    idx_detalhe = ordem.index(("/documents/{doc_id}", ("GET",)))
    assert ordem.index(("/documents/tipos", ("GET",))) < idx_detalhe
    assert ordem.index(("/documents/", ("GET",))) < idx_detalhe
