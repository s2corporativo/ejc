"""Cofre de Credenciais — PR-2: credential_vault_service (service + overlay).

Sem Postgres: SQLite in-memory (aiosqlite + StaticPool, mesmo padrão de
test_scheduler_heartbeat) com o índice único PARCIAL real (sqlite_where).
A auditoria é capturada por um fake (autouse) — valida ação/detalhes sem
depender da tabela audit_logs (JSONB é dialeto Postgres).

Cobertura:
  * cadastrar: v1, substituição (v2, valor antigo ZERADO, last4), validações;
  * revogar: desativa + zera + revoked_at/by; overlay põe "" (sem fallback .env);
  * precedência do overlay: nunca cadastrado → .env; ativa → sobrepõe;
  * mutação IN-PLACE do singleton (módulo que importou settings antes enxerga);
  * importar_do_env idempotente e sem vazar valor;
  * listar só metadados; auditoria sem segredo; versao_atual muda a cada escrita.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.models.integration_credential import IntegrationCredential
from app.services import credential_registry, credential_vault_service as svc
from app.services import vault_crypto

SEGREDO = "sk-teste-cofre-0000abcd"
USER = "u-1"


@pytest.fixture
async def db():
    """Sessão SQLite in-memory com integration_credentials + índice parcial."""
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
    """Captura criar_audit_log do service (a tabela audit_logs usa JSONB —
    dialeto Postgres — e a auditoria aqui é validada pelo CONTEÚDO)."""
    registros: list[dict] = []

    async def _fake(db, user_id, user_role, acao, entidade,
                    registro_id=None, detalhes=None, **kw):
        registros.append({
            "user_id": user_id, "acao": acao, "entidade": entidade,
            "registro_id": registro_id, "detalhes": detalhes,
        })

    monkeypatch.setattr(svc, "criar_audit_log", _fake)
    return registros


async def _rows(db, field_key: str) -> list[IntegrationCredential]:
    res = await db.execute(
        select(IntegrationCredential)
        .where(IntegrationCredential.field_key == field_key)
        .order_by(IntegrationCredential.versao)
    )
    return res.scalars().all()


# ── cadastrar ────────────────────────────────────────────────────────────────

async def test_cadastrar_cria_v1_cifrada(db):
    meta = await svc.cadastrar(db, "datajud", "DATAJUD_API_KEY", SEGREDO,
                               "api_key", USER)
    assert meta["versao"] == 1 and meta["ativo"] is True
    assert meta["last4"] == SEGREDO[-4:] and len(meta["last4"]) == 4
    assert meta["origem"] == "manual"
    assert "valor" not in meta and "valor_encrypted" not in meta

    (linha,) = await _rows(db, "DATAJUD_API_KEY")
    assert linha.valor_encrypted != SEGREDO          # cifrado em repouso
    assert vault_crypto.decifrar(linha.valor_encrypted) == SEGREDO
    assert linha.created_by == USER


async def test_cadastrar_substitui_versiona_e_zera_valor_antigo(db):
    await svc.cadastrar(db, "datajud", "DATAJUD_API_KEY", SEGREDO,
                        "api_key", USER)
    novo = "sk-teste-cofre-9999wxyz"
    meta2 = await svc.cadastrar(db, "datajud", "DATAJUD_API_KEY", novo,
                                "api_key", USER)
    assert meta2["versao"] == 2

    v1, v2 = await _rows(db, "DATAJUD_API_KEY")
    assert v1.ativo is False and v2.ativo is True
    assert v1.valor_encrypted is None                # segredo antigo ZERADO
    assert v1.last4 == SEGREDO[-4:]                  # metadado sobrevive
    assert vault_crypto.decifrar(v2.valor_encrypted) == novo


async def test_cadastrar_rejeita_fora_do_catalogo_e_formato(db):
    with pytest.raises(ValueError):                  # provider desconhecido
        await svc.cadastrar(db, "acme", "DATAJUD_API_KEY", SEGREDO,
                            "api_key", USER)
    with pytest.raises(ValueError):                  # field fora do catálogo
        await svc.cadastrar(db, "datajud", "CAMPO_INVENTADO", SEGREDO,
                            "api_key", USER)
    with pytest.raises(ValueError):                  # tipo ≠ catálogo
        await svc.cadastrar(db, "datajud", "DATAJUD_API_KEY", SEGREDO,
                            "senha", USER)
    with pytest.raises(ValueError):                  # vazio
        await svc.cadastrar(db, "datajud", "DATAJUD_API_KEY", "   ",
                            "api_key", USER)
    with pytest.raises(ValueError):                  # espaço em api_key
        await svc.cadastrar(db, "datajud", "DATAJUD_API_KEY", "tem espaco aqui",
                            "api_key", USER)
    with pytest.raises(ValueError):                  # curto demais
        await svc.cadastrar(db, "datajud", "DATAJUD_API_KEY", "abc",
                            "api_key", USER)
    assert await _rows(db, "DATAJUD_API_KEY") == []  # nada gravado


# ── revogar ──────────────────────────────────────────────────────────────────

async def test_revogar_desativa_zera_e_marca(db):
    await svc.cadastrar(db, "datajud", "DATAJUD_API_KEY", SEGREDO,
                        "api_key", USER)
    meta = await svc.revogar(db, "datajud", "DATAJUD_API_KEY", "u-2")
    assert meta["ativo"] is False and meta["revoked_at"] is not None

    (linha,) = await _rows(db, "DATAJUD_API_KEY")
    assert linha.ativo is False
    assert linha.valor_encrypted is None
    assert linha.revoked_at is not None and linha.revoked_by == "u-2"


async def test_revogar_sem_ativa_levanta_valueerror(db):
    with pytest.raises(ValueError):
        await svc.revogar(db, "datajud", "DATAJUD_API_KEY", USER)


# ── overlay: precedência e mutação do singleton ──────────────────────────────

async def test_precedencia_env_ativa_revogada(db, monkeypatch):
    settings = get_settings()
    # monkeypatch.setattr registra o valor ORIGINAL — restaura o singleton no
    # teardown mesmo que aplicar_overlay o mute depois.
    monkeypatch.setattr(settings, "DATAJUD_API_KEY", "valor-do-env")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "groq-do-env")

    # 1. Nunca cadastrado → .env intacto.
    await svc.aplicar_overlay(db)
    assert settings.DATAJUD_API_KEY == "valor-do-env"
    assert settings.GROQ_API_KEY == "groq-do-env"

    # 2. Linha ATIVA sobrepõe o .env (groq segue no .env).
    await svc.cadastrar(db, "datajud", "DATAJUD_API_KEY", SEGREDO,
                        "api_key", USER)
    aplicados = await svc.aplicar_overlay(db)
    assert settings.DATAJUD_API_KEY == SEGREDO
    assert settings.GROQ_API_KEY == "groq-do-env"
    assert aplicados == ["DATAJUD_API_KEY"]

    # 3. Revogada → "" explícito, SEM fallback ao .env.
    await svc.revogar(db, "datajud", "DATAJUD_API_KEY", USER)
    await svc.aplicar_overlay(db)
    assert settings.DATAJUD_API_KEY == ""
    assert settings.GROQ_API_KEY == "groq-do-env"


async def test_overlay_muta_o_singleton_visto_por_modulo_antigo(db, monkeypatch):
    """vault_crypto guardou `settings = get_settings()` no import (como ~68
    módulos): a mutação in-place tem que aparecer lá — e o objeto tem que
    continuar sendo O MESMO (nunca cache_clear/segundo Settings)."""
    settings = get_settings()
    monkeypatch.setattr(settings, "DATAJUD_API_KEY", "antes-do-overlay")
    assert vault_crypto.settings is settings          # identidade do singleton

    await svc.cadastrar(db, "datajud", "DATAJUD_API_KEY", SEGREDO,
                        "api_key", USER)
    await svc.aplicar_overlay(db)

    assert vault_crypto.settings.DATAJUD_API_KEY == SEGREDO
    assert vault_crypto.settings is get_settings()    # mesmo objeto, sempre


async def test_resolver_overlay_so_ativas_decifradas(db):
    await svc.cadastrar(db, "datajud", "DATAJUD_API_KEY", SEGREDO,
                        "api_key", USER)
    await svc.cadastrar(db, "smtp", "SMTP_PASSWORD", "senha-smtp",
                        "senha", USER)
    await svc.revogar(db, "smtp", "SMTP_PASSWORD", USER)
    overlay = await svc.resolver_overlay(db)
    assert overlay == {"DATAJUD_API_KEY": SEGREDO}


# ── importar_do_env ──────────────────────────────────────────────────────────

async def test_importar_do_env_idempotente_sem_vazar_valor(db, monkeypatch):
    settings = get_settings()
    for fk in credential_registry.todos_field_keys():
        monkeypatch.setattr(settings, fk, "")
    monkeypatch.setattr(settings, "DATAJUD_API_KEY", "env-datajud-123456")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "env-senha")

    importados = await svc.importar_do_env(db, USER)
    assert {(i["provider"], i["field"]) for i in importados} == {
        ("datajud", "DATAJUD_API_KEY"), ("smtp", "SMTP_PASSWORD"),
    }
    for item in importados:
        assert set(item) == {"provider", "field", "last4"}   # nunca o valor
        assert item["last4"] and len(item["last4"]) <= 4

    linhas = await _rows(db, "DATAJUD_API_KEY")
    assert len(linhas) == 1 and linhas[0].origem == "env_import"
    assert vault_crypto.decifrar(linhas[0].valor_encrypted) == "env-datajud-123456"

    # Idempotência: segunda chamada não duplica nada.
    assert await svc.importar_do_env(db, USER) == []
    assert len(await _rows(db, "DATAJUD_API_KEY")) == 1


async def test_importar_do_env_nao_sobrescreve_linha_ativa(db, monkeypatch):
    settings = get_settings()
    for fk in credential_registry.todos_field_keys():
        monkeypatch.setattr(settings, fk, "")
    monkeypatch.setattr(settings, "DATAJUD_API_KEY", "env-datajud-123456")

    await svc.cadastrar(db, "datajud", "DATAJUD_API_KEY", SEGREDO,
                        "api_key", USER)
    assert await svc.importar_do_env(db, USER) == []
    (linha,) = [l for l in await _rows(db, "DATAJUD_API_KEY") if l.ativo]
    assert vault_crypto.decifrar(linha.valor_encrypted) == SEGREDO


# ── listar / versao_atual ────────────────────────────────────────────────────

async def test_listar_so_metadados(db):
    await svc.cadastrar(db, "datajud", "DATAJUD_API_KEY", SEGREDO,
                        "api_key", USER)
    await svc.cadastrar(db, "datajud", "DATAJUD_API_KEY",
                        "sk-teste-cofre-9999wxyz", "api_key", USER)
    itens = await svc.listar(db)
    assert len(itens) == 2
    for item in itens:
        assert "valor" not in item and "valor_encrypted" not in item
        assert SEGREDO not in repr(item)             # segredo nunca aparece
        assert {"provider_key", "field_key", "tipo", "last4", "versao",
                "ativo", "origem", "created_at", "updated_at",
                "last_test_status"} <= set(item)


async def test_versao_atual_muda_a_cada_escrita(db):
    v0 = await svc.versao_atual(db)
    assert v0 == (0, None)
    await svc.cadastrar(db, "datajud", "DATAJUD_API_KEY", SEGREDO,
                        "api_key", USER)
    v1 = await svc.versao_atual(db)
    assert v1 != v0 and v1[0] == 1
    await svc.revogar(db, "datajud", "DATAJUD_API_KEY", USER)
    v2 = await svc.versao_atual(db)
    assert v2 != v1


# ── auditoria ────────────────────────────────────────────────────────────────

async def test_auditoria_gravada_sem_segredo(db, audit, monkeypatch):
    await svc.cadastrar(db, "datajud", "DATAJUD_API_KEY", SEGREDO,
                        "api_key", USER)
    await svc.cadastrar(db, "datajud", "DATAJUD_API_KEY",
                        "sk-teste-cofre-9999wxyz", "api_key", USER)
    await svc.revogar(db, "datajud", "DATAJUD_API_KEY", USER)

    settings = get_settings()
    for fk in credential_registry.todos_field_keys():
        monkeypatch.setattr(settings, fk, "")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "env-senha")
    await svc.importar_do_env(db, USER)

    acoes = [r["acao"] for r in audit]
    assert acoes[:3] == ["COFRE_CREATE", "COFRE_ROTATE", "COFRE_REVOKE"]
    assert "COFRE_IMPORT_ENV" in acoes
    for r in audit:
        assert r["entidade"] == "integration_credentials"
        assert r["user_id"] == USER
        assert r["registro_id"]
        assert "last4=" in r["detalhes"]
        for segredo in (SEGREDO, "sk-teste-cofre-9999wxyz", "env-senha"):
            assert segredo not in (r["detalhes"] or "")
