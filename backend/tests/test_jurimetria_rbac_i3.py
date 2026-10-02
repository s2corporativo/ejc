# Achado I3 (auditoria de Inteligência 2026-10-01): rotas do router de
# jurimetria registradas ANTES do `router.dependencies.append(_req_staff)`
# ficavam sem gate de papel (FastAPI só aplica dependências do router às rotas
# registradas depois do append). `/analise-prospectiva` respondia 200 a
# financeiro/secretaria. Issue #694: allowlist EXATA EQUIPE_JURIDICA.
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import EQUIPE_JURIDICA, get_current_user
from app.models.user import User, UserRole
from app.routers import jurimetria

FORA = [UserRole.financeiro, UserRole.secretaria, UserRole.cliente_externo]
DENTRO = [UserRole.advogado, UserRole.estagiario]
ROTAS = ["/jurimetria/analise-prospectiva", "/jurimetria/predicao-exito"]


def _client(role: UserRole, monkeypatch) -> TestClient:
    from app.services.ai.core import orchestrator as orq

    async def _run(**kw):
        return {"conteudo": "ok", "modelo": "m", "provider": "p", "log_id": 1}

    monkeypatch.setattr(orq.orchestrator, "run", _run)
    app = FastAPI()
    app.include_router(jurimetria.router, prefix="/api")
    app.include_router(jurimetria.router, prefix="/api/v1")

    async def _db():
        yield object()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: User(
        id="u1", role=role, full_name="Teste"
    )
    return TestClient(app)


@pytest.mark.parametrize("prefix", ["/api", "/api/v1"])
@pytest.mark.parametrize("rota", ROTAS)
@pytest.mark.parametrize("role", FORA)
def test_fora_da_equipe_recebe_403(role, rota, prefix, monkeypatch):
    r = _client(role, monkeypatch).post(prefix + rota, json={"contexto": "x"})
    assert r.status_code == 403


@pytest.mark.parametrize("prefix", ["/api", "/api/v1"])
@pytest.mark.parametrize("rota", ROTAS)
@pytest.mark.parametrize("role", DENTRO)
def test_equipe_juridica_continua_com_acesso(role, rota, prefix, monkeypatch):
    r = _client(role, monkeypatch).post(prefix + rota, json={"contexto": "x"})
    assert r.status_code == 200


def test_toda_rota_do_router_exige_gate_de_equipe():
    # Varredura: nenhuma rota do router pode ficar fora do gate de equipe,
    # independentemente da ordem de registro.
    sem_gate = []
    for rt in jurimetria.router.routes:
        if not isinstance(rt, APIRoute):
            continue
        deps = {d.call for d in rt.dependant.dependencies}
        if jurimetria._req_staff not in deps:
            sem_gate.append(rt.path)
    assert not sem_gate, f"rotas sem _req_staff: {sem_gate}"
    assert "financeiro" not in EQUIPE_JURIDICA
