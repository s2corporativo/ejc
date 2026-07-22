"""Lote final de correções pré-go-live (code review + re-auditoria + E2E).

1.  Refresh: janela de graça (~60s) para corrida multi-aba — reuso do token da
    ÚLTIMA rotação dentro da graça é 401 simples SEM revogação em massa; fora
    da graça, ou token de rotação mais antiga, mantém a punição total.
9.  Reuso de refresh SEM `sub` no payload também audita (REFRESH_REUSE).
3.  TOTP: segredo indecifrável (PII_ENCRYPTION_KEY rotacionada) → 401
    controlado, nunca 500; re-cifragem oportunista tolera falha de encrypt.
4.  /auth/totp/desativar: bloqueio anti-brute-force com chave PRÓPRIA
    (totp_desativar:{email}) — não tranca o /login da vítima.
2.  Mojibake: forma cp1252 ("Ã‰"/"Ã‡"/"â€”") reparada para o caractere
    CORRETO acentuado, ANTES das substituições de aspas/travessões.
6.  /ai/detectar-prazos: case_id inexistente/sem acesso → 404/403 ANTES da
    chamada de IA (antes: 500 por FK após pagar o custo do gateway).
7.  /documents/drive/*: Drive não configurado → 503 controlado.
8.  Content-Disposition do proxy Drive: filename sanitizado + RFC 5987.
12. GET /signatures/: cada item traz `signatarios` (shape do frontend).

Fakes no padrão de test_auditoria_pre_producao.py. Dados 100% fictícios.
"""
from __future__ import annotations

import io
import types
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import jwt as pyjwt
import pyotp
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from starlette.datastructures import Headers
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import create_access_token, create_refresh_token, get_password_hash
from app.models.audit_log import AuditLog
from app.models.user import RefreshToken, UserRole
from app.routers import auth as auth_router
from app.services import pii_crypto

settings = get_settings()


# ── Fakes ─────────────────────────────────────────────────────────────────────

class _Res:
    def __init__(self, one=None, lista=None):
        self._one = one
        self._lista = lista or []

    def scalar_one_or_none(self):
        return self._one

    def scalars(self):
        return SimpleNamespace(all=lambda: self._lista)

    def all(self):
        return self._lista


class _FakeDB:
    """Devolve resultados na ordem da fila `results` (um por execute)."""

    def __init__(self, results=None):
        self.results = list(results or [])
        self.added = []
        self.committed = 0
        self.executed = []

    async def execute(self, stmt, *a, **k):
        self.executed.append(stmt)
        r = self.results.pop(0) if self.results else None
        return r if isinstance(r, _Res) else _Res(r)

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


def _hdr(ip: str, token: str | None = None) -> dict:
    h = {"X-Forwarded-For": ip}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _audits(db: _FakeDB) -> list[AuditLog]:
    return [o for o in db.added if isinstance(o, AuditLog)]


def _rec(jti="j-old", revoked=True, revoked_at=None, replaced_by=None):
    return RefreshToken(
        id="rt1", user_id="u1", jti=jti, revoked=revoked,
        revoked_at=revoked_at, replaced_by_jti=replaced_by,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )


_AGORA = lambda: datetime.now(timezone.utc)  # noqa: E731


# ── 1. Refresh — janela de graça (corrida multi-aba) ──────────────────────────

def test_refresh_reuso_dentro_da_graca_nao_revoga_sessoes():
    """Corrida benigna: token da ÚLTIMA rotação (substituto ainda ativo),
    revogado há segundos → 401 simples; sessões da vítima intactas."""
    token, _ = create_refresh_token("u1")
    substituto = _rec(jti="j-new", revoked=False)
    db = _FakeDB(results=[
        _rec(revoked=True, revoked_at=_AGORA(), replaced_by="j-new"),
        substituto,
    ])
    client = TestClient(_montar(db))
    r = client.post("/auth/refresh", json={"refresh_token": token},
                    headers=_hdr("10.40.0.1"))
    assert r.status_code == 401
    # 2 SELECTs (registro + substituto), NENHUM UPDATE revoga-tudo,
    # nenhum commit, nenhuma auditoria de reuso, cookie preservado.
    assert len(db.executed) == 2
    assert db.committed == 0 and not _audits(db)
    assert "ejc_refresh" not in r.headers.get("set-cookie", "")


