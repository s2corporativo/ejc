"""Cofre de Credenciais — PR-1 (fundação): vault_crypto (MultiFernet),
credential_registry (catálogo estático) e modelo/migration 108.

Não precisa de banco: primitivas criptográficas puras + introspecção de
metadata/Settings (a config de testes gera VAULT_MASTER_KEYS efêmera de dev
em app/core/config.py — nunca em produção)."""
import inspect
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.core.config import Settings
from app.services import credential_registry, vault_crypto


# ── vault_crypto: MultiFernet ────────────────────────────────────────────────

def test_cifrar_decifrar_roundtrip():
    original = "sk-ant-teste-000000000000"
    token = vault_crypto.cifrar(original)
    assert token != original  # não pode vazar em claro
    assert vault_crypto.decifrar(token) == original


def test_cifrar_nao_e_deterministico():
    """Fernet usa IV aleatório — mesma propriedade do pii_crypto."""
    a = vault_crypto.cifrar("segredo")
    b = vault_crypto.cifrar("segredo")
    assert a != b
    assert vault_crypto.decifrar(a) == vault_crypto.decifrar(b) == "segredo"


def test_decifrar_token_invalido_levanta_valueerror():
    with pytest.raises(ValueError):
        vault_crypto.decifrar("isto-nao-e-um-token-fernet-valido")


def test_decifrar_token_de_chave_fora_do_csv_levanta_valueerror(monkeypatch):
    """Token cifrado com chave que NÃO está em VAULT_MASTER_KEYS → falha alto
    (mascarar entregaria credencial errada a uma integração externa)."""
    chave_perdida = Fernet.generate_key()
    token = Fernet(chave_perdida).encrypt(b"segredo").decode()
    monkeypatch.setattr(
        vault_crypto.settings, "VAULT_MASTER_KEYS", Fernet.generate_key().decode()
    )
    with pytest.raises(ValueError):
        vault_crypto.decifrar(token)


def test_rotacao_de_mestra_prepend_e_reencrypt(monkeypatch):
    """Fluxo completo da rotação: cifra com a chave antiga; prepend da nova
    (nova primária, antiga ainda decifra); rotacionar() recifra com a nova;
    ao remover a antiga do CSV, só o token rotacionado sobrevive."""
    antiga = Fernet.generate_key().decode()
    nova = Fernet.generate_key().decode()

    # 1. Regime antigo: só a chave antiga.
    monkeypatch.setattr(vault_crypto.settings, "VAULT_MASTER_KEYS", antiga)
    token_legado = vault_crypto.cifrar("credencial-legada")

    # 2. Prepend da nova (primária) mantendo a antiga como secundária:
    #    o legado continua decifrável e valores novos saem pela nova chave.
    monkeypatch.setattr(
        vault_crypto.settings, "VAULT_MASTER_KEYS", f"{nova},{antiga}"
    )
    assert vault_crypto.decifrar(token_legado) == "credencial-legada"
    assert (
        Fernet(nova.encode()).decrypt(
            vault_crypto.cifrar("valor-novo").encode()
        ).decode()
        == "valor-novo"
    )

    # 3. Re-encrypt em background: rotacionar() decifra (qualquer chave do
    #    CSV) e recifra com a PRIMÁRIA.
    token_rotacionado = vault_crypto.rotacionar(token_legado)
    assert token_rotacionado != token_legado
    assert (
        Fernet(nova.encode()).decrypt(token_rotacionado.encode()).decode()
        == "credencial-legada"
    )

    # 4. Descarte da chave antiga: o token rotacionado sobrevive, o legado não.
    monkeypatch.setattr(vault_crypto.settings, "VAULT_MASTER_KEYS", nova)
    assert vault_crypto.decifrar(token_rotacionado) == "credencial-legada"
    with pytest.raises(ValueError):
        vault_crypto.decifrar(token_legado)


def test_chaves_configuradas_e_falha_alta_sem_chave(monkeypatch):
    assert vault_crypto.chaves_configuradas() is True  # dev gera efêmera
    monkeypatch.setattr(vault_crypto.settings, "VAULT_MASTER_KEYS", "")
    assert vault_crypto.chaves_configuradas() is False
    with pytest.raises(RuntimeError):
        vault_crypto.cifrar("x")
    with pytest.raises(RuntimeError):
        vault_crypto.decifrar("x")


def test_primeira_chave_do_csv_e_a_primaria(monkeypatch):
    """Contrato documentado: a PRIMEIRA chave do CSV cifra; as demais só
    decifram (espaços em volta das vírgulas são tolerados)."""
    k1 = Fernet.generate_key().decode()
    k2 = Fernet.generate_key().decode()
    monkeypatch.setattr(
        vault_crypto.settings, "VAULT_MASTER_KEYS", f" {k1} , {k2} "
    )
    token = vault_crypto.cifrar("segredo")
    assert Fernet(k1.encode()).decrypt(token.encode()).decode() == "segredo"


# ── config: gate de produção do VAULT_MASTER_KEYS ────────────────────────────

