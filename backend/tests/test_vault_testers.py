"""Cofre de Credenciais — PR-4: testadores de conexão + estados.

Cobertura (NENHUM teste faz rede real — httpx/SMTP 100% mockados):
  * mapeamento de cada categoria de erro por integração:
      200 → configurada · 401 → invalida · 401(expirado) → expirada ·
      403 → sem_permissao · timeout/5xx/DNS → indisponivel · ausência → ausente;
  * o `detalhe` nunca ecoa o segredo;
  * TESTERS cobre TODOS os providers do credential_registry;
  * endpoint POST /{provider}/testar: persiste last_test_* e exige superadmin;
  * integration_status.credential_state: campo novo, retrocompatível.
"""
from __future__ import annotations

import asyncio
import smtplib

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core import rate_limit as rl
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.security import get_current_user, get_password_hash
from app.models.integration_credential import IntegrationCredential
from app.models.user import User, UserRole
from app.routers import credential_vault as cv
from app.services import credential_registry
from app.services import credential_testers as ct
from app.services import credential_vault_service as svc
from app.services.integration_status import build_integration_status


# ── Fakes de httpx (sem rede) ────────────────────────────────────────────────

class _Resp:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = {} if json_data is None else json_data
        self.text = text

    def json(self):
        return self._json


class _Client:
    def __init__(self, resp=None, exc=None):
        self._resp = resp
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def request(self, *a, **k):
        if self._exc is not None:
            raise self._exc
        return self._resp

    async def get(self, *a, **k):
        return await self.request("GET", *a, **k)

    async def post(self, *a, **k):
        return await self.request("POST", *a, **k)


def _mock_httpx(monkeypatch, *, resp=None, exc=None):
    monkeypatch.setattr(ct.httpx, "AsyncClient", lambda *a, **k: _Client(resp, exc))


def _run(coro):
    return asyncio.run(coro)


# ── datajud: matriz completa de mapeamento HTTP → estado ─────────────────────

@pytest.mark.parametrize("resp,exc,esperado", [
    (_Resp(200), None, ct.CONFIGURADA),
    (_Resp(401, text="unauthorized"), None, ct.INVALIDA),
    (_Resp(401, text="Your token has expired"), None, ct.EXPIRADA),
    (_Resp(403), None, ct.SEM_PERMISSAO),
    (_Resp(500), None, ct.INDISPONIVEL),
    (_Resp(503), None, ct.INDISPONIVEL),
    (None, httpx.ConnectTimeout("timeout"), ct.INDISPONIVEL),
    (None, httpx.ConnectError("dns"), ct.INDISPONIVEL),
])
def test_datajud_mapeia_estados(monkeypatch, resp, exc, esperado):
    segredo = "datajud-secret-key-0000"
    monkeypatch.setattr(get_settings(), "DATAJUD_API_KEY", segredo)
    _mock_httpx(monkeypatch, resp=resp, exc=exc)

    estado, detalhe = _run(ct.testar_datajud())
    assert estado == esperado
    assert segredo not in detalhe          # detalhe nunca ecoa a chave


def test_datajud_sem_chave_e_ausente(monkeypatch):
    monkeypatch.setattr(get_settings(), "DATAJUD_API_KEY", "")
    # Sem chave, o testador retorna ANTES de qualquer httpx (sem rede).
    monkeypatch.setattr(ct.httpx, "AsyncClient", _rede_proibida)
    estado, _ = _run(ct.testar_datajud())
    assert estado == ct.AUSENTE


def _rede_proibida(*a, **k):
    raise AssertionError("testador não pode tocar a rede sem credencial")


# ── groq / anthropic / maritaca: liveness da chave via /models ───────────────

