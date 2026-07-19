"""Cofre de Credenciais — PR-3: router /cofre-credenciais (RBAC + step-up).

Sem Postgres: SQLite in-memory (aiosqlite + StaticPool, padrão de
test_vault_service) criado DENTRO do loop do TestClient (override de get_db).
Auth substituída por dependency_overrides (get_current_user) com User ORM
detached; auditoria capturada por fake (a tabela audit_logs usa JSONB).

Cobertura:
  * RBAC: admin → 403 em todas as rotas; superadmin passa;
  * step-up: senha errada → 403 + audit COFRE_REAUTH_FALHA + SEM efeito;
    TOTP exigido/validado quando o usuário tem 2FA ativo;
  * cadastro → aplicar_overlay NA MESMA request (Settings singleton);
  * IntegrityError (corrida) → 409; ValueError de validação → 422;
  * revogar: 404 sem ativa; ok → "" no Settings (sem fallback ao .env);
  * importar-env: resumo sem valores;
  * historico: só metadados;
  * NENHUMA resposta JSON contém o valor cadastrado (varredura do corpo);
  * rate limit presente nas rotas mutadoras (6ª chamada → 429).
"""
from __future__ import annotations

import asyncio

import pyotp
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core import rate_limit as rl
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user, get_password_hash
from app.models.integration_credential import IntegrationCredential
from app.models.user import User, UserRole
from app.routers import credential_vault as cv
from app.services import credential_vault_service as svc

SENHA = "senha-correta-123"
HASH = get_password_hash(SENHA)          # 1 bcrypt por módulo (12 rounds)
SEGREDO = "sk-router-cofre-0000abcd"
TOTP_SECRET = pyotp.random_base32()      # em claro = legado aceito (fallback)

BASE = "/cofre-credenciais"
URL_DATAJUD = f"{BASE}/datajud/DATAJUD_API_KEY"


def _user(role: UserRole = UserRole.superadmin, totp: bool = False) -> User:
    u = User(
        id="u-super", email="super@ejc.test", hashed_password=HASH,
        full_name="Super", role=role, is_active=True, totp_enabled=totp,
    )
    if totp:
        u.totp_secret = TOTP_SECRET      # legado em claro — _totp_secret_de cai no base32
    return u


@pytest.fixture(autouse=True)
def _rate_limit_limpo(monkeypatch):
    """Contadores de rate limit zerados e backend Redis desligado por teste."""
    rl._limpar_janelas()
    rl._redis_client = None
    monkeypatch.setattr(get_settings(), "RATE_LIMIT_REDIS_ENABLED", False)
    yield
    rl._limpar_janelas()
    rl._redis_client = None


@pytest.fixture(autouse=True)
def audit(monkeypatch):
    """Captura criar_audit_log do router E do service (audit_logs usa JSONB)."""
    registros: list[dict] = []

    async def _fake(db, user_id, user_role, acao, entidade,
                    registro_id=None, detalhes=None, **kw):
        registros.append({"user_id": user_id, "acao": acao,
                          "entidade": entidade, "detalhes": detalhes})

    monkeypatch.setattr(cv, "criar_audit_log", _fake)
    monkeypatch.setattr(svc, "criar_audit_log", _fake)
    return registros


@pytest.fixture
def montar():
    """Fábrica de app com router real + get_db/get_current_user substituídos.

    O engine SQLite é criado aqui, mas o DDL roda LAZY dentro do loop do
    TestClient (primeira request) — evita cruzar loops com o aiosqlite."""
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


def _reauth(**extra) -> dict:
    return {"senha_atual": SENHA, **extra}


# ── RBAC: admin não opera o cofre ────────────────────────────────────────────

def test_rbac_admin_403_superadmin_ok(montar):
    app, estado = montar(_user(UserRole.admin))
    with TestClient(app) as client:
        assert client.get(BASE).status_code == 403
        assert client.post(URL_DATAJUD,
                           json=_reauth(valor=SEGREDO)).status_code == 403
        assert client.request("DELETE", URL_DATAJUD,
                              json=_reauth()).status_code == 403
        assert client.post(f"{BASE}/importar-env",
                           json=_reauth()).status_code == 403
        assert client.get(f"{URL_DATAJUD}/historico").status_code == 403

        estado["user"] = _user()             # superadmin passa
        r = client.get(BASE)
        assert r.status_code == 200
        providers = {p["provider_key"] for p in r.json()}
        assert "datajud" in providers and "smtp" in providers


