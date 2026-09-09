from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from app.models.user import User
from app.routers.users import _preparar_cpf_usuario
from app.services import pii_crypto

CPF_VALIDO = "153.509.460-56"


def _keys(monkeypatch):
    monkeypatch.setattr(pii_crypto.settings, "PII_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(pii_crypto.settings, "PII_HASH_KEY", "teste-hmac-users-cpf")


def test_cpf_usuario_e_cifrado_e_hasheado(monkeypatch):
    _keys(monkeypatch)
    enc, h = _preparar_cpf_usuario(CPF_VALIDO)
    assert enc and enc != "15350946056"
    assert pii_crypto.decrypt(enc) == "15350946056"
    assert h == pii_crypto.hash_documento("15350946056")


def test_cpf_invalido_e_recusado(monkeypatch):
    _keys(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        _preparar_cpf_usuario("111.111.111-11")
    assert exc.value.status_code == 422


def test_string_vazia_limpa_cpf(monkeypatch):
    _keys(monkeypatch)
    assert _preparar_cpf_usuario("") == (None, None)


def test_user_response_expoe_apenas_cpf_mascarado(monkeypatch):
    _keys(monkeypatch)
    enc, _ = _preparar_cpf_usuario(CPF_VALIDO)
    u = User(id="u1", email="u@teste.local", hashed_password="x", full_name="Usuário", cpf_enc=enc)
    assert u.cpf_mascarado == "***.509.460-**"
    assert not hasattr(u, "cpf")


def test_migration_159_nao_cria_coluna_plaintext():
    from pathlib import Path
    text = Path("alembic/versions/159_user_cpf_secure.py").read_text()
    assert "cpf_enc" in text and "cpf_hash" in text
    assert "ADD COLUMN IF NOT EXISTS cpf " not in text
    assert 'down_revision = "158_case_partes_trabalhista_pii_expand"' in text