@pytest.mark.parametrize("tester,field", [
    (ct.testar_groq, "GROQ_API_KEY"),
    (ct.testar_anthropic, "ANTHROPIC_API_KEY"),
    (ct.testar_maritaca, "MARITACA_API_KEY"),
])
def test_provedores_ia_reuso_health(monkeypatch, tester, field):
    monkeypatch.setattr(get_settings(), field, "sk-ia-secret-abcd")
    _mock_httpx(monkeypatch, resp=_Resp(200))
    assert _run(tester())[0] == ct.CONFIGURADA

    _mock_httpx(monkeypatch, resp=_Resp(401, text="invalid api key"))
    assert _run(tester())[0] == ct.INVALIDA

    monkeypatch.setattr(get_settings(), field, "")
    monkeypatch.setattr(ct.httpx, "AsyncClient", _rede_proibida)
    assert _run(tester())[0] == ct.AUSENTE


# ── infosimples: mapeia o `code` do corpo (endpoint gratuito de conta) ───────

@pytest.mark.parametrize("code,esperado", [
    (200, ct.CONFIGURADA),
    (401, ct.INVALIDA),
    (403, ct.SEM_PERMISSAO),
    (600, ct.INDISPONIVEL),
])
def test_infosimples_mapeia_code(monkeypatch, code, esperado):
    monkeypatch.setattr(get_settings(), "INFOSIMPLES_TOKEN", "info-token-secret")
    _mock_httpx(monkeypatch, resp=_Resp(200, json_data={"code": code}))
    assert _run(ct.testar_infosimples())[0] == esperado


def test_infosimples_timeout_indisponivel(monkeypatch):
    monkeypatch.setattr(get_settings(), "INFOSIMPLES_TOKEN", "info-token-secret")
    _mock_httpx(monkeypatch, exc=httpx.ReadTimeout("t"))
    assert _run(ct.testar_infosimples())[0] == ct.INDISPONIVEL


# ── nfse: OAuth client_credentials, token descartado ─────────────────────────

def test_nfse_oauth(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "NFSE_NUVEMFISCAL_CLIENT_ID", "cid-secret")
    monkeypatch.setattr(s, "NFSE_NUVEMFISCAL_CLIENT_SECRET", "csecret-secret")

    _mock_httpx(monkeypatch, resp=_Resp(200, json_data={"access_token": "t"}))
    estado, detalhe = _run(ct.testar_nfse())
    assert estado == ct.CONFIGURADA
    assert "t" == "t" and "csecret-secret" not in detalhe  # token/secret nunca no detalhe

    _mock_httpx(monkeypatch, resp=_Resp(401, text="invalid_client"))
    assert _run(ct.testar_nfse())[0] == ct.INVALIDA

    monkeypatch.setattr(s, "NFSE_NUVEMFISCAL_CLIENT_ID", "")
    monkeypatch.setattr(ct.httpx, "AsyncClient", _rede_proibida)
    assert _run(ct.testar_nfse())[0] == ct.AUSENTE


# ── transparencia / langfuse: teste real de credencial (mockado) ─────────────

def test_transparencia_e_langfuse(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "TRANSPARENCIA_API_KEY", "cgu-key-secret")
    _mock_httpx(monkeypatch, resp=_Resp(200, json_data=[]))
    assert _run(ct.testar_transparencia())[0] == ct.CONFIGURADA
    _mock_httpx(monkeypatch, resp=_Resp(401))
    assert _run(ct.testar_transparencia())[0] == ct.INVALIDA

    monkeypatch.setattr(s, "LANGFUSE_PUBLIC_KEY", "pk-secret")
    monkeypatch.setattr(s, "LANGFUSE_SECRET_KEY", "sk-secret")
    monkeypatch.setattr(s, "LANGFUSE_HOST", "http://langfuse:3000")
    _mock_httpx(monkeypatch, resp=_Resp(200, json_data={"data": []}))
    assert _run(ct.testar_langfuse())[0] == ct.CONFIGURADA
    _mock_httpx(monkeypatch, resp=_Resp(401))
    assert _run(ct.testar_langfuse())[0] == ct.INVALIDA


# ── push_vapid: par local, sem teste remoto ──────────────────────────────────

def test_push_vapid_presenca(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "VAPID_PUBLIC_KEY", "pub")
    monkeypatch.setattr(s, "VAPID_PRIVATE_KEY", "priv")
    assert _run(ct.testar_push_vapid())[0] == ct.CONFIGURADA
    monkeypatch.setattr(s, "VAPID_PRIVATE_KEY", "")
    assert _run(ct.testar_push_vapid())[0] == ct.AUSENTE