def test_refresh_reuso_fora_da_graca_pune_normalmente():
    token, _ = create_refresh_token("u1")
    db = _FakeDB(results=[
        _rec(revoked=True, revoked_at=_AGORA() - timedelta(seconds=120),
             replaced_by="j-new"),
    ])
    client = TestClient(_montar(db))
    r = client.post("/auth/refresh", json={"refresh_token": token},
                    headers=_hdr("10.40.0.2"))
    assert r.status_code == 401
    # SELECT + UPDATE revoga-tudo (sem consultar substituto: fora da janela).
    assert len(db.executed) == 2
    assert db.committed == 1
    logs = _audits(db)
    assert len(logs) == 1 and logs[0].acao == "REFRESH_REUSE"


def test_refresh_token_de_duas_rotacoes_atras_pune_mesmo_na_janela():
    """O substituto do token JÁ FOI rotacionado (revogado) → não é a última
    rotação → replay real, mesmo com revoked_at recente."""
    token, _ = create_refresh_token("u1")
    substituto_revogado = _rec(jti="j-mid", revoked=True)
    db = _FakeDB(results=[
        _rec(revoked=True, revoked_at=_AGORA(), replaced_by="j-mid"),
        substituto_revogado,
    ])
    client = TestClient(_montar(db))
    r = client.post("/auth/refresh", json={"refresh_token": token},
                    headers=_hdr("10.40.0.3"))
    assert r.status_code == 401
    # SELECT registro + SELECT substituto + UPDATE revoga-tudo.
    assert len(db.executed) == 3
    assert any(l.acao == "REFRESH_REUSE" for l in _audits(db))


def test_refresh_rotacao_grava_metadados_de_graca(monkeypatch):
    # Isola do enforcement organizacional de 2FA: com "advogado" agora no default
    # de REQUIRE_2FA_ROLES, o /auth/refresh entra no ramo de 2FA (lê totp_enabled,
    # ausente no fake). Este teste é sobre rotação de refresh, não 2FA.
    monkeypatch.setattr(auth_router.settings, "REQUIRE_2FA_ROLES", "")
    token, _ = create_refresh_token("u1")
    user = types.SimpleNamespace(
        id="u1", role=types.SimpleNamespace(value="advogado"),
        must_change_password=False,
    )
    antigo = _rec(revoked=False)
    db = _FakeDB(results=[antigo, user])
    client = TestClient(_montar(db))
    r = client.post("/auth/refresh", json={"refresh_token": token},
                    headers=_hdr("10.40.0.4"))
    assert r.status_code == 200
    novo = next(o for o in db.added if isinstance(o, RefreshToken))
    assert antigo.revoked is True
    assert antigo.revoked_at is not None
    assert antigo.replaced_by_jti == novo.jti


# ── 9. Reuso sem `sub` no payload também audita ───────────────────────────────

def test_refresh_reuso_sem_sub_audita_anomalia():
    tok = pyjwt.encode(
        {"type": "refresh", "jti": str(uuid4()),
         "exp": _AGORA() + timedelta(days=7), "iat": _AGORA()},
        settings.SECRET_KEY, algorithm=settings.ALGORITHM,
    )
    db = _FakeDB(results=[None])          # JTI desconhecido
    client = TestClient(_montar(db))
    r = client.post("/auth/refresh", json={"refresh_token": tok},
                    headers=_hdr("10.40.0.5"))
    assert r.status_code == 401
    assert len(db.executed) == 1          # só o SELECT — nada a revogar
    assert db.committed == 1
    logs = _audits(db)
    assert len(logs) == 1 and logs[0].acao == "REFRESH_REUSE"
    assert logs[0].user_id is None
    assert "SEM sub" in (logs[0].detalhes or "")


# ── 3. TOTP — segredo indecifrável nunca 500 ─────────────────────────────────

def _user_totp(secret_armazenado: str, email="totp3@teste.com"):
    return types.SimpleNamespace(
        id="u1", role=types.SimpleNamespace(value="advogado"),
        hashed_password=get_password_hash("senha-correta"),
        totp_enabled=True, totp_secret=secret_armazenado,
        must_change_password=False, full_name="Fulano",
        email=email, last_login_at=None,
    )


def test_login_totp_segredo_cifrado_com_outra_chave_401_nao_500():
    from cryptography.fernet import Fernet

    secret = pyotp.random_base32()
    outra_chave = Fernet(Fernet.generate_key())
    user = _user_totp(outra_chave.encrypt(secret.encode()).decode())
    db = _FakeDB(results=[user])
    client = TestClient(_montar(db))
    r = client.post("/auth/login", json={
        "email": "totp3@teste.com", "password": "senha-correta",
        "totp_code": pyotp.TOTP(secret).now(),
    }, headers=_hdr("10.41.0.1"))
    assert r.status_code == 401           # controlado — nunca 500
    assert "dois fatores" in r.json()["detail"]


