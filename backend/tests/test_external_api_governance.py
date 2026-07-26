"""Regressões de governança dos adaptadores de APIs externas.

Sem rede: cobre classificação de retry, HTTP 204, estados de configuração e
a distinção entre "não encontrado" e falha do DataJud.
"""
from __future__ import annotations

import httpx
import pytest

from app.core.config import Settings, get_settings
from app.services import datajud_service
from app.services.integration_status import build_integration_status


def _status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.test/recurso")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError(
        f"status {status}", request=request, response=response
    )


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_datajud_nao_repete_erro_de_contrato_ou_credencial(status):
    assert datajud_service._erro_datajud_transitorio(_status_error(status)) is False


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_datajud_repete_apenas_rate_limit_e_5xx(status):
    assert datajud_service._erro_datajud_transitorio(_status_error(status)) is True


async def test_datajud_desligado_nao_vira_processo_ausente(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "DATAJUD_ENABLED", False)
    monkeypatch.setattr(settings, "DATAJUD_API_KEY", "")

    with pytest.raises(datajud_service.DataJudDesabilitadoError):
        await datajud_service.consultar_processo(
            "0000001-02.2020.8.13.0000"
        )


async def test_datajud_propaga_falha_upstream_em_vez_de_none(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "DATAJUD_ENABLED", True)
    monkeypatch.setattr(settings, "DATAJUD_API_KEY", "chave-teste")

    async def _falha(*args, **kwargs):
        raise _status_error(503)

    monkeypatch.setattr(datajud_service, "_datajud_search", _falha)
    with pytest.raises(httpx.HTTPStatusError):
        await datajud_service.consultar_processo(
            "0000001-02.2020.8.13.0000"
        )


def test_defaults_e_status_de_acesso_sao_explicitos():
    settings = Settings(
        _env_file=None,
        APP_ENV="development",
        DATAJUD_ENABLED=True,
        DATAJUD_API_KEY="segredo-que-nao-pode-sair",
    )
    assert settings.DATAJUD_TIMEOUT_SECONDS > 0

    payload = build_integration_status(settings)
    items = {item["key"]: item for item in payload["items"]}
    assert items["datajud"]["mode"] == "APIKey pública rotativa (CNJ)"
    assert "consulta anônima" in items["cadastros_publicos"]["mode"]
    assert "segredo-que-nao-pode-sair" not in str(payload)
