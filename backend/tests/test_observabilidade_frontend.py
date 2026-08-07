"""Observabilidade — endpoint que recebe crashes de render do frontend.

Item #3 do plano de melhorias: o ErrorBoundary passa a reportar o erro ao
backend (visibilidade sem auditoria manual de console). Testa o contrato do
endpoint com auth substituível (padrão de test_search.py), sem banco.
"""
from __future__ import annotations

import types

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.security import get_current_user
from app.routers import observabilidade as obs_router


def _montar(role: str = "advogado"):
    app = FastAPI()
    app.include_router(obs_router.router)
    app.dependency_overrides[get_current_user] = lambda: types.SimpleNamespace(
        id="user-teste", role=types.SimpleNamespace(value=role)
    )
    return TestClient(app)


def test_registra_erro_frontend_204():
    client = _montar()
    r = client.post(
        "/observabilidade/frontend-error",
        json={
            "message": "TypeError: b.reduce is not a function",
            "stack": "at Sociedade (Sociedade.tsx:225)",
            "component_stack": "in Sociedade",
            "url": "/sociedade",
            "user_agent": "jsdom",
        },
    )
    assert r.status_code == 204


def test_message_obrigatoria_422():
    client = _montar()
    r = client.post("/observabilidade/frontend-error", json={"url": "/x"})
    assert r.status_code == 422


def test_campos_opcionais_ausentes_ok_204():
    client = _montar()
    r = client.post(
        "/observabilidade/frontend-error", json={"message": "erro só com message"}
    )
    assert r.status_code == 204