def test_recifragem_oportunista_tolera_falha_de_encrypt(monkeypatch):
    """Encrypt falhando (PII_ENCRYPTION_KEY ausente → RuntimeError) não pode
    derrubar um login correto com segredo legado em claro."""
    secret = pyotp.random_base32()
    user = _user_totp(secret, email="totp3b@teste.com")   # legado em claro

    def boom(_valor):
        raise RuntimeError("PII_ENCRYPTION_KEY não configurada")
    monkeypatch.setattr(auth_router.pii_crypto, "encrypt", boom)

    db = _FakeDB(results=[user, user])
    client = TestClient(_montar(db))
    r = client.post("/auth/login", json={
        "email": "totp3b@teste.com", "password": "senha-correta",
        "totp_code": pyotp.TOTP(secret).now(),
    }, headers=_hdr("10.41.0.2"))
    assert r.status_code == 200
    assert user.totp_secret == secret     # mantido em claro, sem quebrar


# ── 4. /auth/totp/desativar — bloqueio com chave própria ─────────────────────

def test_totp_desativar_bloqueia_na_6a_sem_trancar_login_da_vitima(monkeypatch):
    # "advogado" agora é 2FA-obrigado por default → /auth/totp/desativar
    # devolveria 403 (papel obrigado) ANTES do fluxo anti-brute-force que este
    # teste exercita. O bloqueio de papel é coberto em test_seguranca_senha_2fa;
    # aqui isolamos do enforcement organizacional.
    monkeypatch.setattr(auth_router.settings, "REQUIRE_2FA_ROLES", "")
    from app.services.security_service import esta_bloqueado

    secret = pyotp.random_base32()
    user = _user_totp(pii_crypto.encrypt(secret), email="vitima@teste.com")
    access = create_access_token("u1", "advogado")
    db = _FakeDB(results=[user] * 10)
    client = TestClient(_montar(db))
    ip = "10.42.0.1"

    codes = [
        client.post("/auth/totp/desativar", json={"codigo": "000000"},
                    headers=_hdr(ip, access)).status_code
        for _ in range(6)
    ]
    assert codes[:5] == [400] * 5
    assert codes[5] == 429                # 6ª tentativa bloqueada
    # O /login da vítima NÃO foi trancado (chaves ip:/em: intactas)…
    assert esta_bloqueado(f"ip:{ip}") == (False, 0)
    assert esta_bloqueado("em:vitima@teste.com") == (False, 0)
    # …e um login completo dela continua funcionando.
    db.results = [user, user]
    r = client.post("/auth/login", json={
        "email": "vitima@teste.com", "password": "senha-correta",
        "totp_code": pyotp.TOTP(secret).now(),
    }, headers=_hdr(ip))
    assert r.status_code == 200


def test_totp_desativar_codigo_correto_desativa_e_limpa_contador(monkeypatch):
    # Isola do enforcement de 2FA por papel (advogado agora obrigado por default):
    # o foco é o contador anti-brute-force do desativar, não o bloqueio de papel.
    monkeypatch.setattr(auth_router.settings, "REQUIRE_2FA_ROLES", "")
    secret = pyotp.random_base32()
    user = _user_totp(pii_crypto.encrypt(secret), email="ok-desativa@teste.com")
    access = create_access_token("u1", "advogado")
    db = _FakeDB(results=[user] * 4)
    client = TestClient(_montar(db))
    ip = "10.42.0.2"
    # 2 erros antes não impedem o acerto (abaixo do teto de 5)
    for _ in range(2):
        client.post("/auth/totp/desativar", json={"codigo": "000000"},
                    headers=_hdr(ip, access))
    r = client.post("/auth/totp/desativar",
                    json={"codigo": pyotp.TOTP(secret).now()},
                    headers=_hdr(ip, access))
    assert r.status_code == 200
    assert user.totp_enabled is False and user.totp_secret is None


# ── 2. Mojibake — forma cp1252 reparada para o caractere correto ─────────────

