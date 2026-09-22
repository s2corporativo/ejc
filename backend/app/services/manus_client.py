from __future__ import annotations

import base64
import hashlib
import logging
import time
from typing import Any

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from app.core.config import get_settings

logger = logging.getLogger("ejc.manus")


class ManusDisabledError(RuntimeError):
    pass


class ManusAPIError(RuntimeError):
    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class ManusClient:
    """Cliente mínimo e sem estado para a Manus API v2.

    O cliente não registra corpo de requisição, chave, resposta ou PII em logs.
    A política de autorização/sanitização fica no serviço chamador.
    """

    def __init__(self, *, base_url: str | None = None, api_key: str | None = None):
        settings = get_settings()
        self.base_url = (base_url or settings.MANUS_API_BASE_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.MANUS_API_KEY
        self.timeout = httpx.Timeout(
            settings.MANUS_CONNECT_TIMEOUT,
            read=settings.MANUS_READ_TIMEOUT,
            write=settings.MANUS_WRITE_TIMEOUT,
            pool=settings.MANUS_CONNECT_TIMEOUT,
        )

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ManusDisabledError("MANUS_API_KEY não configurada")
        return {"x-manus-api-key": self.api_key, "Content-Type": "application/json"}

    async def create_task(
        self,
        *,
        content: str,
        title: str,
        structured_output_schema: dict[str, Any],
        agent_profile: str = "standard",
    ) -> dict[str, Any]:
        payload = {
            "message": {"content": [{"type": "text", "text": content, "visibility": "visible"}]},
            "agent_profile": agent_profile,
            "title": title,
            "hide_in_task_list": True,
            "share_visibility": "private",
            "interactive_mode": False,
            "structured_output_schema": structured_output_schema,
        }
        return await self._request("POST", "/v2/task.create", json=payload)

    async def get_messages(self, task_id: str) -> dict[str, Any]:
        return await self._request(
            "GET", "/v2/task.listMessages", params={"task_id": task_id, "order": "desc", "limit": 20}
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method, f"{self.base_url}{path}", headers=self._headers(), **kwargs
                )
                response.raise_for_status()
                data = response.json()
        except ManusDisabledError:
            raise
        except httpx.TimeoutException as exc:
            raise ManusAPIError("Manus indisponível por timeout", code="timeout") from exc
        except httpx.HTTPStatusError as exc:
            # Não usar response.text: a API pode ecoar conteúdo sensível.
            code = None
            try:
                body = exc.response.json()
                code = ((body.get("error") or {}).get("code") if isinstance(body, dict) else None)
            except ValueError:
                pass
            raise ManusAPIError(
                "Manus recusou a requisição", code=code, status_code=exc.response.status_code
            ) from None
        except (httpx.HTTPError, ValueError) as exc:
            raise ManusAPIError("Falha de comunicação com a Manus", code="transport") from exc
        if not isinstance(data, dict) or data.get("ok") is False:
            error = data.get("error") if isinstance(data, dict) else {}
            raise ManusAPIError(
                "Manus retornou uma resposta inválida",
                code=error.get("code") if isinstance(error, dict) else "invalid_response",
            )
        return data


def verify_manus_webhook(
    *, public_key_pem: str, url: str, body: bytes, signature_b64: str, timestamp: str, now: int | None = None
) -> bool:
    """Verifica assinatura RSA-SHA256 e janela de cinco minutos da Manus."""
    try:
        ts = int(timestamp)
        if abs((now or int(time.time())) - ts) > 300:
            return False
        body_hash = hashlib.sha256(body).hexdigest()
        signed_content = f"{ts}.{url}.{body_hash}".encode()
        public_key = serialization.load_pem_public_key(public_key_pem.encode())
        public_key.verify(
            base64.b64decode(signature_b64, validate=True),
            signed_content,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except (ValueError, TypeError, InvalidSignature, IndexError):
        return False