# ── Step-up: senha errada → 403 + audit + sem efeito ─────────────────────────

def test_reauth_senha_errada_403_sem_efeito(montar, audit, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "DATAJUD_API_KEY", "valor-do-env")

    app, _ = montar(_user())
    with TestClient(app) as client:
        r = client.post(URL_DATAJUD,
                        json={"senha_atual": "senha-errada", "valor": SEGREDO})
        assert r.status_code == 403
        assert SEGREDO not in r.text
        # Mensagem genérica (anti-oráculo): a resposta não revela QUE foi a senha.
        assert r.json()["detail"] == "Reautenticação falhou."

        # Auditoria da falha, sem detalhes sensíveis (nem senha, nem valor) —
        # mas COM o motivo granular (só no audit, nunca no corpo HTTP).
        falhas = [a for a in audit if a["acao"] == "COFRE_REAUTH_FALHA"]
        assert len(falhas) == 1
        assert falhas[0]["entidade"] == "integration_credentials"
        assert "motivo=senha" in (falhas[0]["detalhes"] or "")
        assert "senha-errada" not in (falhas[0]["detalhes"] or "")
        assert SEGREDO not in (falhas[0]["detalhes"] or "")

        # SEM efeito: nada gravado, Settings intacto.
        campos = {c["field_key"]: c for p in client.get(BASE).json()
                  for c in p["campos"]}
        assert campos["DATAJUD_API_KEY"]["estado"] == "ausente"
    assert settings.DATAJUD_API_KEY == "valor-do-env"


def test_totp_exigido_quando_ativo(montar, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "DATAJUD_API_KEY", "valor-do-env")

    app, _ = montar(_user(totp=True))
    with TestClient(app) as client:
        # Sem código → 403 (senha certa não basta com 2FA ativo).
        assert client.post(URL_DATAJUD,
                           json=_reauth(valor=SEGREDO)).status_code == 403
        # Código errado → 403.
        valido = pyotp.TOTP(TOTP_SECRET).now()
        errado = "000000" if valido != "000000" else "111111"
        assert client.post(
            URL_DATAJUD, json=_reauth(valor=SEGREDO, codigo_totp=errado),
        ).status_code == 403
        assert settings.DATAJUD_API_KEY == "valor-do-env"   # sem efeito

        # Código válido → cadastra e aplica o overlay.
        r = client.post(URL_DATAJUD,
                        json=_reauth(valor=SEGREDO, codigo_totp=valido))
        assert r.status_code == 201
    assert settings.DATAJUD_API_KEY == SEGREDO


def test_reauth_mensagem_generica_nao_distingue_fator(montar, audit):
    """Anti-oráculo: senha errada e TOTP ausente devem devolver EXATAMENTE a
    mesma mensagem 403 (não revela se a senha estava certa e só faltou o TOTP);
    o motivo granular fica SÓ no audit."""
    app, estado = montar(_user())          # sem TOTP → falha por senha
    with TestClient(app) as client:
        r_senha = client.post(
            URL_DATAJUD, json={"senha_atual": "errada", "valor": SEGREDO})

        estado["user"] = _user(totp=True)  # com TOTP → falha por TOTP ausente
        r_totp = client.post(URL_DATAJUD, json=_reauth(valor=SEGREDO))

    assert r_senha.status_code == r_totp.status_code == 403
    assert r_senha.json()["detail"] == r_totp.json()["detail"] == \
        "Reautenticação falhou."
    # O motivo distinto existe, mas apenas na trilha de auditoria.
    motivos = {a["detalhes"].split("motivo=")[-1]
               for a in audit if a["acao"] == "COFRE_REAUTH_FALHA"}
    assert motivos == {"senha", "totp_ausente"}