# ── SMTP: connect+starttls+login+quit, sem enviar (smtplib mockado) ──────────

class _FakeSMTP:
    modo = "ok"  # ok | auth | timeout

    def __init__(self, host, port, timeout=None):
        if _FakeSMTP.modo == "timeout":
            raise TimeoutError("connect timed out")
        self.enviou = False

    def starttls(self):
        return (220, b"ready")

    def login(self, usuario, senha):
        if _FakeSMTP.modo == "auth":
            raise smtplib.SMTPAuthenticationError(535, b"auth failed")

    def send_message(self, *a, **k):  # nunca deve ser chamado (teste não envia)
        self.enviou = True

    def quit(self):
        return (221, b"bye")


@pytest.mark.parametrize("modo,esperado", [
    ("ok", ct.CONFIGURADA),
    ("auth", ct.INVALIDA),
    ("timeout", ct.INDISPONIVEL),
])
def test_smtp_mapeia_estados(monkeypatch, modo, esperado):
    s = get_settings()
    monkeypatch.setattr(s, "SMTP_USER", "user@ejc.test")
    monkeypatch.setattr(s, "SMTP_PASSWORD", "smtp-pass-secret")
    _FakeSMTP.modo = modo
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)

    estado, detalhe = _run(ct.testar_smtp())
    assert estado == esperado
    assert "smtp-pass-secret" not in detalhe


def test_smtp_sem_credencial_ausente(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "SMTP_USER", "")
    monkeypatch.setattr(s, "SMTP_PASSWORD", "")

    def _proibido(*a, **k):
        raise AssertionError("não pode conectar SMTP sem credencial")

    monkeypatch.setattr(smtplib, "SMTP", _proibido)
    assert _run(ct.testar_smtp())[0] == ct.AUSENTE


# ── Cobertura: todo provider do catálogo tem testador ────────────────────────

def test_todos_providers_tem_testador():
    assert set(credential_registry.REGISTRY) == set(ct.TESTERS)


def test_provider_desconhecido_nao_quebra():
    estado, _ = _run(ct.testar_provider("provider-inexistente"))
    assert estado == ct.CONFIGURADA  # metadado (sem teste) — não persiste erro falso


# ── integration_status.credential_state (retrocompatível) ────────────────────

def test_credential_state_ausente_por_default():
    """Sem credential_states, todos os itens ficam com credential_state=None e o
    contrato status ∈ disabled|attention|ready é preservado."""
    payload = build_integration_status(Settings(_env_file=None, APP_ENV="development"))
    for item in payload["items"]:
        assert item["credential_state"] is None
        assert item["status"] in ("disabled", "attention", "ready")


def test_credential_state_rebaixa_ready_para_attention():
    settings = Settings(
        _env_file=None, APP_ENV="development",
        DATAJUD_ENABLED=True, DATAJUD_API_KEY="k-datajud",
    )
    base = {i["key"]: i for i in build_integration_status(settings)["items"]}
    assert base["datajud"]["status"] == "ready"  # ready antes do teste

    refinado = {
        i["key"]: i for i in build_integration_status(
            settings, credential_states={"datajud": "invalida"},
        )["items"]
    }
    assert refinado["datajud"]["credential_state"] == "invalida"
    assert refinado["datajud"]["status"] == "attention"  # rebaixado pelo teste
    # configurada NÃO rebaixa.
    ok = {
        i["key"]: i for i in build_integration_status(
            settings, credential_states={"datajud": "configurada"},
        )["items"]
    }
    assert ok["datajud"]["status"] == "ready"
    assert ok["datajud"]["credential_state"] == "configurada"


def test_credential_state_nao_toca_disabled():
    settings = Settings(_env_file=None, APP_ENV="development", DATAJUD_ENABLED=False)
    refinado = {
        i["key"]: i for i in build_integration_status(
            settings, credential_states={"datajud": "invalida"},
        )["items"]
    }
    # Item desligado permanece disabled (o teste não o promove a attention).
    assert refinado["datajud"]["status"] == "disabled"


