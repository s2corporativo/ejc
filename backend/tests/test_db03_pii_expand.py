"""DB-03 Fase A — PII de partes/CID cifrada sem quebrar contratos de API."""
from __future__ import annotations

from cryptography.fernet import Fernet


def _configurar_chaves(monkeypatch):
    from app.services import pii_crypto

    monkeypatch.setattr(
        pii_crypto.settings,
        "PII_ENCRYPTION_KEY",
        Fernet.generate_key().decode(),
    )
    monkeypatch.setattr(pii_crypto.settings, "PII_HASH_KEY", "db03-hash-key-test-only")


def test_case_parte_nova_nao_persiste_plaintext(monkeypatch):
    _configurar_chaves(monkeypatch)
    from app.models.case_parte import CaseParte
    from app.services.pii_crypto import hash_documento, normalizar_documento

    parte = CaseParte(id="p1", case_id="c1", tipo="autor", nome="Pessoa Fictícia")
    parte.cpf_cnpj = "153.509.460-56"
    parte.email = " pessoa@example.test "
    parte.telefone = "(31) 99999-9999"

    assert parte._cpf_cnpj_legacy is None
    assert parte._email_legacy is None
    assert parte._telefone_legacy is None
    assert parte.cpf_cnpj_enc and "153.509" not in parte.cpf_cnpj_enc
    assert parte.email_enc and "example.test" not in parte.email_enc
    assert parte.telefone_enc and "99999" not in parte.telefone_enc
    assert parte.cpf_cnpj_hash == hash_documento(normalizar_documento("153.509.460-56"))

    # Contrato externo preservado: o valor de apresentação volta sob demanda.
    assert parte.cpf_cnpj == "153.509.460-56"
    assert parte.email == "pessoa@example.test"
    assert parte.telefone == "(31) 99999-9999"


def test_case_parte_le_plaintext_legado_apenas_sem_ciphertext(monkeypatch):
    _configurar_chaves(monkeypatch)
    from app.models.case_parte import CaseParte

    parte = CaseParte(id="p2", case_id="c1", tipo="reu", nome="Legado")
    parte._cpf_cnpj_legacy = "390.533.447-05"
    parte._email_legacy = "legado@example.test"
    parte._telefone_legacy = "3133334444"

    assert parte.cpf_cnpj == "390.533.447-05"
    assert parte.email == "legado@example.test"
    assert parte.telefone == "3133334444"

    # Nova atribuição faz cutover daquela linha e limpa o legado.
    parte.cpf_cnpj = "390.533.447-05"
    parte.email = "novo@example.test"
    parte.telefone = "31988887777"
    assert parte._cpf_cnpj_legacy is None
    assert parte._email_legacy is None
    assert parte._telefone_legacy is None


def test_cid_trabalhista_cifrado_e_nao_exposto_como_ciphertext(monkeypatch):
    _configurar_chaves(monkeypatch)
    from app.models.especializado import TrabalhistaCase
    from app.routers.ramos_comum import _serialize

    trab = TrabalhistaCase(id="t1", case_id="c1", tipo="acidente_trabalho")
    trab.cid = "S93.4"

    assert trab._cid_legacy is None
    assert trab.cid_enc and "S93.4" not in trab.cid_enc
    assert trab.cid == "S93.4"

    data = _serialize(trab)
    assert data["cid"] == "S93.4"
    assert "cid_enc" not in data


def test_cid_legado_continua_legivel_ate_cutover(monkeypatch):
    _configurar_chaves(monkeypatch)
    from app.models.especializado import TrabalhistaCase

    trab = TrabalhistaCase(id="t2", case_id="c2", tipo="acidente_trabalho")
    trab._cid_legacy = "M54.5"
    assert trab.cid == "M54.5"
    trab.cid = "M54.6"
    assert trab._cid_legacy is None
    assert trab.cid == "M54.6"
