"""Fase 0 — endpoint GET /pecas/meta (fonte única de metadados do gerador).

Exercita o endpoint REAL com get_current_user substituído (mesma abordagem de
test_bloco6_auth.py). Sem DB: o /meta é catálogo puro.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.security import get_current_user
from app.models.user import UserRole
from app.routers import peca_geracao as peca_router
from app.services.peca_service import (
    TIPOS_PECA_VALIDOS,
    TIPOS_PECA_GRUPO,
    GRUPOS_PECA_VALIDOS,
    AREAS_DIREITO,
    NIVEIS_COMPLEXIDADE,
)


class _FakeUser:
    def __init__(self, role: UserRole):
        self.id = "u-teste"
        self.role = role
        self.full_name = "Fulano Teste"


def _montar(role: UserRole = UserRole.estagiario):
    app = FastAPI()
    app.include_router(peca_router.router)
    app.dependency_overrides[get_current_user] = lambda: _FakeUser(role)
    return TestClient(app)


def test_meta_estagiario_recebe_catalogo_completo():
    client = _montar(UserRole.estagiario)
    r = client.get("/pecas/meta")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {"tipos", "areas", "niveis_complexidade"}

    # tipos: cobre TODOS os tipos válidos, cada um com value/label/grupo válido.
    values = [t["value"] for t in body["tipos"]]
    assert values == list(TIPOS_PECA_VALIDOS), "tipos do /meta divergem de TIPOS_PECA_VALIDOS"
    for t in body["tipos"]:
        assert set(t.keys()) == {"value", "label", "grupo"}
        assert t["grupo"] in GRUPOS_PECA_VALIDOS
        assert t["grupo"] == TIPOS_PECA_GRUPO[t["value"]]
        assert t["label"]  # rótulo não-vazio

    # "auto" é conveniência de UI, não é peça gerável — não entra no catálogo.
    assert "auto" not in values


def test_meta_expoe_todas_as_17_areas():
    client = _montar()
    body = client.get("/pecas/meta").json()
    areas = [a["value"] for a in body["areas"]]
    assert areas == list(AREAS_DIREITO)
    assert len(areas) == 17
    for a in body["areas"]:
        assert set(a.keys()) == {"value", "label"}
        assert a["label"]


def test_meta_expoe_niveis_complexidade_placeholder():
    client = _montar()
    body = client.get("/pecas/meta").json()
    assert body["niveis_complexidade"] == list(NIVEIS_COMPLEXIDADE)


def test_meta_todos_os_grupos_presentes():
    client = _montar()
    body = client.get("/pecas/meta").json()
    grupos = {t["grupo"] for t in body["tipos"]}
    assert grupos == set(GRUPOS_PECA_VALIDOS), \
        f"esperava todos os grupos {set(GRUPOS_PECA_VALIDOS)}, achou {grupos}"


def test_meta_role_abaixo_de_estagiario_recebe_403():
    client = _montar(UserRole.secretaria)  # nível 2 < estagiário (3)
    r = client.get("/pecas/meta")
    assert r.status_code == 403