def _prod_kwargs(**over):
    """Mesmo helper de test_auditoria_pre_producao: produção mínima válida."""
    base = dict(
        APP_ENV="production",
        SECRET_KEY="s" * 64,
        PII_ENCRYPTION_KEY=Fernet.generate_key().decode(),
        PII_HASH_KEY="h" * 32,
        VAULT_MASTER_KEYS=Fernet.generate_key().decode(),
        FRONTEND_URL="https://app.exemplo.adv.br",
        CORS_ORIGINS="https://app.exemplo.adv.br",
    )
    base.update(over)
    return base


def test_producao_sem_vault_master_keys_falha_no_boot():
    with pytest.raises(ValueError, match="VAULT_MASTER_KEYS"):
        Settings(**_prod_kwargs(VAULT_MASTER_KEYS=""))


def test_producao_recusa_chave_secundaria_malformada():
    """TODAS as chaves do CSV são validadas no boot — uma secundária podre só
    estouraria meses depois, na primeira decifragem durante uma rotação."""
    boa = Fernet.generate_key().decode()
    with pytest.raises(ValueError, match="VAULT_MASTER_KEYS"):
        Settings(**_prod_kwargs(VAULT_MASTER_KEYS=f"{boa},nao-e-fernet"))


def test_producao_aceita_csv_de_chaves_validas():
    k1, k2 = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    s = Settings(**_prod_kwargs(VAULT_MASTER_KEYS=f"{k1},{k2}"))
    assert s.vault_master_keys_list == [k1, k2]


def test_dev_gera_chave_efemera_com_aviso():
    with pytest.warns(UserWarning, match="VAULT_MASTER_KEYS"):
        s = Settings(APP_ENV="development", VAULT_MASTER_KEYS="")
    assert s.vault_master_keys_list  # efêmera gerada


# ── credential_registry: catálogo × Settings ─────────────────────────────────

def test_todo_field_key_do_catalogo_existe_em_settings():
    """CONTRATO CENTRAL do cofre: field_key = nome EXATO do atributo em
    Settings (é o que permite o overlay por setattr no PR-2). Introspecção
    real — se alguém renomear o atributo na config, este teste quebra."""
    atributos = set(Settings.model_fields)
    for field_key in credential_registry.todos_field_keys():
        assert field_key in atributos, (
            f"field_key '{field_key}' do credential_registry não existe como "
            "atributo de Settings (app/core/config.py)"
        )


def test_catalogo_cobre_as_integracoes_planejadas():
    assert set(credential_registry.REGISTRY) == {
        "datajud", "groq", "anthropic", "maritaca", "infosimples",
        "smtp", "nfse", "transparencia", "langfuse", "push_vapid",
    }


def test_tipos_do_catalogo_sao_validos_e_sem_field_key_duplicado():
    field_keys = credential_registry.todos_field_keys()
    assert len(field_keys) == len(set(field_keys))
    for campos in credential_registry.REGISTRY.values():
        assert campos, "provider sem campos no catálogo"
        for campo in campos:
            assert campo.tipo in credential_registry.TIPOS_VALIDOS
            assert campo.rotulo


def test_buscar_campo():
    campo = credential_registry.buscar_campo("datajud", "DATAJUD_API_KEY")
    assert campo is not None and campo.tipo == "api_key"
    assert credential_registry.buscar_campo("datajud", "OUTRA_COISA") is None
    assert credential_registry.buscar_campo("inexistente", "X") is None


# ── modelo + migration 108 ───────────────────────────────────────────────────

def test_modelo_importavel_e_na_metadata():
    from app.core.database import Base
    from app.models import IntegrationCredential

    assert IntegrationCredential.__tablename__ == "integration_credentials"
    tabela = Base.metadata.tables["integration_credentials"]
    colunas = set(tabela.columns.keys())
    assert {
        "id", "provider_key", "field_key", "tipo", "valor_encrypted", "last4",
        "versao", "ativo", "origem", "expires_at", "last_test_at",
        "last_test_status", "last_test_detail", "created_by", "created_at",
        "updated_at", "revoked_at", "revoked_by",
    } <= colunas
    # Unicidade do valor vigente: índice único PARCIAL (WHERE ativo).
    indices = {ix.name: ix for ix in tabela.indexes}
    parcial = indices["uq_integration_credentials_provider_field_ativo"]
    assert parcial.unique


def test_migration_108_encadeada_e_idempotente():
    """Segue o harness dos vizinhos (test_alembic_single_head): valida o
    encadeamento via ScriptDirectory e a idempotência por inspeção do SQL
    (CREATE ... IF NOT EXISTS — padrão da 107)."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    script = ScriptDirectory.from_config(config)

    revision = script.get_revision("108_credential_vault")
    assert revision.down_revision == "107_scheduler_heartbeat"
    # Head único preservado: o hardening acrescentou 109_rag_scope_cliente
    # ENCADEADO sobre a 108 (sem ramificar) — a cadeia segue linear.
    assert script.get_heads() == ["109_rag_scope_cliente"]

    modulo = revision.module
    fonte_upgrade = inspect.getsource(modulo.upgrade)
    assert "CREATE TABLE IF NOT EXISTS integration_credentials" in fonte_upgrade
    assert "CREATE UNIQUE INDEX IF NOT EXISTS" in fonte_upgrade
    assert "WHERE ativo" in fonte_upgrade