def test_mojibake_cp1252_repara_acentuacao_correta():
    from app.services.document_format import sem_caracteres_problematicos as f

    # Forma cp1252 (a mais comum): Ã‰ Ã‡ Ãƒ â€” …
    # "—" é intencionalmente normalizado para "-" DEPOIS do reparo.
    assert f("PETIÃ‡ÃƒO INICIAL â€” aÃ§Ã£o") == \
        "PETIÇÃO INICIAL - ação"
    assert f("EXCEÃ‡ÃƒO DE PRÃ‰-EXECUTIVIDADE") == \
        "EXCEÇÃO DE PRÉ-EXECUTIVIDADE"


def test_mojibake_latin1_continua_reparado():
    from app.services.document_format import sem_caracteres_problematicos as f

    assert f("PETIÃ\x87Ã\x83O INICIAL â\x80\x94 aÃ§Ã£o") == \
        "PETIÇÃO INICIAL - ação"
    assert f("AÃ§Ã£o nÂº 10 Â§ 2Âº") == \
        "Ação nº 10 § 2º"


def test_mojibake_roda_antes_das_substituicoes_de_aspas():
    """O trigrama cp1252 de "—" contém "”" — se _REPLACEMENTS rodasse antes,
    o reparo seria destruído e sobraria lixo ("â€-")."""
    from app.services.document_format import sem_caracteres_problematicos as f

    assert f("tÃ­tulo â€” conteÃºdo") == "título - conteúdo"
    # Texto JÁ correto não é alterado (aspas/travessão viram ASCII pelo mapa).
    assert f("Petição — “ação”") == 'Petição - "ação"'


# ── 6. /ai/detectar-prazos — valida caso ANTES da IA ─────────────────────────

_TEXTO_OK = (
    "Intimação fictícia: fica a parte ré intimada para apresentar contestação "
    "no prazo de 15 dias úteis, com termo final em 20/08/2026 (teste)."
)


def _cu_advogado():
    from app.models.user import User
    return User(id="u-adv-1", role=UserRole.advogado)


async def test_detectar_prazos_case_inexistente_404_sem_chamar_ia(monkeypatch):
    import app.services.ai_service as svc
    from app.routers.ai import detectar_prazos
    from app.schemas.ai import ResumirDocRequest

    async def nao_deveria_chamar(*a, **k):
        raise AssertionError("IA chamada antes de validar o caso")
    monkeypatch.setattr(svc, "_gateway_text", nao_deveria_chamar)
    monkeypatch.setattr(svc.settings, "AI_ENABLED", True)

    db = _FakeDB(results=[None])          # caso não existe
    with pytest.raises(HTTPException) as exc:
        await detectar_prazos(
            ResumirDocRequest(texto=_TEXTO_OK, case_id="c-inexistente"),
            db=db, cu=_cu_advogado(),
        )
    assert exc.value.status_code == 404


async def test_detectar_prazos_sem_acesso_ao_caso_403(monkeypatch):
    import app.services.ai_service as svc
    from app.routers.ai import detectar_prazos
    from app.schemas.ai import ResumirDocRequest

    async def nao_deveria_chamar(*a, **k):
        raise AssertionError("IA chamada antes de validar o caso")
    monkeypatch.setattr(svc, "_gateway_text", nao_deveria_chamar)
    monkeypatch.setattr(svc.settings, "AI_ENABLED", True)

    caso_alheio = SimpleNamespace(
        advogado_responsavel_id="outro-1", advogado_auxiliar_id="outro-2")
    db = _FakeDB(results=[caso_alheio])
    with pytest.raises(HTTPException) as exc:
        await detectar_prazos(
            ResumirDocRequest(texto=_TEXTO_OK, case_id="c-alheio"),
            db=db, cu=_cu_advogado(),
        )
    assert exc.value.status_code == 403


# ── 7/8. Drive — 503 controlado + Content-Disposition sanitizado ─────────────

def _upload_file(nome: str, conteudo: bytes, content_type: str):
    return StarletteUploadFile(
        io.BytesIO(conteudo), filename=nome,
        headers=Headers({"content-type": content_type}),
    )


def _cu_socio():
    return types.SimpleNamespace(id="u1", role=types.SimpleNamespace(value="socio"))


_PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF"


async def test_drive_upload_sem_rclone_503(monkeypatch):
    from app.routers import documents as docs_mod

    def indisponivel(*a, **k):
        raise docs_mod.gd.DriveIndisponivelError("rclone não configurado")
    monkeypatch.setattr(docs_mod.gd, "upload_file", indisponivel)

    with pytest.raises(HTTPException) as exc:
        await docs_mod.upload_para_drive(
            file=_upload_file("contrato.pdf", _PDF, "application/pdf"),
            case_id=None, descricao=None, db=_FakeDB(), current_user=_cu_socio(),
        )
    assert exc.value.status_code == 503
    assert "Drive" in exc.value.detail


