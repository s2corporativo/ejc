"""P0 usabilidade (relatório 2026-07-18, §10) — backend.

Cobre:
1. GET /ia/status — {"disponivel", "mensagem"} por configuração (sem rede);
2. Tradução de erros de IA para mensagem leiga (core.ai_errors);
3. POST /auth/recuperar-senha com SMTP desligado → orientação leiga (sem
   vazar existência de conta);
4. POST /auth/alterar-senha → mantém a sessão (novos tokens, claim limpo);
5. POST /intake/casos/{id}/analise-completa sem IA → payload degradado
   explícito (nunca mais objetos {nome, endpoint} soltos).
"""
from __future__ import annotations

import types

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from app.core.ai_errors import (
    MSG_IA_INDISPONIVEL,
    MSG_IA_NAO_ATIVADA,
    MSG_IA_NAO_ATIVADA_CURTA,
    MSG_PII_BLOQUEADA,
    MSG_TRANSCRICAO_NAO_ATIVADA,
    http_erro_ia,
    mensagem_ia_para_usuario,
)
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import create_access_token, decode_token, get_password_hash
from app.routers import auth as auth_router


class _User:
    id = "u-p0"
    role = types.SimpleNamespace(value="advogado")


# ── Helpers de configuração de provedores (ai_gateway.settings) ───────────────

def _sem_provedores(monkeypatch):
    from app.services import ai_gateway as gw
    monkeypatch.setattr(gw.settings, "AI_ENABLED", True, raising=False)
    monkeypatch.setattr(gw.settings, "OLLAMA_ENABLED", False, raising=False)
    monkeypatch.setattr(gw.settings, "ANTHROPIC_API_KEY", "", raising=False)
    monkeypatch.setattr(gw.settings, "GROQ_API_KEY", "", raising=False)
    monkeypatch.setattr(gw.settings, "MARITACA_ENABLED", False, raising=False)


def _com_groq(monkeypatch):
    from app.services import ai_gateway as gw
    monkeypatch.setattr(gw.settings, "AI_ENABLED", True, raising=False)
    monkeypatch.setattr(gw.settings, "AI_EXTERNAL_PROVIDERS_ALLOWED", True, raising=False)
    monkeypatch.setattr(gw.settings, "GROQ_API_KEY", "gsk_teste", raising=False)


# ── 1) GET /ia/status ─────────────────────────────────────────────────────────

async def test_ia_status_com_provedor_configurado(monkeypatch):
    _com_groq(monkeypatch)
    from app.routers.ia_saude import ia_status
    r = await ia_status(cu=_User())
    assert r == {"disponivel": True, "mensagem": None}


async def test_ia_status_sem_provedor(monkeypatch):
    _sem_provedores(monkeypatch)
    from app.routers.ia_saude import ia_status
    r = await ia_status(cu=_User())
    assert r["disponivel"] is False
    assert r["mensagem"] == MSG_IA_NAO_ATIVADA
    # Mensagem leiga: nada de jargão de infraestrutura.
    for jargao in (".env", "API_KEY", "Ollama", "provider"):
        assert jargao.lower() not in r["mensagem"].lower()


async def test_ia_status_ai_enabled_false_desativa(monkeypatch):
    from app.services import ai_gateway as gw
    _com_groq(monkeypatch)
    monkeypatch.setattr(gw.settings, "AI_ENABLED", False, raising=False)
    assert gw.ia_disponivel() is False


# ── 2) Tradução de erros de IA ────────────────────────────────────────────────

def test_erro_provedores_falharam_vira_mensagem_leiga():
    tecnico = ("Todos os provedores falharam para task=estrategia. "
               "Último erro: Ollama indisponível: [Errno -2] Name or service not known")
    assert mensagem_ia_para_usuario(tecnico) == MSG_IA_INDISPONIVEL


def test_erro_pii_vira_mensagem_leiga():
    tecnico = ("Conteúdo com dados pessoais não pode ir a provider externo — "
               "configure Ollama ou revise o texto")
    assert mensagem_ia_para_usuario(tecnico) == MSG_PII_BLOQUEADA


