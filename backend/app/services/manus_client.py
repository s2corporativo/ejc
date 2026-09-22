from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings


class ManusDisabledError(RuntimeError):
    pass


class ManusAPIError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class ManusClient:
    """Cliente mínimo para Manus API v2, sem registrar conteúdo sensível."""

    def __init__(self, *, api_key: str | None = None, base_url: str | None = None):
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.MANUS_API_KEY
        self.base_url = (base_url or settings.MANUS_API_BASE_URL).rstrip("/")
        self.timeout = httpx.Timeout(
            settings.MANUS_CONNECT_TIMEOUT,
            read=settings.MANUS_READ_TIMEOUT,
            write=settings.MANUS_WRITE_TIMEOUT,
            pool=settings.MANUS_CONNECT_TIMEOUT,
        )

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ManusDisabledError("MANUS_API_KEY não configurada")
        return {
            "x-manus-api-key": self.api_key,
            "Content-Type": "application/json",
        }

    async def create_task(
        self,
        *,
        content: str,
        structured_output_schema: dict[str, Any],
        title: str,
        agent_profile: str,
    ) -> dict[str, Any]:
        payload = {
            "message": {
                "content": content,
                # Não herdar conectores/skills default da conta Manus.
                # Esta integração é somente raciocínio, sem ações externas.
                "connectors": [],
                "enable_skills": [],
                "force_skills": [],
                "task_references": [],
            },
            "locale": "pt-BR",
            "interactive_mode": False,
            "hide_in_task_list": True,
            "share_visibility": "private",
            "agent_profile": agent_profile,
            "title": title,
            "structured_output_schema": structured_output_schema,
        }
        return await self._request("POST", "/v2/task.create", json=payload)

    async def list_messages(self, task_id: str) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/v2/task.listMessages",
            params={"task_id": task_id, "order": "desc", "limit": 50},
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method,
                    f"{self.base_url}{path}",
                    headers=self._headers(),
                    **kwargs,
                )
                response.raise_for_status()
                data = response.json()
        except ManusDisabledError:
            raise
        except httpx.TimeoutException as exc:
            raise ManusAPIError("Manus indisponível por timeout", code="timeout") from exc
        except httpx.HTTPStatusError as exc:
            code = None
            try:
                body = exc.response.json()
                if isinstance(body, dict):
                    error = body.get("error") or {}
                    if isinstance(error, dict):
                        code = error.get("code")
            except ValueError:
                pass
            raise ManusAPIError(
                "Manus recusou a requisição",
                code=code,
                status_code=exc.response.status_code,
            ) from None
        except (httpx.HTTPError, ValueError) as exc:
            raise ManusAPIError(
                "Falha de comunicação com a Manus",
                code="transport",
            ) from exc

        if not isinstance(data, dict) or data.get("ok") is not True:
            error = data.get("error") if isinstance(data, dict) else {}
            raise ManusAPIError(
                "Manus retornou resposta inválida",
                code=error.get("code") if isinstance(error, dict) else "invalid_response",
            )
        return data
