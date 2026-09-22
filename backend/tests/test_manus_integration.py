from __future__ import annotations

import base64
import hashlib
import time

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from pydantic import ValidationError

from app.core.config import Settings
from app.routers.manus import ManusAnalysisRequest
from app.services.manus_client import verify_manus_webhook
from app.services.manus_service import MANUS_CASE_INTELLIGENCE_SCHEMA


def _assinatura(private_key, *, url: str, body: bytes, timestamp: int) -> str:
    body_hash = hashlib.sha256(body).hexdigest()
    signed = f"{timestamp}.{url}.{body_hash}".encode()
    signature = private_key.sign(signed, padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(signature).decode()


def test_manus_nasce_desligada_e_sem_chave():
    settings = Settings()
    assert settings.MANUS_API_ENABLED is False
    assert settings.MANUS_API_KEY == ""
    assert settings.MANUS_API_BASE_URL == "https://api.manus.ai"


def test_schema_manus_obedece_regras_de_structured_output():
    schema = MANUS_CASE_INTELLIGENCE_SCHEMA
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])


def test_request_manus_rejeita_profile_invalido():
    with pytest.raises(ValidationError):
        ManusAnalysisRequest(case_id="case-1", texto="x" * 30, profile="unsafe")


def test_webhook_manus_verifica_assinatura_e_janela_temporal():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    body = b'{"event_type":"task_created"}'
    url = "https://ejc.example/api/manus/webhook"
    timestamp = int(time.time())
    signature = _assinatura(private, url=url, body=body, timestamp=timestamp)

    assert verify_manus_webhook(
        public_key_pem=public_pem, url=url, body=body,
        signature_b64=signature, timestamp=str(timestamp), now=timestamp,
    ) is True
    assert verify_manus_webhook(
        public_key_pem=public_pem, url=url, body=body,
        signature_b64=signature, timestamp=str(timestamp - 301), now=timestamp,
    ) is False
    assert verify_manus_webhook(
        public_key_pem=public_pem, url=url, body=b"{}",
        signature_b64=signature, timestamp=str(timestamp), now=timestamp,
    ) is False