def test_erro_transcricao_sem_chave_vira_mensagem_leiga():
    assert (mensagem_ia_para_usuario("GROQ_API_KEY não configurada para transcrição.")
            == MSG_TRANSCRICAO_NAO_ATIVADA)


def test_mensagem_de_negocio_legivel_passa_intacta():
    msg = "Texto insuficiente para análise (envie documentos ou 'texto')"
    assert mensagem_ia_para_usuario(msg) == msg


def test_http_erro_ia_nao_vaza_detalhe_tecnico():
    exc = RuntimeError("Todos os provedores falharam para task=resumo. "
                       "Último erro: connection refused localhost:11434")
    http = http_erro_ia(exc, 502, contexto="teste")
    assert isinstance(http, HTTPException)
    assert http.status_code == 502
    assert http.detail == MSG_IA_INDISPONIVEL
    for jargao in ("task=", "localhost", "connection", "provedores"):
        assert jargao not in http.detail


# ── Infra fake p/ endpoints de auth (padrão de test_bloco6_auth.py) ───────────

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

    async def execute(self, *a, **k):
        return _Res(self._user)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed += 1


def _montar_auth(user=None):
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(auth_router.router)
    db = _FakeDB(user)
    app.dependency_overrides[get_db] = lambda: db
    return app, db


# ── 3) Recuperar senha sem SMTP ───────────────────────────────────────────────

def test_recuperar_senha_sem_smtp_orienta_procurar_admin(monkeypatch):
    monkeypatch.setattr(auth_router.settings, "EMAIL_ENABLED", False, raising=False)
    chamado = {"n": 0}

    async def fake_reset(*a, **k):
        chamado["n"] += 1

    monkeypatch.setattr(auth_router, "solicitar_reset", fake_reset)
    app, _ = _montar_auth()
    client = TestClient(app)
    r = client.post("/auth/recuperar-senha",
                    json={"email": "qualquer@teste.com"},
                    headers={"X-Forwarded-For": "10.55.0.1"})
    assert r.status_code == 200
    assert r.json()["detail"] == (
        "O envio de e-mail não está configurado nesta instalação. "
        "Procure o administrador do escritório para redefinir sua senha."
    )
    # Sem SMTP não gera token de reset (e a resposta independe do e-mail existir).
    assert chamado["n"] == 0


def test_recuperar_senha_com_smtp_mantem_resposta_neutra(monkeypatch):
    monkeypatch.setattr(auth_router.settings, "EMAIL_ENABLED", True, raising=False)
    monkeypatch.setattr(auth_router.settings, "SMTP_USER", "ejc@teste.com", raising=False)
    chamado = {"n": 0}

    async def fake_reset(*a, **k):
        chamado["n"] += 1

    monkeypatch.setattr(auth_router, "solicitar_reset", fake_reset)
    app, _ = _montar_auth()
    client = TestClient(app)
    r = client.post("/auth/recuperar-senha",
                    json={"email": "existe@teste.com"},
                    headers={"X-Forwarded-For": "10.55.0.2"})
    assert r.status_code == 200
    assert r.json()["detail"] == "Se o e-mail existir, enviaremos as instruções em breve."
    assert chamado["n"] == 1


# ── 4) Alterar senha mantém a sessão (novos tokens) ───────────────────────────

