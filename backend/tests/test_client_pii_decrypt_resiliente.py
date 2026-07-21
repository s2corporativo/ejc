"""Cutover C6/LGPD — decifra resiliente para exibição em lote.

Uma linha com cpf_enc/cnpj_enc indecifrável (chave rotacionada ou ciphertext
corrompido) NÃO pode derrubar a listagem/busca/export inteira: como o
ClientResponse decifra CADA registro, um único InvalidToken faria a página
toda retornar 500. As propriedades cpf_plain/cnpj_plain degradam só a linha
afetada para o sentinela PII_INDECIFRAVEL. Teste unitário (sem DB).
"""
from __future__ import annotations

from cryptography.fernet import Fernet

from app.models.client import Client, PII_INDECIFRAVEL
from app.services import pii_crypto


def _com_chave(monkeypatch) -> None:
    # Chave Fernet válida e estável para este teste (o env de teste não define
    # PII_ENCRYPTION_KEY; sem ela decrypt() levanta RuntimeError, não o
    # InvalidToken/ValueError que queremos exercitar).
    monkeypatch.setattr(
        pii_crypto.settings, "PII_ENCRYPTION_KEY", Fernet.generate_key().decode()
    )


def test_cpf_enc_valido_decifra(monkeypatch):
    _com_chave(monkeypatch)
    c = Client(cpf_enc=pii_crypto.encrypt("12345678909"))
    assert c.cpf_plain == "12345678909"


def test_cpf_enc_indecifravel_vira_sentinela_sem_levantar(monkeypatch):
    _com_chave(monkeypatch)
    # Ciphertext cifrado com OUTRA chave (simula rotação): InvalidToken ao
    # decifrar com a chave atual. Não pode propagar — degrada para o sentinela.
    de_outra_chave = Fernet(Fernet.generate_key()).encrypt(b"12345678909").decode()
    c = Client(cpf_enc=de_outra_chave)
    assert c.cpf_plain == PII_INDECIFRAVEL
    assert c.documento_plain == PII_INDECIFRAVEL   # PF-first cai no sentinela


def test_enc_nulo_continua_none(monkeypatch):
    _com_chave(monkeypatch)
    c = Client()
    assert c.cpf_plain is None
    assert c.cnpj_plain is None
    assert c.documento_plain is None