def test_overlay_falho_apos_cadastro_sinaliza_sem_silencio(montar, audit,
                                                           monkeypatch):
    """Inconsistência gravado-mas-não-aplicado: a linha commita, mas o overlay
    estoura DEPOIS. A operação NÃO é revertida (201), a resposta traz
    overlay_aplicado=False e um audit COFRE_OVERLAY_FALHA (sem segredo) é
    gravado — nunca uma falha silenciosa."""
    async def _boom(_db):
        raise RuntimeError("overlay explodiu (ex.: settings inacessível)")

    monkeypatch.setattr(cv.credential_vault_service, "aplicar_overlay", _boom)

    app, _ = montar(_user())
    with TestClient(app) as client:
        r = client.post(URL_DATAJUD, json=_reauth(valor=SEGREDO))
        assert r.status_code == 201                  # NÃO reverte a escrita
        assert r.json()["overlay_aplicado"] is False
        assert SEGREDO not in r.text

        # A linha ficou gravada (estado eventualmente consistente).
        campos = {c["field_key"]: c for p in client.get(BASE).json()
                  for c in p["campos"]}
        assert campos["DATAJUD_API_KEY"]["estado"] == "configurada"

    # Sinalização para reconciliação: audit COFRE_OVERLAY_FALHA sem segredo.
    overlay_falhas = [a for a in audit if a["acao"] == "COFRE_OVERLAY_FALHA"]
    assert len(overlay_falhas) == 1
    assert overlay_falhas[0]["entidade"] == "integration_credentials"
    assert SEGREDO not in (overlay_falhas[0]["detalhes"] or "")
    assert "overlay explodiu" not in (overlay_falhas[0]["detalhes"] or "")


# ── Cadastro: overlay na MESMA request + resposta só com metadados ───────────

def test_cadastro_aplica_overlay_na_mesma_request(montar, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "DATAJUD_API_KEY", "valor-do-env")

    app, _ = montar(_user())
    with TestClient(app) as client:
        r = client.post(URL_DATAJUD, json=_reauth(valor=SEGREDO))
        assert r.status_code == 201
        body = r.json()
        assert body["last4"] == SEGREDO[-4:] and body["versao"] == 1
        assert body["ativo"] is True and body["origem"] == "manual"
        assert "valor" not in body and "valor_encrypted" not in body
        assert SEGREDO not in r.text                 # valor nunca ecoado

        # Overlay aplicado ANTES da resposta — requisito da auditoria.
        assert settings.DATAJUD_API_KEY == SEGREDO

        # GET agrupado reflete o estado configurado (sem valor).
        r2 = client.get(BASE)
        assert SEGREDO not in r2.text
        campos = {c["field_key"]: c for p in r2.json() for c in p["campos"]}
        assert campos["DATAJUD_API_KEY"]["estado"] == "configurada"
        assert campos["DATAJUD_API_KEY"]["last4"] == SEGREDO[-4:]
        assert campos["SMTP_PASSWORD"]["estado"] == "ausente"
        assert campos["SMTP_PASSWORD"]["rotulo"]     # campos esperados do catálogo


def test_corrida_integrityerror_vira_409(montar, monkeypatch):
    async def _boom(*a, **k):
        raise IntegrityError("stmt", {}, Exception("uq ativo"))

    monkeypatch.setattr(cv.credential_vault_service, "cadastrar", _boom)
    app, _ = montar(_user())
    with TestClient(app) as client:
        r = client.post(URL_DATAJUD, json=_reauth(valor=SEGREDO))
    assert r.status_code == 409
    assert SEGREDO not in r.text


def test_validacao_valueerror_vira_422_e_catalogo_404(montar):
    app, _ = montar(_user())
    with TestClient(app) as client:
        # espaço em api_key → ValueError de formato do service → 422
        r = client.post(URL_DATAJUD, json=_reauth(valor="tem espaco aqui"))
        assert r.status_code == 422
        assert "tem espaco aqui" not in r.text       # mensagem não ecoa o valor
        # provider/field fora do catálogo → 404 (nunca setattr arbitrário)
        assert client.post(f"{BASE}/acme/CAMPO_QUALQUER",
                           json=_reauth(valor=SEGREDO)).status_code == 404
        assert client.get(f"{BASE}/acme/CAMPO_QUALQUER/historico"
                          ).status_code == 404


# ── Revogar ──────────────────────────────────────────────────────────────────

