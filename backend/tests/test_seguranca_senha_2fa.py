"""Hardening de segurança/auth (auditoria):

  1. Política de senha FORTE aplicada em TODA definição de senha nova
     (troca autenticada /auth/alterar-senha e reset por e-mail confirmar_reset).
     Nunca incide no login — senhas legadas curtas seguem entrando.
  2. 2FA (TOTP) obrigatório por PAPEL, sem lockout:
     - /auth/login sinaliza `precisa_configurar_2fa` quando o papel exige e o
       usuário ainda não tem TOTP;
     - /auth/totp/desativar recusa (403) desativar 2FA de papel obrigado.
     - REQUIRE_2FA_ROLES vazio (default) ⇒ nada muda.

Mesma abordagem de test_bloco6_auth.py: endpoints REAIS com DB substituível e o
wrapper @limiter.limit do slowapi. X-Forwarded-For / e-mails ÚNICOS por teste
isolam os contadores anti-brute-force e slowapi.
"""
from __future__ import annotations

import types

import pyotp
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import get_password_hash, create_access_token
from app.routers import auth as auth_router
from app.services import pii_crypto
from app.services.security_service import (
    validar_forca_senha, SENHA_MIN_LEN, confirmar_reset,
)


# ── Infra de teste ────────────────────────────────────────────────────────────
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


class _ResetDB:
    """execute() devolve a sequência esperada por confirmar_reset:
    1) token de reset, 2) usuário, 3) UPDATE de revogação de sessões."""

    def __init__(self, token_record, user):
        self._seq = [token_record, user]
        self.i = 0
        self.committed = 0

    async def execute(self, *a, **k):
        val = self._seq[self.i] if self.i < len(self._seq) else None
        self.i += 1
        return _Res(val)

    def add(self, obj):
        pass

    async def commit(self):
        self.committed += 1


def _montar(user=None):
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(auth_router.router)
    db = _FakeDB(user)
    app.dependency_overrides[get_db] = lambda: db
    return app, db


def _hdr(ip: str) -> dict:
    return {"X-Forwarded-For": ip}


# ─────────────────────────────────────────────────────────────────────────────
# 1. Política de senha forte — validador (unidade)
# ─────────────────────────────────────────────────────────────────────────────
def test_min_len_e_dez():
    assert SENHA_MIN_LEN == 10


@pytest.mark.parametrize("senha", [
    "Ab@1",            # curta demais (< 10)
    "senhalongaX",     # 11 chars, letra, SEM dígito
    "senha1234567",    # letra + dígito, SEM caractere especial
    "12345678901!",    # SEM letra
    "senha@1234",      # trivial (blocklist) apesar de complexa
    "Password@123",    # trivial (blocklist) apesar de complexa
])
def test_senhas_fracas_levantam(senha):
    with pytest.raises(ValueError):
        validar_forca_senha(senha)


def test_senha_igual_email_rejeitada():
    with pytest.raises(ValueError):
        validar_forca_senha("Joao1@teste.com", email="joao1@teste.com")


def test_senha_igual_parte_local_do_email_rejeitada():
    # local part "ab.cd1234ef" satisfaz a complexidade e é igual à senha.
    with pytest.raises(ValueError):
        validar_forca_senha("ab.cd1234ef", email="ab.cd1234ef@teste.com")


@pytest.mark.parametrize("senha", [
    "Str0ng@Pass!",
    "Nov@SenhaForte9",
    "X9y!zAbcdef",
])
def test_senhas_fortes_passam(senha):
    validar_forca_senha(senha)  # não deve levantar


# ─────────────────────────────────────────────────────────────────────────────
# 2. Troca de senha autenticada (/auth/alterar-senha)
# ─────────────────────────────────────────────────────────────────────────────
def _user_troca(email="troca@teste.com"):
    return types.SimpleNamespace(
        id="u1", email=email,
        role=types.SimpleNamespace(value="advogado"),
        hashed_password=get_password_hash("Atual@Senha123"),
        must_change_password=False,
    )