async def test_drive_download_sem_rclone_503(monkeypatch):
    from app.routers import documents as docs_mod

    async def gate_ok(*a, **k):
        return {"id": "doc1"}
    monkeypatch.setattr(docs_mod, "_gate_drive_doc", gate_ok)

    def indisponivel(*a, **k):
        raise docs_mod.gd.DriveIndisponivelError("rclone não configurado")
    monkeypatch.setattr(docs_mod.gd, "download_file", indisponivel)

    with pytest.raises(HTTPException) as exc:
        await docs_mod.download_documento(
            "drv1", db=_FakeDB(), current_user=_cu_socio())
    assert exc.value.status_code == 503


async def test_drive_delete_sem_rclone_503(monkeypatch):
    from app.routers import documents as docs_mod

    async def gate_ok(*a, **k):
        return {"id": "doc1"}
    monkeypatch.setattr(docs_mod, "_gate_drive_doc", gate_ok)

    def indisponivel(*a, **k):
        raise docs_mod.gd.DriveIndisponivelError("rclone não configurado")
    monkeypatch.setattr(docs_mod.gd, "delete_file", indisponivel)

    with pytest.raises(HTTPException) as exc:
        await docs_mod.deletar_documento_drive(
            "drv1", db=_FakeDB(), current_user=_cu_socio())
    assert exc.value.status_code == 503


async def test_drive_download_content_disposition_sanitizado(monkeypatch):
    from app.routers import documents as docs_mod

    async def gate_ok(*a, **k):
        return {"id": "doc1"}
    monkeypatch.setattr(docs_mod, "_gate_drive_doc", gate_ok)
    monkeypatch.setattr(docs_mod.gd, "download_file",
                        lambda fid: (_PDF, "application/pdf"))
    monkeypatch.setattr(
        docs_mod.gd, "get_file_link",
        lambda fid: {"name": 'peti"ção; ré\r\nplica.pdf'},
    )

    resp = await docs_mod.download_documento(
        "drv1", db=_FakeDB(), current_user=_cu_socio())
    cd = resp.headers["content-disposition"]
    # filename ASCII sem aspas/; /CR-LF (não mangla nem injeta header)…
    assert 'filename="peticao re plica.pdf"' in cd
    # …e filename* RFC 5987 preserva o nome real percent-encoded.
    assert "filename*=UTF-8''" in cd
    assert "%C3%A7" in cd                 # "ç" percent-encoded
    assert "\r" not in cd and "\n" not in cd


# ── 12. GET /signatures/ — cada item traz `signatarios` ──────────────────────

async def test_signatures_listar_inclui_signatarios():
    from app.models.signature import SignatureRequest, SignatureStatus
    from app.routers.signatures import listar

    sr = SignatureRequest(
        id="sig1", document_id="d1", client_id="c1",
        status=SignatureStatus.pendente, hash_sha256="a" * 64,
    )
    portal = SimpleNamespace(id="up1", full_name="Cliente Fictício",
                             email="cliente@portal.teste", client_id="c1")
    db = _FakeDB(results=[
        _Res(lista=[sr]),                          # solicitações
        _Res(lista=[("d1", "Procuração (teste)")]),  # títulos dos docs
        _Res(lista=[portal]),                      # logins do portal
    ])
    cu = SimpleNamespace(role=UserRole.advogado, client_id=None)

    r = await listar(db=db, cu=cu)
    item = r["data"][0]
    assert item["documento"] == "Procuração (teste)"
    assert item["client_id"] == "c1"
    assert item["signatarios"] == [{
        "nome": "Cliente Fictício", "email": "cliente@portal.teste",
        "papel": "cliente", "assinado": False,
    }]


async def test_signatures_listar_sem_login_de_portal_lista_vazia():
    from app.models.signature import SignatureRequest, SignatureStatus
    from app.routers.signatures import listar

    sr = SignatureRequest(
        id="sig2", document_id="d2", client_id="c2",
        status=SignatureStatus.pendente, hash_sha256="b" * 64,
    )
    db = _FakeDB(results=[
        _Res(lista=[sr]),
        _Res(lista=[("d2", "Contrato (teste)")]),
        _Res(lista=[]),                            # cliente sem login de portal
    ])
    cu = SimpleNamespace(role=UserRole.advogado, client_id=None)

    r = await listar(db=db, cu=cu)
    assert r["data"][0]["signatarios"] == []       # campo sempre presente