def test_revogar_404_sem_ativa_e_zera_settings_quando_ok(montar, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "DATAJUD_API_KEY", "valor-do-env")

    app, _ = montar(_user())
    with TestClient(app) as client:
        # Sem credencial ativa → 404.
        assert client.request("DELETE", URL_DATAJUD,
                              json=_reauth()).status_code == 404

        client.post(URL_DATAJUD, json=_reauth(valor=SEGREDO))
        assert settings.DATAJUD_API_KEY == SEGREDO

        r = client.request("DELETE", URL_DATAJUD, json=_reauth())
        assert r.status_code == 200
        body = r.json()
        assert body["ativo"] is False and body["revoked_at"] is not None
        assert SEGREDO not in r.text
    # Revogada → "" na MESMA request (sem fallback ao .env).
    assert settings.DATAJUD_API_KEY == ""


# ── importar-env ─────────────────────────────────────────────────────────────

def test_importar_env_resumo_sem_valores(montar, monkeypatch):
    settings = get_settings()
    for fk in cv.credential_registry.todos_field_keys():
        monkeypatch.setattr(settings, fk, "")
    monkeypatch.setattr(settings, "DATAJUD_API_KEY", "env-datajud-123456")

    app, _ = montar(_user())
    with TestClient(app) as client:
        r = client.post(f"{BASE}/importar-env", json=_reauth())
        assert r.status_code == 200
        assert "env-datajud-123456" not in r.text
        body = r.json()
        assert body["total"] == 1
        assert body["importados"] == [{
            "provider": "datajud", "field": "DATAJUD_API_KEY", "last4": "3456",
        }]
        # Overlay na mesma request: valor importado segue vigente via cofre.
        assert settings.DATAJUD_API_KEY == "env-datajud-123456"


# ── Histórico: só metadados ──────────────────────────────────────────────────

def test_historico_so_metadados(montar, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "DATAJUD_API_KEY", "valor-do-env")
    novo = "sk-router-cofre-9999wxyz"

    app, _ = montar(_user())
    with TestClient(app) as client:
        client.post(URL_DATAJUD, json=_reauth(valor=SEGREDO))
        client.post(URL_DATAJUD, json=_reauth(valor=novo))

        r = client.get(f"{URL_DATAJUD}/historico")
        assert r.status_code == 200
        for segredo in (SEGREDO, novo):
            assert segredo not in r.text
        versoes = r.json()
        assert [v["versao"] for v in versoes] == [2, 1]
        assert [v["ativo"] for v in versoes] == [True, False]
        assert versoes[0]["last4"] == novo[-4:]
        for v in versoes:
            assert "valor" not in v and "valor_encrypted" not in v


# ── Varredura: NENHUMA resposta contém o valor cadastrado ────────────────────

def test_nenhuma_resposta_contem_o_valor(montar, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "DATAJUD_API_KEY", "valor-do-env")

    app, _ = montar(_user())
    with TestClient(app) as client:
        respostas = [
            client.post(URL_DATAJUD, json=_reauth(valor=SEGREDO)),
            client.get(BASE),
            client.get(f"{URL_DATAJUD}/historico"),
            client.request("DELETE", URL_DATAJUD, json=_reauth()),
            client.get(BASE),
            client.get(f"{URL_DATAJUD}/historico"),
        ]
    for r in respostas:
        assert r.status_code in (200, 201), r.text
        assert SEGREDO not in r.text                 # corpo inteiro, não só campos


# ── Rate limit nas rotas mutadoras ───────────────────────────────────────────

def test_rate_limit_5_por_minuto_nas_mutadoras(montar):
    app, _ = montar(_user())
    with TestClient(app) as client:
        # Senha errada de propósito: a cota é consumida pela dependency ANTES
        # do handler — 5× 403 e a 6ª estoura em 429 sem tocar o banco.
        for _ in range(5):
            assert client.post(
                URL_DATAJUD,
                json={"senha_atual": "x", "valor": SEGREDO},
            ).status_code == 403
        r = client.post(URL_DATAJUD,
                        json={"senha_atual": "x", "valor": SEGREDO})
        assert r.status_code == 429
        assert "Retry-After" in r.headers
        # A cota é compartilhada entre as mutadoras (mesmo nome de rota).
        assert client.request("DELETE", URL_DATAJUD,
                              json=_reauth()).status_code == 429
        assert client.post(f"{BASE}/importar-env",
                           json=_reauth()).status_code == 429
        # Leitura NÃO é limitada.
        assert client.get(BASE).status_code == 200
