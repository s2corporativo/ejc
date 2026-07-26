"""Auditoria de segurança pré-produção — cobre os endurecimentos desta rodada.

1. Refresh: detecção de REUSO de token (JTI revogado/desconhecido → revoga
   TODAS as sessões do usuário + audita) sem punir expiração natural.
2. TOTP: segredo cifrado em repouso (Fernet/pii_crypto) com fallback para
   segredo legado em claro + re-cifragem oportunista.
3. Login 2FA: o passo "TOTP obrigatório" (senha válida sem código) conta no
   anti-brute-force — antes era oráculo de credenciais sem custo.
4. Drive upload: mesma validação de conteúdo do /documents/upload (extensão +
   magic bytes + MIME derivado do servidor, nunca o content_type do cliente).
5. Config: SECRET_KEY exige >= 32 chars em produção.

Fakes de DB no padrão de test_bloco6_auth.py (endpoints reais via TestClient,
IP/e-mail únicos por teste para isolar os contadores anti-brute-force).
"""
from __future__ import annotations

import io
import types
from datetime import datetime, timedelta, timezone

import pyotp
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from starlette.datastructures import Headers
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import get_password_hash, create_refresh_token
from app.models.audit_log import AuditLog
from app.models.user import RefreshToken
from app.routers import auth as auth_router
from app.services import pii_crypto


# ── Fakes ─────────────────────────────────────────────────────────────────────

class _Res:
    def __init__(self, one=None):
        self._one = one

    def scalar_one_or_none(self):
        return self._one


class _FakeDB:
    """Devolve resultados na ordem da fila `results` (um por execute)."""

    def __init__(self, results=None):
        self.results = list(results or [])
        self.added = []
        self.committed = 0
        self.executed = []

    async def execute(self, stmt, *a, **k):
        self.executed.append(stmt)
        return _Res(self.results.pop(0) if self.results else None)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed += 1


def _montar(db: _FakeDB):
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(auth_router.router)
    app.dependency_overrides[get_db] = lambda: db
    return app


def _hdr(ip: str) -> dict:
    return {"X-Forwarded-For": ip}


def _audits(db: _FakeDB) -> list[AuditLog]:
    return [o for o in db.added if isinstance(o, AuditLog)]


def _record(revoked: bool = False, expirado: bool = False,
            replaced_by_jti: str | None = None,
            revoked_at: datetime | None = None) -> RefreshToken:
    delta = timedelta(days=-1 if expirado else 7)
    return RefreshToken(
        id="rt1", user_id="u1", jti="j-old", revoked=revoked,
        expires_at=datetime.now(timezone.utc) + delta,
        revoked_at=revoked_at, replaced_by_jti=replaced_by_jti,
    )


# ── 1. Refresh — detecção de reuso ────────────────────────────────────────────

def test_refresh_reuso_de_token_rotacionado_revoga_todas_sessoes_e_audita():
    """Replay de token já ROTACIONADO (replaced_by_jti) fora da graça = furto."""
    token, _ = create_refresh_token("u1")
    fora_da_graca = datetime.now(timezone.utc) - timedelta(hours=1)
    db = _FakeDB(results=[_record(
        revoked=True, replaced_by_jti="j-novo", revoked_at=fora_da_graca)])
    client = TestClient(_montar(db))
    r = client.post("/auth/refresh", json={"refresh_token": token},
                    headers=_hdr("10.30.0.1"))
    assert r.status_code == 401
    # 2 execute: SELECT do JTI + UPDATE revoga-tudo do usuário.
    assert len(db.executed) == 2
    assert db.committed == 1
    logs = _audits(db)
    assert len(logs) == 1 and logs[0].acao == "REFRESH_REUSE"
    assert logs[0].user_id == "u1"


