"""Cofre de Credenciais — PR-6: rotação da chave-mestra (rotacionar_todas).

Sem Postgres: SQLite in-memory (aiosqlite + StaticPool, mesmo padrão de
test_vault_service) com o índice único parcial real. A auditoria é capturada
por um fake (autouse) — valida ação/detalhes sem depender de audit_logs (JSONB).

Cobertura:
  * rotacionar_todas recifra com a NOVA primária e o valor decifrado é IGUAL
    (roundtrip antes/depois) — inclusive uma linha HISTÓRICA com ciphertext;
  * idempotência: rodar 2x não altera o claro;
  * dry-run não grava (ciphertext intacto) e retorna (0, total);
  * o script vault_rotate_master_key aborta com erro claro se o CSV tem só
    uma chave.
"""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet, MultiFernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.models.integration_credential import IntegrationCredential
from app.services import credential_vault_service as svc
from app.services import vault_crypto

SEGREDO = "sk-teste-cofre-0000abcd"
SEGREDO2 = "sk-teste-cofre-9999wxyz"
USER = "u-rot"

CHAVE_ANTIGA = Fernet.generate_key().decode()
CHAVE_NOVA = Fernet.generate_key().decode()


@pytest.fixture
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(IntegrationCredential.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture(autouse=True)
def audit(monkeypatch):
    registros: list[dict] = []

    async def _fake(db, user_id, user_role, acao, entidade,
                    registro_id=None, detalhes=None, **kw):
        registros.append({
            "user_id": user_id, "acao": acao, "entidade": entidade,
            "registro_id": registro_id, "detalhes": detalhes,
        })

    monkeypatch.setattr(svc, "criar_audit_log", _fake)
    return registros


@pytest.fixture
def so_chave_antiga(monkeypatch):
    """CSV só com a chave antiga — estado ANTES de iniciar a rotação."""
    monkeypatch.setattr(get_settings(), "VAULT_MASTER_KEYS", CHAVE_ANTIGA)


def _prepend_chave_nova(monkeypatch):
    """Passo (a) da rotação: coloca a chave nova na FRENTE do CSV."""
    monkeypatch.setattr(
        get_settings(), "VAULT_MASTER_KEYS", f"{CHAVE_NOVA},{CHAVE_ANTIGA}"
    )


async def _rows_com_cipher(db) -> list[IntegrationCredential]:
    res = await db.execute(
        select(IntegrationCredential)
        .where(IntegrationCredential.valor_encrypted.is_not(None))
        .order_by(IntegrationCredential.field_key)
    )
    return list(res.scalars().all())


# ── roundtrip: recifra com a nova primária, claro idêntico ───────────────────

async def test_rotacao_recifra_com_nova_e_preserva_claro(db, monkeypatch, so_chave_antiga):
    # Cadastra cifrando com a chave ANTIGA (única no CSV neste momento).
    await svc.cadastrar(db, "datajud", "DATAJUD_API_KEY", SEGREDO, "api_key", USER)
    await svc.cadastrar(db, "smtp", "SMTP_PASSWORD", "senha-smtp-1", "senha", USER)
    # Uma linha HISTÓRICA com ciphertext não-nulo (o fluxo normal zera, então
    # forjamos uma para provar que a rotação alcança linhas inativas também).
    historica = IntegrationCredential(
        id="hist-1", provider_key="groq", field_key="GROQ_API_KEY",
        tipo="api_key", valor_encrypted=vault_crypto.cifrar("gsk-historica-xyz"),
        last4="axyz", versao=1, ativo=False, origem="manual",
    )
    db.add(historica)
    await db.commit()

    antes = {c.field_key: c.valor_encrypted for c in await _rows_com_cipher(db)}

    # Passo (a): chave nova na frente. Passo (b): rotaciona.
    _prepend_chave_nova(monkeypatch)
    rotacionadas, total = await svc.rotacionar_todas(db, user_id=USER)
    assert (rotacionadas, total) == (3, 3)

    depois = {c.field_key: c.valor_encrypted for c in await _rows_com_cipher(db)}
    so_nova = MultiFernet([Fernet(CHAVE_NOVA.encode())])
    esperado = {
        "DATAJUD_API_KEY": SEGREDO,
        "SMTP_PASSWORD": "senha-smtp-1",
        "GROQ_API_KEY": "gsk-historica-xyz",
    }
    for fk, claro in esperado.items():
        assert depois[fk] != antes[fk]                      # ciphertext mudou
        assert vault_crypto.decifrar(depois[fk]) == claro   # claro preservado
        # Recifrado com a PRIMÁRIA nova: decifra só com a nova, sem a antiga.
        assert so_nova.decrypt(depois[fk].encode()).decode() == claro


async def test_rotacao_audita_sem_segredo(db, monkeypatch, audit, so_chave_antiga):
    await svc.cadastrar(db, "datajud", "DATAJUD_API_KEY", SEGREDO, "api_key", USER)
    _prepend_chave_nova(monkeypatch)
    await svc.rotacionar_todas(db, user_id=USER)

    rot = [r for r in audit if r["acao"] == "COFRE_ROTATE_MASTER"]
    assert len(rot) == 1
    assert rot[0]["entidade"] == "integration_credentials"
    assert rot[0]["user_id"] == USER
    assert "rotacionadas=1" in rot[0]["detalhes"]
    assert SEGREDO not in (rot[0]["detalhes"] or "")


# ── idempotência ─────────────────────────────────────────────────────────────

async def test_rotacao_idempotente_nao_muda_o_claro(db, monkeypatch, so_chave_antiga):
    await svc.cadastrar(db, "datajud", "DATAJUD_API_KEY", SEGREDO, "api_key", USER)
    _prepend_chave_nova(monkeypatch)

    await svc.rotacionar_todas(db, user_id=USER)
    (linha,) = await _rows_com_cipher(db)
    cipher_1 = linha.valor_encrypted

    # Segunda passada: rotaciona de novo. O ciphertext pode mudar (novo IV),
    # mas o valor DECIFRADO tem que permanecer idêntico — nada corrompe.
    rotacionadas, total = await svc.rotacionar_todas(db, user_id=USER)
    assert (rotacionadas, total) == (1, 1)
    (linha,) = await _rows_com_cipher(db)
    assert vault_crypto.decifrar(linha.valor_encrypted) == SEGREDO
    assert vault_crypto.decifrar(cipher_1) == SEGREDO


# ── dry-run não grava ────────────────────────────────────────────────────────

async def test_dry_run_conta_sem_gravar(db, monkeypatch, audit, so_chave_antiga):
    await svc.cadastrar(db, "datajud", "DATAJUD_API_KEY", SEGREDO, "api_key", USER)
    await svc.cadastrar(db, "smtp", "SMTP_PASSWORD", "senha-smtp-1", "senha", USER)
    antes = {c.field_key: c.valor_encrypted for c in await _rows_com_cipher(db)}

    _prepend_chave_nova(monkeypatch)
    rotacionadas, total = await svc.rotacionar_todas(db, dry_run=True, user_id=USER)
    assert rotacionadas == 0 and total == 2

    depois = {c.field_key: c.valor_encrypted for c in await _rows_com_cipher(db)}
    assert depois == antes                                  # nada gravado
    assert [r for r in audit if r["acao"] == "COFRE_ROTATE_MASTER"] == []


# ── guarda de chave única (service — rede de segurança real) ─────────────────

async def test_rotacionar_todas_uma_chave_levanta(db, monkeypatch, so_chave_antiga):
    """Caller programático com uma única chave no CSV e dry_run=False: recifra
    seria no-op → levanta ANTES de tocar em qualquer linha."""
    await svc.cadastrar(db, "datajud", "DATAJUD_API_KEY", SEGREDO, "api_key", USER)
    antes = {c.field_key: c.valor_encrypted for c in await _rows_com_cipher(db)}

    with pytest.raises((RuntimeError, ValueError)):
        await svc.rotacionar_todas(db, user_id=USER)   # CSV com 1 chave só

    depois = {c.field_key: c.valor_encrypted for c in await _rows_com_cipher(db)}
    assert depois == antes                             # nenhuma linha tocada


async def test_rotacionar_todas_uma_chave_dry_run_ok(db, monkeypatch, so_chave_antiga):
    """dry_run só CONTA — não exige a segunda chave (não vai recifrar nada)."""
    await svc.cadastrar(db, "datajud", "DATAJUD_API_KEY", SEGREDO, "api_key", USER)
    rotacionadas, total = await svc.rotacionar_todas(db, dry_run=True, user_id=USER)
    assert (rotacionadas, total) == (0, 1)


# ── guarda de chave única (script) ───────────────────────────────────────────

def test_script_aborta_com_chave_unica(monkeypatch):
    from scripts import vault_rotate_master_key as script

    monkeypatch.setattr(get_settings(), "VAULT_MASTER_KEYS", CHAVE_ANTIGA)
    with pytest.raises(SystemExit) as exc:
        script._exigir_multiplas_chaves()
    assert "menos de duas chaves" in str(exc.value).lower()


def test_script_aceita_duas_chaves(monkeypatch):
    from scripts import vault_rotate_master_key as script

    monkeypatch.setattr(
        get_settings(), "VAULT_MASTER_KEYS", f"{CHAVE_NOVA},{CHAVE_ANTIGA}"
    )
    assert script._exigir_multiplas_chaves() == 2