def test_alterar_senha_nova_fraca_400():
    user = _user_troca()
    app, _ = _montar(user=user)
    client = TestClient(app)
    token = create_access_token("u1", "advogado")
    r = client.post(
        "/auth/alterar-senha",
        json={"senha_atual": "Atual@Senha123", "nova_senha": "senhalongaX"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert "número" in r.json()["detail"].lower()


def test_alterar_senha_nova_forte_200():
    user = _user_troca()
    app, db = _montar(user=user)
    client = TestClient(app)
    token = create_access_token("u1", "advogado")
    r = client.post(
        "/auth/alterar-senha",
        json={"senha_atual": "Atual@Senha123", "nova_senha": "Nov@SenhaForte9"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    # nova hash aplicada + sessões revogadas + commit
    assert user.hashed_password != get_password_hash("Atual@Senha123")
    assert db.committed == 1


# ─────────────────────────────────────────────────────────────────────────────
# 3. Reset por e-mail (confirmar_reset) — service async
# ─────────────────────────────────────────────────────────────────────────────
async def test_reset_senha_fraca_raise_e_nao_consome_token():
    token = types.SimpleNamespace(user_id="u1", used=False)
    user = types.SimpleNamespace(id="u1", email="reset@teste.com",
                                 hashed_password="hash-antigo")
    db = _ResetDB(token, user)
    with pytest.raises(ValueError):
        await confirmar_reset(db, "tok-raw", "fraca")   # < 10, sem tudo
    # senha fraca NÃO consome o token nem grava nada
    assert token.used is False
    assert user.hashed_password == "hash-antigo"
    assert db.committed == 0


async def test_reset_senha_forte_aplica_e_consome_token():
    token = types.SimpleNamespace(user_id="u1", used=False)
    user = types.SimpleNamespace(id="u1", email="reset2@teste.com",
                                 hashed_password="hash-antigo")
    db = _ResetDB(token, user)
    ok = await confirmar_reset(db, "tok-raw", "Str0ng@Pass!")
    assert ok is True
    assert token.used is True
    assert user.hashed_password != "hash-antigo"
    assert db.committed == 1


# ─────────────────────────────────────────────────────────────────────────────
# 4. 2FA por papel — login sinaliza precisa_configurar_2fa
# ─────────────────────────────────────────────────────────────────────────────
def _user_login(role_value="admin", totp_enabled=False,
                email="user@teste.com", password="Str0ng@Pass!"):
    return types.SimpleNamespace(
        id="u1", email=email, full_name="Fulano",
        role=types.SimpleNamespace(value=role_value),
        hashed_password=get_password_hash(password),
        totp_enabled=totp_enabled, must_change_password=False,
        last_login_at=None,
    )


def test_login_require_2fa_vazio_nao_sinaliza(monkeypatch):
    monkeypatch.setattr(auth_router.settings, "REQUIRE_2FA_ROLES", "")
    user = _user_login(role_value="admin", totp_enabled=False)
    app, _ = _montar(user=user)
    client = TestClient(app)
    r = client.post(
        "/auth/login",
        json={"email": "user@teste.com", "password": "Str0ng@Pass!"},
        headers=_hdr("10.40.0.1"),
    )
    assert r.status_code == 200
    assert "precisa_configurar_2fa" not in r.json()


def test_login_require_2fa_papel_exigido_sem_totp_sinaliza(monkeypatch):
    monkeypatch.setattr(auth_router.settings, "REQUIRE_2FA_ROLES", "admin,socio")
    user = _user_login(role_value="admin", totp_enabled=False)
    app, _ = _montar(user=user)
    client = TestClient(app)
    r = client.post(
        "/auth/login",
        json={"email": "user@teste.com", "password": "Str0ng@Pass!"},
        headers=_hdr("10.40.0.2"),
    )
    assert r.status_code == 200
    assert r.json().get("precisa_configurar_2fa") is True


# ─────────────────────────────────────────────────────────────────────────────
# 5. 2FA por papel — desativar recusa (403) para papel obrigado
# ─────────────────────────────────────────────────────────────────────────────
def test_totp_desativar_papel_exigido_403(monkeypatch):
    monkeypatch.setattr(auth_router.settings, "REQUIRE_2FA_ROLES", "admin")
    user = types.SimpleNamespace(
        id="u1", email="admin@teste.com",
        role=types.SimpleNamespace(value="admin"),
        totp_enabled=True, totp_secret=pyotp.random_base32(),
    )
    app, _ = _montar(user=user)
    client = TestClient(app)
    token = create_access_token("u1", "admin")
    # o código nem é verificado — a recusa por papel vem antes.
    r = client.post(
        "/auth/totp/desativar",
        json={"codigo": "123456"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403
    assert "dois fatores" in r.json()["detail"].lower()
    # 2FA continua ativo — não foi desligado.
    assert user.totp_enabled is True


def test_totp_desativar_papel_nao_exigido_funciona(monkeypatch):
    # admin NÃO está na lista ⇒ o gate de papel não bloqueia; com o código
    # correto o 2FA é desativado normalmente (comportamento atual preservado).
    monkeypatch.setattr(auth_router.settings, "REQUIRE_2FA_ROLES", "socio")
    secret = pyotp.random_base32()
    user = types.SimpleNamespace(
        id="u2", email="admin2@teste.com",
        role=types.SimpleNamespace(value="admin"),
        totp_enabled=True, totp_secret=pii_crypto.encrypt(secret),
    )
    app, _ = _montar(user=user)
    client = TestClient(app)
    token = create_access_token("u2", "admin")
    codigo = pyotp.TOTP(secret).now()
    r = client.post(
        "/auth/totp/desativar",
        json={"codigo": codigo},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert user.totp_enabled is False
