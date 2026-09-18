"""#1701 — falha total das OABs não pode virar sucesso 0/0 no ingestor DJEN."""
from __future__ import annotations

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

    with pytest.raises(djen.DjenContratoError, match="todas as OABs"):
        await djen.ingerir(_FakeDB())
