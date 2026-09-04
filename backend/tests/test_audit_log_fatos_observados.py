"""Regressão: auditoria WORM não pode transformar intenção em fato observado."""

from app.models.audit_log import _normalizar_fatos_observados


def test_delete_documento_nao_afirma_storage_preservado_sem_verificacao():
    original = {"storage": "drive", "storage_preservado": True}

    normalizado = _normalizar_fatos_observados("documents", "DELETE", original)

    assert normalizado == {
        "storage": "drive",
        "storage_preservacao_intencao": True,
        "storage_verificado": False,
    }
    assert original == {"storage": "drive", "storage_preservado": True}


def test_verificacao_explicita_do_storage_e_preservada_sem_reinterpretacao():
    payload = {
        "storage": "drive",
        "storage_preservado": True,
        "storage_verificado": True,
    }

    assert _normalizar_fatos_observados("documents", "DELETE", payload) == payload


def test_normalizacao_e_restrita_ao_delete_de_documents():
    payload = {"storage_preservado": True}

    assert _normalizar_fatos_observados("documents", "UPDATE", payload) == payload
    assert _normalizar_fatos_observados("outra_entidade", "DELETE", payload) == payload


def test_payload_nulo_permanece_nulo():
    assert _normalizar_fatos_observados("documents", "DELETE", None) is None
