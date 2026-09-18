"""#1701 — falha total das OABs não pode virar sucesso 0/0 no ingestor DJEN."""
from __future__ import annotations

import httpx
import pytest

from app.core.config import get_settings
from app.services.ingestors import djen


class _FakeDB:
    async def commit(self):
        pass

    async def rollback(self):
        pass


@pytest.mark.asyncio
async def test_todas_oabs_falham_falha_alto(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "DJEN_OABS_MONITORADAS", "12345/MG,67890/MG")
    monkeypatch.setattr(settings, "DJEN_INGEST_JANELA_DIAS", 2)

    async def _falha(*args, **kwargs):
        raise RuntimeError("upstream indisponível")

    monkeypatch.setattr(djen, "_coletar_oab", _falha)

    with pytest.raises(djen.DjenContratoError, match="todas as OABs") as exc:
        await djen.ingerir(_FakeDB())

    mensagem = str(exc.value)
    assert "oabs_total=2" in mensagem
    assert "causas=erro_interno:2" in mensagem
    assert "12345" not in mensagem
    assert "67890" not in mensagem


@pytest.mark.asyncio
async def test_falha_total_explica_geo_bloqueado_sem_expor_oab(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "DJEN_OABS_MONITORADAS", "12345/MG,67890/MG")
    monkeypatch.setattr(settings, "DJEN_INGEST_JANELA_DIAS", 2)

    request = httpx.Request("GET", "https://comunicaapi.pje.jus.br/api/v1/comunicacao")
    response = httpx.Response(
        403,
        request=request,
        text="The Amazon CloudFront distribution is configured to block access from your country.",
    )

    async def _falha(*args, **kwargs):
        raise httpx.HTTPStatusError("HTTP 403", request=request, response=response)

    monkeypatch.setattr(djen, "_coletar_oab", _falha)

    with pytest.raises(djen.DjenContratoError) as exc:
        await djen.ingerir(_FakeDB())

    mensagem = str(exc.value)
    assert "oabs_total=2" in mensagem
    assert "causas=geo_bloqueado:2" in mensagem
    assert "12345" not in mensagem
    assert "67890" not in mensagem