def test_alterar_senha_retorna_tokens_e_limpa_claim(monkeypatch):
    # "advogado" entrou no default de REQUIRE_2FA_ROLES → /auth/alterar-senha
    # tocaria o ramo de 2FA (totp_enabled, ausente no fake). Teste é sobre o
    # contrato de tokens/claim, não 2FA.
    monkeypatch.setattr(auth_router.settings, "REQUIRE_2FA_ROLES", "")
    user = types.SimpleNamespace(
        id="u-troca", role=types.SimpleNamespace(value="advogado"),
        full_name="Dr. Teste",
        email="troca-p0@teste.com",
        hashed_password=get_password_hash("SenhaAtual@1"),
        must_change_password=True,
    )
    app, db = _montar_auth(user)
    client = TestClient(app)
    token = create_access_token(user.id, "advogado", must_change_password=True)
    r = client.post(
        "/auth/alterar-senha",
        json={"senha_atual": "SenhaAtual@1", "nova_senha": "SenhaNova@123"},
        headers={"Authorization": f"Bearer {token}",
                 "X-Forwarded-For": "10.55.0.3"},
    )
    assert r.status_code == 200
    body = r.json()
    # Compat: campo antigo continua existindo.
    assert "detail" in body
    # Contrato novo (mesmo formato do login):
    assert body["token_type"] == "bearer"
    assert body["user_id"] == "u-troca"
    assert body["must_change_password"] is False
    novo_access = decode_token(body["access_token"])
    assert novo_access["sub"] == "u-troca"
    assert novo_access["type"] == "access"
    assert not novo_access.get("pwd_change_required")  # claim limpo
    novo_refresh = decode_token(body["refresh_token"])
    assert novo_refresh["type"] == "refresh"
    # Cookie httpOnly rotacionado com o novo refresh.
    assert client.cookies.get("ejc_refresh") == body["refresh_token"]
    # A nova sessão foi registrada (RefreshToken adicionado) e persistida.
    from app.models.user import RefreshToken
    assert any(isinstance(o, RefreshToken) for o in db.added)
    assert db.committed >= 1
    # A troca de fato aconteceu.
    assert user.must_change_password is False


# ── 5) Análise completa degradada sem IA ──────────────────────────────────────

async def test_analise_completa_sem_ia_payload_degradado(monkeypatch):
    from app.routers import intake
    from app.services import ai_gateway as gw

    caso = types.SimpleNamespace(id="c-p0")

    async def fake_acesso(db, cu, case_id):
        return caso

    monkeypatch.setattr(intake, "verificar_acesso_caso", fake_acesso)
    monkeypatch.setattr(intake, "_pode_usar_ia", lambda cu: True)
    monkeypatch.setattr(gw, "ia_disponivel", lambda: False)

    r = await intake.analise_completa("c-p0", payload=None, db=None, cu=_User())
    assert r == {
        "ia_disponivel": False,
        "case_id": "c-p0",
        "mensagem": MSG_IA_NAO_ATIVADA_CURTA,
    }
    # Nada de estruturas semi-preenchidas que quebravam o frontend.
    assert "modulos_sugeridos" not in r
    assert "estrategia" not in r


async def test_analise_completa_com_ia_mantem_envelope(monkeypatch):
    """Caminho feliz: formato preservado + campo aditivo ia_disponivel=True."""
    from app.routers import intake
    from app.services import ai_gateway as gw

    caso = types.SimpleNamespace(id="c-ok", area=types.SimpleNamespace(value="civel"),
                                 descricao_fatos="", valor_causa=None)

    async def fake_acesso(db, cu, case_id):
        return caso

    async def fake_texto(db, case, payload):
        return ""

    async def fake_area(db, cu, case, payload, texto):
        return {"valor": "civel", "origem": "area_do_caso", "ai_log_id": None}

    async def fake_teses(db, area):
        return []

    async def fake_estrategia(db, cu, case, area, texto, teses):
        return {"recomendada": None, "justificativa": "x", "ai_log_id": None}

    async def fake_honorarios(db, cu, case, area, payload):
        return None, intake.AVISO_SEM_TABELA

    async def fake_modulos(db, area):
        return []

    monkeypatch.setattr(intake, "verificar_acesso_caso", fake_acesso)
    monkeypatch.setattr(intake, "_pode_usar_ia", lambda cu: True)
    monkeypatch.setattr(gw, "ia_disponivel", lambda: True)
    monkeypatch.setattr(intake, "_texto_base", fake_texto)
    monkeypatch.setattr(intake, "_identificar_area", fake_area)
    monkeypatch.setattr(intake, "_buscar_teses", fake_teses)
    monkeypatch.setattr(intake, "_estrategia_recomendada", fake_estrategia)
    monkeypatch.setattr(intake, "_honorarios_referencia", fake_honorarios)
    monkeypatch.setattr(intake, "_modulos_sugeridos", fake_modulos)

    r = await intake.analise_completa("c-ok", payload=None, db=None, cu=_User())
    assert r["ia_disponivel"] is True
    assert r["status"] == "rascunho"
    for campo in ("area", "teses", "estrategia", "honorarios", "modulos_sugeridos"):
        assert campo in r