def test_refresh_revogado_por_logout_ou_troca_de_senha_nao_pune():
    """Token revogado SEM replaced_by_jti (logout/troca de senha) vindo de um
    dispositivo antigo legítimo: 401 simples, sem cascata e sem REFRESH_REUSE —
    não derruba a sessão nova emitida pelo alterar-senha. M-S3: o replay ainda
    deixa trilha leve REFRESH_REPLAY_POS_LOGOUT (forense), sem punição."""
    token, _ = create_refresh_token("u1")
    db = _FakeDB(results=[_record(
        revoked=True, revoked_at=datetime.now(timezone.utc))])
    client = TestClient(_montar(db))
    r = client.post("/auth/refresh", json={"refresh_token": token},
                    headers=_hdr("10.30.0.9"))
    assert r.status_code == 401
    assert "Sessão encerrada" in r.json()["detail"]
    assert len(db.executed) == 1          # só o SELECT do JTI — sem revoga-tudo
    logs = _audits(db)
    assert len(logs) == 1 and logs[0].acao == "REFRESH_REPLAY_POS_LOGOUT"
    assert logs[0].user_id == "u1"
    assert db.committed == 1              # trilha persistida antes do 401


def test_refresh_jti_desconhecido_tambem_e_reuso():
    """Token criptograficamente válido sem registro no banco = replay."""
    token, _ = create_refresh_token("u1")
    db = _FakeDB(results=[None])
    client = TestClient(_montar(db))
    r = client.post("/auth/refresh", json={"refresh_token": token},
                    headers=_hdr("10.30.0.2"))
    assert r.status_code == 401
    assert len(db.executed) == 2          # SELECT + UPDATE revoga-tudo
    assert any(l.acao == "REFRESH_REUSE" for l in _audits(db))


def test_refresh_expirado_naturalmente_nao_pune():
    token, _ = create_refresh_token("u1")
    db = _FakeDB(results=[_record(expirado=True)])
    client = TestClient(_montar(db))
    r = client.post("/auth/refresh", json={"refresh_token": token},
                    headers=_hdr("10.30.0.3"))
    assert r.status_code == 401
    assert len(db.executed) == 1          # só o SELECT — sem revoga-tudo
    assert db.committed == 0 and not _audits(db)


def test_refresh_valido_rotaciona_normalmente(monkeypatch):
    # "advogado" entrou no default de REQUIRE_2FA_ROLES; sem isto o /auth/refresh
    # tocaria o ramo de 2FA (totp_enabled, ausente no fake). Teste é sobre rotação.
    monkeypatch.setattr(auth_router.settings, "REQUIRE_2FA_ROLES", "")
    token, _ = create_refresh_token("u1")
    user = types.SimpleNamespace(
        id="u1", role=types.SimpleNamespace(value="advogado"),
        must_change_password=False,
    )
    db = _FakeDB(results=[_record(), user])
    client = TestClient(_montar(db))
    r = client.post("/auth/refresh", json={"refresh_token": token},
                    headers=_hdr("10.30.0.4"))
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"] and body["refresh_token"] != token
    # Novo RefreshToken persistido; nenhum audit de reuso.
    assert any(isinstance(o, RefreshToken) for o in db.added)
    assert not _audits(db)


def test_refresh_token_lixo_401_sem_tocar_banco():
    db = _FakeDB()
    client = TestClient(_montar(db))
    r = client.post("/auth/refresh", json={"refresh_token": "lixo"},
                    headers=_hdr("10.30.0.5"))
    assert r.status_code == 401
    assert db.executed == [] and db.committed == 0


# ── 2. TOTP — segredo cifrado em repouso + fallback legado ───────────────────

def test_totp_secret_de_cifrado_e_legado():
    secret = pyotp.random_base32()
    u_cifrado = types.SimpleNamespace(totp_secret=pii_crypto.encrypt(secret))
    assert auth_router._totp_secret_de(u_cifrado) == (secret, False)
    u_legado = types.SimpleNamespace(totp_secret=secret)
    assert auth_router._totp_secret_de(u_legado) == (secret, True)


def _user_totp(secret_armazenado: str):
    return types.SimpleNamespace(
        id="u1", role=types.SimpleNamespace(value="advogado"),
        hashed_password=get_password_hash("senha-correta"),
        totp_enabled=True, totp_secret=secret_armazenado,
        must_change_password=False, full_name="Fulano",
        email="totp@teste.com", last_login_at=None,
    )


def _login(client, ip, code=None, email="totp@teste.com"):
    payload = {"email": email, "password": "senha-correta"}
    if code is not None:
        payload["totp_code"] = code
    return client.post("/auth/login", json=payload, headers=_hdr(ip))


