"""Onda 4 (§10) — filtro ``case_id`` no ``GET /intimacoes/``.

A aba "Intimações" do workspace do caso (frontend) lista as comunicações DJEN
vinculadas ao caso. O parâmetro é ADITIVO: sem ``case_id`` a query é exatamente
a anterior (mesmo comportamento validado pela suíte DJEN existente).

Estratégia de teste (padrão test_ajuizamento_router_rbac): app FastAPI isolado
com apenas o router sob teste; a statement SQLAlchemy executada é capturada e
a prova é a presença/ausência do predicado ``djen_comunicacoes.case_id``.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Select

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import UserRole
from app.routers import intimacoes as router_mod


class _CapturaDB:
    """execute() que captura a statement e devolve resultado vazio."""

    def __init__(self):
        self.statements: list[Any] = []

    async def execute(self, stmt, *a, **k):
        self.statements.append(stmt)

        class _R:
            def scalar(self):
                return 0

            def scalars(self):
                class _L:
                    def all(self):
                        return []

                return _L()

        return _R()


def _client(db: _CapturaDB) -> TestClient:
    app = FastAPI()
    app.include_router(router_mod.router)
    app.dependency_overrides[get_db] = lambda: db
    # `role` precisa ser o enum real: is_gestao usa ROLE_LEVEL[role] (hashable).
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id="u1", role=UserRole.advogado, full_name="Fulana"
    )
    return TestClient(app, raise_server_exceptions=False)


def _where_contem_case_id(stmt: Select) -> bool:
    """Prova o PREDICADO (WHERE), não a coluna do SELECT."""
    where = stmt.whereclause
    return where is not None and "case_id" in str(where.compile())


def _tem_predicado_case_id(db: _CapturaDB) -> bool:
    return any(isinstance(stmt, Select) and _where_contem_case_id(stmt) for stmt in db.statements)


def test_intimacoes_sem_case_id_nao_filtra_por_caso():
    db = _CapturaDB()
    r = _client(db).get("/intimacoes/", params={"apenas_pendentes": False})
    assert r.status_code == 200, r.text
    assert not _tem_predicado_case_id(db)


def test_intimacoes_com_case_id_filtra_por_caso():
    db = _CapturaDB()
    r = _client(db).get(
        "/intimacoes/",
        params={"apenas_pendentes": False, "case_id": "case-9"},
    )
    assert r.status_code == 200, r.text
    assert _tem_predicado_case_id(db)


def test_intimacoes_case_id_vazio_comporta_se_como_ausente():
    db = _CapturaDB()
    r = _client(db).get(
        "/intimacoes/",
        params={"apenas_pendentes": False, "case_id": ""},
    )
    assert r.status_code == 200, r.text
    assert not _tem_predicado_case_id(db)


def test_intimacoes_modelo_persiste_case_id():
    # Contrato consumido pela aba do workspace: a coluna case_id existe no
    # modelo (vínculo comunicação DJEN ↔ caso) e é serializada na resposta.
    from app.models.djen import DjenComunicacao

    assert hasattr(DjenComunicacao, "case_id")
