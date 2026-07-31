# Testes do validador de segurança em produção (SECRET_KEY).
import pytest
from cryptography.fernet import Fernet
from app.core.config import Settings


def test_producao_sem_chave_falha():
    with pytest.raises(Exception):
        Settings(APP_ENV="production", SECRET_KEY="")


def test_producao_placeholder_falha():
    with pytest.raises(Exception):
        Settings(APP_ENV="production", SECRET_KEY="TROCAR_POR_CHAVE_ALEATORIA_DE_64_CHARS")


def test_producao_com_chave_real_ok():
    fernet_key = Fernet.generate_key().decode()
    s = Settings(
        APP_ENV="production",
        SECRET_KEY="z" * 48,
        FRONTEND_URL="https://ejc.depaulateixeira.adv.br",
        PII_ENCRYPTION_KEY=fernet_key,
        PII_HASH_KEY="h" * 48,
        VAULT_MASTER_KEYS=fernet_key,
    )
    assert s.SECRET_KEY == "z" * 48


def test_dev_sem_chave_gera_efemera():
    s = Settings(APP_ENV="development", SECRET_KEY="")
    assert len(s.SECRET_KEY) > 20      # chave efêmera gerada automaticamente
