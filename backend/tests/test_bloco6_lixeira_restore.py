"""Bloco 6 — Lixeira: exclusão lógica efetiva + restauração (ambiente não produtivo).

Exercita o router REAL de /trash com auth e DB substituíveis (mesma abordagem de
test_search.py), sem Postgres. Cobre: restaurar limpa o deleted_at (soft-delete
revertido), 404 fora da lixeira, 422 para entidade inválida, listagem só de
soft-deleted, e o gate RBAC (advogado é barrado: gate socio+).
"""
from __future__ import annotations

import types
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User, UserRole
from app.routers import trash as trash_router


class _Res:
    def __init__(self, one=None, muitos=None):
        self._one = one
        self._muitos = muitos or []

    def scalar_one_or_none(self):
        return self._one

    def scalars(self):
        return types.SimpleNamespace(all=lambda: self._muitos)


class _FakeDB:
    def __init__(self, res: _Res):
        self.res = res
        self.added = []
        self.committed = False

    async def execute(self, *a, **k):
        return self.res

    async def scalar(self, *a, **k):
        # O router passou a devolver paginação total; neste fake a mesma massa
        # representa o conjunto completo da listagem.
        return len(self.res._muitos)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True


def _montar(res: _Res, role: UserRole = UserRole.socio):
    app = FastAPI()
    app.include_router(trash_router.router)
    db = _FakeDB(res)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: User(
        id="user-teste", role=role
    )
    return TestClient(app), db


def test_restaurar_limpa_deleted_at_e_audita():
    rec = types.SimpleNamespace(
        id="c1",
        deleted_at=datetime.now(timezone.utc),
        nome="Cliente Teste",
        razao_social=None,
    )
    client, db = _montar(_Res(one=rec))
    r = client.post("/trash/clients/c1/restaurar")
    assert r.status_code == 200
    assert "restaurado" in r.json()["detail"].lower()
    assert rec.deleted_at is None
    assert db.committed is True
    assert len(db.added) == 1


def test_restaurar_registro_fora_da_lixeira_404():
    client, _ = _montar(_Res(one=None))
    r = client.post("/trash/clients/inexistente/restaurar")
    assert r.status_code == 404


def test_restaurar_entidade_invalida_422():
    client, _ = _montar(_Res(one=None))
    r = client.post("/trash/banana/x/restaurar")
    assert r.status_code == 422


def test_listar_retorna_soft_deleted():
    quando = datetime.now(timezone.utc)
    rows = [
        types.SimpleNamespace(
            id="c1", deleted_at=quando, nome="Alpha", razao_social=None
        ),
        types.SimpleNamespace(
            id="c2", deleted_at=quando, nome=None, razao_social="Beta LTDA"
        ),
    ]
    client, _ = _montar(_Res(muitos=rows))
    r = client.get("/trash/", params={"entidade": "clients"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert [d["id"] for d in data] == ["c1", "c2"]
    assert data[0]["rotulo"] == "Alpha"
    assert data[1]["rotulo"] == "Beta LTDA"
    assert r.json()["total"] == 2


def test_listar_entidade_invalida_422():
    client, _ = _montar(_Res())
    r = client.get("/trash/", params={"entidade": "nao_existe"})
    assert r.status_code == 422


def test_restaurar_barra_advogado_403():
    client, _ = _montar(_Res(one=None), role=UserRole.advogado)
    r = client.post("/trash/clients/c1/restaurar")
    assert r.status_code == 403


def test_listar_barra_advogado_403():
    client, _ = _montar(_Res(), role=UserRole.advogado)
    r = client.get("/trash/", params={"entidade": "clients"})
    assert r.status_code == 403