def test_login_totp_com_segredo_cifrado():
    secret = pyotp.random_base32()
    user = _user_totp(pii_crypto.encrypt(secret))
    db = _FakeDB(results=[user, user])   # credenciais + verificar_novo_dispositivo
    client = TestClient(_montar(db))
    r = _login(client, "10.31.0.1", code=pyotp.TOTP(secret).now())
    assert r.status_code == 200
    assert r.json()["access_token"]


def test_login_totp_legado_em_claro_funciona_e_recifra():
    secret = pyotp.random_base32()
    user = _user_totp(secret)            # legado: em claro no "banco"
    db = _FakeDB(results=[user, user])
    client = TestClient(_montar(db))
    r = _login(client, "10.31.0.2", code=pyotp.TOTP(secret).now())
    assert r.status_code == 200
    # Re-cifragem oportunista: o valor armazenado deixou de ser o claro e
    # decifra de volta para o segredo original.
    assert user.totp_secret != secret
    assert pii_crypto.decrypt(user.totp_secret) == secret


def test_login_totp_codigo_invalido_401():
    secret = pyotp.random_base32()
    user = _user_totp(pii_crypto.encrypt(secret))
    db = _FakeDB(results=[user])
    client = TestClient(_montar(db))
    r = _login(client, "10.31.0.3", code="000000")
    assert r.status_code == 401


# ── 3. Passo "TOTP obrigatório" — contador PRÓPRIO (totp_pend), teto maior ───
# Item 5 (go-live): o fluxo em 2 etapas do frontend SEMPRE faz o 1º POST sem
# totp_code, então esse passo NÃO pode consumir o orçamento principal do login
# (ip:/em: 5/15min) — 5 usuários TOTP no mesmo IP de escritório = 429 geral.
# Contador separado totp_pend:{ip} (teto 20/15min) ainda limita a sondagem de
# senhas válidas, e o audit LOGIN_TOTP_PENDENTE preserva a trilha.

def test_login_sem_codigo_totp_nao_consome_orcamento_principal():
    from app.services.security_service import esta_bloqueado, registrar_falha

    secret = pyotp.random_base32()
    user = _user_totp(pii_crypto.encrypt(secret))
    user.email = "totp-bf@teste.com"
    db = _FakeDB(results=[user] * 10)
    client = TestClient(_montar(db))
    ip = "10.31.0.99"

    codes = [_login(client, ip, email="totp-bf@teste.com").status_code
             for _ in range(6)]
    # Antes: a 6ª tentativa era 429 (orçamento principal). Agora as 6 passam
    # pelo passo pendente (401) sem tocar ip:/em:.
    assert codes == [401] * 6
    assert esta_bloqueado(f"ip:{ip}") == (False, 0)
    assert esta_bloqueado("em:totp-bf@teste.com") == (False, 0)
    assert any(l.acao == "LOGIN_TOTP_PENDENTE" for l in _audits(db))

    # Teto do contador próprio (20/15min): completa 19 falhas pré-semeadas +
    # 1 request real = 20 → a próxima é 429 (sem passar do limiter 10/min).
    for _ in range(13):        # 6 já registradas acima
        registrar_falha(f"totp_pend:{ip}")
    r_20 = _login(client, ip, email="totp-bf@teste.com")
    assert r_20.status_code == 401          # 20ª ainda passa
    r_21 = _login(client, ip, email="totp-bf@teste.com")
    assert r_21.status_code == 429          # 21ª bloqueada pelo teto próprio
    # E mesmo bloqueado o passo pendente, o orçamento do login segue intacto.
    assert esta_bloqueado(f"ip:{ip}") == (False, 0)


def test_login_totp_codigo_errado_continua_no_orcamento_principal():
    """Código TOTP ERRADO (≠ passo pendente) segue contando em ip:/em:."""
    from app.services.security_service import esta_bloqueado

    secret = pyotp.random_base32()
    user = _user_totp(pii_crypto.encrypt(secret))
    user.email = "totp-errado@teste.com"
    db = _FakeDB(results=[user] * 10)
    client = TestClient(_montar(db))
    ip = "10.31.0.98"

    for _ in range(5):
        assert _login(client, ip, code="000000",
                      email="totp-errado@teste.com").status_code == 401
    bloqueado, _seg = esta_bloqueado("em:totp-errado@teste.com")
    assert bloqueado
    assert _login(client, ip, code="000000",
                  email="totp-errado@teste.com").status_code == 429


