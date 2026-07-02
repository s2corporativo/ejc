"""Criptografia de PII (CPF/CNPJ) — Bloco 6a. Não precisa de banco: são
primitivas criptográficas puras (a config de testes já gera chaves efêmeras
de dev em app/core/config.py — nunca em produção)."""
import pytest

from app.services.pii_crypto import (
    normalizar_documento, encrypt, decrypt, hash_documento,
)


def test_normalizar_documento():
    assert normalizar_documento("123.456.789-01") == "12345678901"
    assert normalizar_documento("12.345.678/0001-90") == "12345678000190"
    assert normalizar_documento(None) is None
    assert normalizar_documento("") is None
    assert normalizar_documento("   ") is None


def test_encrypt_decrypt_roundtrip():
    original = "12345678901"
    cifrado = encrypt(original)
    assert cifrado is not None
    assert cifrado != original  # não pode vazar em claro
    assert decrypt(cifrado) == original


def test_encrypt_none_passa_direto():
    assert encrypt(None) is None
    assert decrypt(None) is None


def test_encrypt_nao_e_deterministico():
    """Fernet usa IV aleatório — o mesmo valor cifrado duas vezes produz
    ciphertexts DIFERENTES (propriedade de segurança, não bug)."""
    a = encrypt("12345678901")
    b = encrypt("12345678901")
    assert a != b
    # mas ambos decifram para o mesmo original
    assert decrypt(a) == decrypt(b) == "12345678901"


def test_decrypt_ciphertext_invalido_levanta_erro():
    with pytest.raises(ValueError):
        decrypt("isto-nao-e-um-token-fernet-valido")


def test_hash_documento_e_deterministico():
    """Ao contrário de encrypt(), o hash é a peça que permite busca EXATA —
    por isso TEM que ser igual toda vez para o mesmo valor."""
    a = hash_documento("12345678901")
    b = hash_documento("12345678901")
    assert a == b
    assert len(a) == 64  # SHA-256 hex digest


def test_hash_documento_diferente_para_valores_diferentes():
    assert hash_documento("12345678901") != hash_documento("10987654321")


def test_hash_documento_none_passa_direto():
    assert hash_documento(None) is None
    assert hash_documento("") is None


def test_hash_nao_e_reversivel_para_o_documento():
    """Índice cego: o hash não deve conter nem permitir recuperar o CPF."""
    h = hash_documento("12345678901")
    assert "12345678901" not in h
