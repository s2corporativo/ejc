"""Validação de payload dos endpoints de IA instrumentados (follow-up PR #308).

Exercita os endpoints REAIS com get_current_user/get_db substituídos (mesma
abordagem de test_pecas_meta_endpoint.py). NENHUMA chamada de IA acontece:
todos os cenários são barrados antes do shim ai_brain —
  • diplomacia-v3 /analisar-magistrado: payload agora é Pydantic
    (AnalisarMagistradoRequest) → entrada malformada vira 422, nunca 500;
    tetos por item (4.000 chars) e da lista (50 decisões) contra abuso de
    tokens no gateway de IA.
  • sala-de-guerra-v3 /war-room/simular: contrato 400 preservado para petição
    ausente/não-string; teto novo _MAX_PETICAO_CHARS → 422.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import UserRole
from app.routers import diplomacia_v3, sala_de_guerra_v3
from app.routers.diplomacia_v3 import AnalisarMagistradoRequest
from app.routers.sala_de_guerra_v3 import _MAX_PETICAO_CHARS


class _FakeUser:
    id = "u-teste-payload"
    role = UserRole.advogado
    full_name = "Advogado Teste"


async def _fake_db():
    yield None  # nenhum cenário abaixo chega a tocar o banco


def _montar(router) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    app.dependency_overrides[get_db] = _fake_db
    return TestClient(app)


# ── diplomacia-v3 /analisar-magistrado — payload Pydantic → 422 ──────────────

@pytest.fixture()
def cli_diplomacia() -> TestClient:
    return _montar(diplomacia_v3.router)


@pytest.mark.parametrize(
    "payload",
    [
        {"decisoes": "não é lista"},                       # tipo errado
        {"decisoes": [123]},                               # item não-string
        {"decisoes": ["ok"], "case_id": "x" * 65},         # case_id acima do teto
        {"decisoes": ["x" * 4001]},                        # item acima do teto
        {"decisoes": ["d"] * 51},                          # lista acima do teto
    ],
)
def test_analisar_magistrado_payload_invalido_422(cli_diplomacia, payload):
    r = cli_diplomacia.post("/diplomacia-v3/analisar-magistrado", json=payload)
    assert r.status_code == 422, r.text


def test_analisar_magistrado_schema_aceita_os_limites_exatos():
    # Fronteira superior VÁLIDA (50 × 4.000 + case_id de 64) — o teto barra o
    # abuso, não o uso legítimo.
    req = AnalisarMagistradoRequest(
        decisoes=["x" * 4000] * 50, case_id="a" * 64,
    )
    assert len(req.decisoes) == 50
    with pytest.raises(ValidationError):
        AnalisarMagistradoRequest(decisoes=["x" * 4000] * 51)


# ── sala-de-guerra-v3 /war-room/simular — 400 preservado + teto 422 ──────────

@pytest.fixture()
def cli_guerra() -> TestClient:
    return _montar(sala_de_guerra_v3.router)


@pytest.mark.parametrize("payload", [{}, {"peticao": ""}, {"peticao": 123}])
def test_war_room_sem_peticao_mantem_contrato_400(cli_guerra, payload):
    r = cli_guerra.post("/sala-de-guerra-v3/war-room/simular", json=payload)
    assert r.status_code == 400, r.text


def test_war_room_peticao_acima_do_teto_422(cli_guerra):
    r = cli_guerra.post(
        "/sala-de-guerra-v3/war-room/simular",
        json={"peticao": "x" * (_MAX_PETICAO_CHARS + 1)},
    )
    assert r.status_code == 422, r.text
    assert "limite" in r.json()["detail"].lower()