# ── 4. Drive upload — validação de conteúdo (item 2) ─────────────────────────

def _upload_file(nome: str, conteudo: bytes, content_type: str):
    return StarletteUploadFile(
        io.BytesIO(conteudo), filename=nome,
        headers=Headers({"content-type": content_type}),
    )


def _cu():
    return types.SimpleNamespace(id="u1", role=types.SimpleNamespace(value="socio"))


async def test_drive_upload_extensao_proibida_422():
    from app.routers.documents import upload_para_drive

    with pytest.raises(HTTPException) as exc:
        await upload_para_drive(
            file=_upload_file("virus.exe", b"MZ\x90\x00", "application/octet-stream"),
            case_id=None, descricao=None, db=_FakeDB(), current_user=_cu(),
        )
    assert exc.value.status_code == 422


async def test_drive_upload_conteudo_diverge_da_extensao_415():
    from app.routers.documents import upload_para_drive

    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    with pytest.raises(HTTPException) as exc:
        await upload_para_drive(
            file=_upload_file("laudo.pdf", png, "application/pdf"),
            case_id=None, descricao=None, db=_FakeDB(), current_user=_cu(),
        )
    assert exc.value.status_code == 415


async def test_drive_upload_persiste_mime_do_servidor(monkeypatch):
    """Content-type do cliente (text/html → XSS armazenado no download-proxy)
    é IGNORADO: persiste o MIME derivado dos magic bytes."""
    from app.routers import documents as docs_mod

    monkeypatch.setattr(
        docs_mod.gd, "upload_file",
        # assinatura real: upload_file(content, filename, mime_type, folder_id=None, subfolder=None)
        lambda content, nome, mime, folder_id=None, subfolder=None: {"id": "drv1", "webViewLink": "http://x"},
    )

    class _DB(_FakeDB):
        def __init__(self):
            super().__init__()
            self.params = None

        async def execute(self, stmt, params=None, *a, **k):
            self.params = params
            return _Res(None)

    db = _DB()
    pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF"
    resp = await docs_mod.upload_para_drive(
        file=_upload_file("contrato.pdf", pdf, "text/html"),
        case_id=None, descricao=None, db=db, current_user=_cu(),
    )
    assert resp["drive_file_id"] == "drv1"
    assert db.params["mimetype"] == "application/pdf"   # nunca text/html


# ── 5. Config — SECRET_KEY mínima em produção ────────────────────────────────

def _prod_kwargs(**over):
    from cryptography.fernet import Fernet

    base = dict(
        APP_ENV="production",
        SECRET_KEY="s" * 64,
        PII_ENCRYPTION_KEY=Fernet.generate_key().decode(),
        PII_HASH_KEY="h" * 32,
        # Cofre de Credenciais (migration 108): obrigatória em produção,
        # mesmo padrão do PII_ENCRYPTION_KEY.
        VAULT_MASTER_KEYS=Fernet.generate_key().decode(),
        FRONTEND_URL="https://app.exemplo.adv.br",
        CORS_ORIGINS="https://app.exemplo.adv.br",
    )
    base.update(over)
    return base


def test_producao_recusa_secret_key_curta():
    from app.core.config import Settings

    with pytest.raises(ValueError, match="SECRET_KEY muito curta"):
        Settings(**_prod_kwargs(SECRET_KEY="curta-demais"))


def test_producao_aceita_secret_key_32_chars():
    from app.core.config import Settings

    s = Settings(**_prod_kwargs(SECRET_KEY="k" * 32))
    assert s.SECRET_KEY == "k" * 32


def test_desenvolvimento_nao_exige_tamanho():
    from app.core.config import Settings

    s = Settings(APP_ENV="development", SECRET_KEY="curta")
    assert s.SECRET_KEY == "curta"
