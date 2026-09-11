from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.models.user import User
from app.routers.users import (
    _commit_usuario_com_cpf_guard,
    _integrity_e_duplicidade_cpf_usuario,
    _preparar_cpf_usuario,
)
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


class _OrigCpf(Exception):
    constraint_name = "ux_users_cpf_hash_active"


class _DiagCpf:
    constraint_name = "ux_users_cpf_hash_active"


class _OrigCpfDiag(Exception):
    diag = _DiagCpf()


class _OrigOutra(Exception):
    constraint_name = "uq_users_email_active"


def _integrity(orig: Exception) -> IntegrityError:
    return IntegrityError("INSERT", {}, orig)


def test_integrity_cpf_reconhece_somente_constraint_exata():
    assert _integrity_e_duplicidade_cpf_usuario(_integrity(_OrigCpf())) is True
    assert _integrity_e_duplicidade_cpf_usuario(_integrity(_OrigCpfDiag())) is True
    assert _integrity_e_duplicidade_cpf_usuario(_integrity(_OrigOutra())) is False


class _DbCommitFalha:
    def __init__(self, exc: IntegrityError):
        self.exc = exc
        self.rollback_executado = False

    async def commit(self):
        raise self.exc

    async def rollback(self):
        self.rollback_executado = True


async def test_commit_guard_traduz_corrida_cpf_para_409():
    db = _DbCommitFalha(_integrity(_OrigCpf()))
    with pytest.raises(HTTPException) as exc:
        await _commit_usuario_com_cpf_guard(db)
    assert exc.value.status_code == 409
    assert db.rollback_executado is True


async def test_commit_guard_nao_mascara_integrity_error_nao_relacionado():
    original = _integrity(_OrigOutra())
    db = _DbCommitFalha(original)
    with pytest.raises(IntegrityError) as exc:
        await _commit_usuario_com_cpf_guard(db)
    assert exc.value is original
    assert db.rollback_executado is True
