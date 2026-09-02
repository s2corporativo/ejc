"""Exclusão Drive: soft-delete preserva o objeto remoto até o hard purge."""
from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.audit_log import AuditLog
from app.models.document import DocConfidencialidade, Document
from app.models.user import UserRole
from app.routers import documents as documents_router


class _MappingsResult:
    def __init__(self, payload: dict[str, bool]):
        self.payload = payload

    def one(self) -> dict[str, bool]:
        return self.payload


class _Res:
    def __init__(self, *, lista=None, mappings=None):
        self._lista = list(lista or [])
        self._mappings = mappings

    def scalars(self):
        return SimpleNamespace(all=lambda: self._lista)

    def mappings(self):
        assert isinstance(self._mappings, dict)
        return _MappingsResult(self._mappings)


class _FakeDB:
    def __init__(self, results):
        self.results = list(results)
        self.added = []
        self.committed = 0

    async def execute(self, stmt, *args, **kwargs):
        del stmt, args, kwargs
        assert self.results, "execute inesperado no fake de exclusão Drive"
        return self.results.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed += 1


def _referencias_vazias() -> dict[str, bool]:
    return {
        "protocolo": False,
        "prova": False,
        "assinatura": False,
        "centro_custo": False,
        "fee_payment": False,
        "deadline": False,
        "solicitacao_cliente": False,
        "contrato": False,
        "processo_eletronico": False,
        "data_room": False,
        "intake": False,
        "versao_posterior": False,
    }


def _doc_drive() -> Document:
    return Document(
        id="doc-drive-1",
        titulo="Documento remoto",
        filename="documento.pdf",
        filepath="drive://geral/interno-uuid.pdf",
        mimetype="application/pdf",
        size_bytes=100,
        confidencialidade=DocConfidencialidade.confidencial,
        uploaded_by="u1",
        drive_file_id="drive-1",
        deleted_at=None,
    )


def _client(db: _FakeDB) -> TestClient:
    app = FastAPI()
    app.include_router(documents_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id="u1",
        role=UserRole.admin,
        client_id=None,
    )
    return TestClient(app)


def _audits(db: _FakeDB) -> list[AuditLog]:
    return [obj for obj in db.added if isinstance(obj, AuditLog)]


def test_delete_drive_soft_delete_preserva_objeto_remoto(monkeypatch):
    doc = _doc_drive()
    db = _FakeDB(
        [
            _Res(lista=[doc]),
            _Res(mappings=_referencias_vazias()),
        ]
    )
    chamadas: list[tuple[str, str | None]] = []

    def fake_delete(file_id: str, *, remote_path=None):
        chamadas.append((file_id, remote_path))

    monkeypatch.setattr(documents_router.gd, "delete_file", fake_delete)

    response = _client(db).delete("/documents/drive/drive-1")

    assert response.status_code == 200
    assert chamadas == []
    assert doc.deleted_at is not None
    assert db.committed == 1
    logs = _audits(db)
    assert len(logs) == 1
    assert logs[0].acao == "DELETE"
    assert logs[0].dados_depois == {
        "storage": "drive",
        "storage_preservado": True,
        "rag_desativado": True,
    }


def test_delete_drive_nao_depende_da_disponibilidade_remota(monkeypatch):
    doc = _doc_drive()
    db = _FakeDB(
        [
            _Res(lista=[doc]),
            _Res(mappings=_referencias_vazias()),
        ]
    )

    def fake_delete(file_id: str, *, remote_path=None):
        del file_id, remote_path
        raise AssertionError("soft-delete não deve tocar no storage remoto")

    monkeypatch.setattr(documents_router.gd, "delete_file", fake_delete)

    response = _client(db).delete("/documents/drive/drive-1")

    assert response.status_code == 200
    assert doc.deleted_at is not None
    assert db.committed == 1
    logs = _audits(db)
    assert len(logs) == 1
    assert logs[0].acao == "DELETE"
