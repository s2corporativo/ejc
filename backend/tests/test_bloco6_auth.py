"""Bloco 6 — Autenticação: logout e login com credenciais inválidas.

Exercita os endpoints REAIS /auth/login e /auth/logout com DB substituível
(mesma abordagem de test_search.py), incluindo o wrapper @limiter.limit do
slowapi. Cada teste usa um X-Forwarded-For e e-mail ÚNICOS para isolar os
contadores por-IP (anti-brute-force + slowapi), evitando contaminação cruzada.
"""
from __future__ import annotations

import types

from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import get_password_hash, create_refresh_token
from app.routers import auth as auth_router


class _Res:
    def __init__(self, one=None):
        self._one = one

    def scalar_one_or_none(self):
        return self._one


class _FakeDB:
    def __init__(self, user=None):
        self._user = user
        self.added = []
        self.committed = 0
        self.execute_calls = 0

    async def execute(self, *a, **k):
        self.execute_calls += 1
        return _Res(self._user)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed += 1


def _montar(user=None):
    app = FastAPI()
    # o @limiter.limit do login exige app.state.limiter + handler de 429.
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(auth_router.router)
    db = _FakeDB(user)
    app.dependency_overrides[get_db] = lambda: db
    return app, db


def _hdr(ip: str) -> dict:
    # X-Forwarded-For único → contador anti-brute-force / slowapi isolado.
    return {"X-Forwarded-For": ip}


# ── Login com credenciais inválidas ───────────────────────────────────────────
def test_login_email_inexistente_401_e_audita_falha():
    app, db = _montar(user=None)
    client = TestClient(app)
    r = client.post(
        "/auth/login",
        json={"email": "naoexiste@teste.com", "password": "qualquer"},
        headers=_hdr("10.20.0.1"),
    )
    assert r.status_code == 401
    assert "senha" in r.json()["detail"].lower()
    # LOGIN_FALHA foi auditado (db.add do audit log + commit).
    assert len(db.added) == 1
    assert db.committed == 1


def test_login_senha_incorreta_401():
    user = types.SimpleNamespace(
        id="u1", role=types.SimpleNamespace(value="advogado"),
        hashed_password=get_password_hash("senha-correta"),
        totp_enabled=False,
    )
    app, _ = _montar(user=user)
    client = TestClient(app)
    r = client.post(
        "/auth/login",
        json={"email": "advogado@teste.com", "password": "senha-ERRADA"},
        headers=_hdr("10.20.0.2"),
    )
    assert r.status_code == 401


def test_login_brute_force_bloqueia_apos_5_falhas_429():
    app, _ = _montar(user=None)
    client = TestClient(app)
    ip = _hdr("10.20.0.99")
    # 5 falhas permitidas (401), a 6ª tentativa é bloqueada (429).
    codes = []
    for i in range(6):
        r = client.post(
            "/auth/login",
            json={"email": "bf@teste.com", "password": "x"},
            headers=ip,
        )
        codes.append(r.status_code)
    assert codes[:5] == [401, 401, 401, 401, 401]
    assert codes[5] == 429


# ── Logout ────────────────────────────────────────────────────────────────────
def test_logout_token_valido_revoga_e_200():
    app, db = _montar()
    client = TestClient(app)
    token, _jti = create_refresh_token("u1")
    r = client.post("/auth/logout", json={"refresh_token": token})
    assert r.status_code == 200
    assert "logout" in r.json()["detail"].lower()
    # A revogação (UPDATE RefreshToken SET revoked=True) foi emitida + commit.
    assert db.execute_calls == 1
    assert db.committed == 1


def test_logout_token_invalido_idempotente_sem_escrita():
    app, db = _montar()
    client = TestClient(app)
    r = client.post("/auth/logout", json={"refresh_token": "lixo-invalido"})
    assert r.status_code == 200            # idempotente, não vaza erro
    assert db.execute_calls == 0           # nada foi escrito no banco
    assert db.committed == 0