# ── Endpoint POST /{provider}/testar (RBAC + persistência) ───────────────────

SENHA = "senha-testar-123"
HASH = get_password_hash(SENHA)
SEGREDO = "sk-datajud-cofre-0000abcd"
BASE = "/cofre-credenciais"
URL_DATAJUD = f"{BASE}/datajud/DATAJUD_API_KEY"


def _user(role: UserRole = UserRole.superadmin) -> User:
    return User(
        id="u-super", email="super@ejc.test", hashed_password=HASH,
        full_name="Super", role=role, is_active=True, totp_enabled=False,
    )


@pytest.fixture(autouse=True)
def _rate_limit_limpo(monkeypatch):
    rl._limpar_janelas()
    rl._redis_client = None
    monkeypatch.setattr(get_settings(), "RATE_LIMIT_REDIS_ENABLED", False)
    yield
    rl._limpar_janelas()
    rl._redis_client = None


@pytest.fixture
def audit(monkeypatch):
    registros: list[dict] = []

    async def _fake(db, user_id, user_role, acao, entidade,
                    registro_id=None, detalhes=None, **kw):
        registros.append({"acao": acao, "entidade": entidade, "detalhes": detalhes})

    monkeypatch.setattr(cv, "criar_audit_log", _fake)
    monkeypatch.setattr(svc, "criar_audit_log", _fake)
    return registros


@pytest.fixture
def montar():
    engines = []

    def _montar(user: User):
        app = FastAPI()
        app.include_router(cv.router)
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        engines.append(engine)
        estado = {"criado": False, "user": user}

        async def _get_db():
            if not estado["criado"]:
                async with engine.begin() as conn:
                    await conn.run_sync(IntegrationCredential.__table__.create)
                estado["criado"] = True
            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as session:
                yield session

        app.dependency_overrides[get_db] = _get_db
        app.dependency_overrides[get_current_user] = lambda: estado["user"]
        return app, estado

    yield _montar
    for engine in engines:
        asyncio.run(engine.dispose())


def test_testar_persiste_e_exige_superadmin(montar, audit, monkeypatch):
    # Testador stubado: nenhuma rede real na rota.
    async def _stub(provider_key):
        assert provider_key == "datajud"
        return ("invalida", "Credencial inválida (HTTP 401).")

    monkeypatch.setattr(cv.credential_testers, "testar_provider", _stub)
    monkeypatch.setattr(get_settings(), "DATAJUD_API_KEY", "valor-do-env")

    app, estado = montar(_user())
    with TestClient(app) as client:
        # Cadastra a credencial (step-up por senha) para haver linha ativa.
        r = client.post(URL_DATAJUD, json={"senha_atual": SENHA, "valor": SEGREDO})
        assert r.status_code == 201

        # Testa a conexão (sem step-up) → persiste last_test_* na linha ativa.
        r = client.post(f"{BASE}/datajud/testar")
        assert r.status_code == 200
        body = r.json()
        assert body["estado"] == "invalida"
        assert body["campos_atualizados"] == 1
        assert body["provider_key"] == "datajud"
        assert SEGREDO not in r.text

        # GET agrupado reflete o last_test_status persistido (sem valor).
        campos = {c["field_key"]: c for p in client.get(BASE).json()
                  for c in p["campos"]}
        assert campos["DATAJUD_API_KEY"]["last_test_status"] == "invalida"
        assert campos["DATAJUD_API_KEY"]["last_test_at"] is not None
        assert SEGREDO not in client.get(BASE).text

        # Admin (nível 8) não opera o cofre → 403.
        estado["user"] = _user(UserRole.admin)
        assert client.post(f"{BASE}/datajud/testar").status_code == 403

    # Auditoria COFRE_TEST sem segredo.
    testes = [a for a in audit if a["acao"] == "COFRE_TEST"]
    assert len(testes) == 1
    assert SEGREDO not in (testes[0]["detalhes"] or "")


def test_testar_provider_fora_do_catalogo_404(montar, audit):
    app, _ = montar(_user())
    with TestClient(app) as client:
        assert client.post(f"{BASE}/acme/testar").status_code == 404
