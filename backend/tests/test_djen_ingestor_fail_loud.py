from __future__ import annotations

import pytest

from app.services.ingestors import djen


async def test_json_invalido_na_primeira_pagina_falha_alto(monkeypatch):
    """Fonte que não respondeu não pode ser interpretada como 'sem intimação'."""

    async def _fetch_html(*args, **kwargs):
        class _Resposta:
            def json(self):
                raise ValueError("não é JSON")

        return _Resposta()

    monkeypatch.setattr(djen, "fetch", _fetch_html)

    with pytest.raises(djen.DjenContratoError, match="primeira página"):
        await djen._coletar_oab("123456", "MG", "2026-09-01", "2026-09-04")


async def test_json_invalido_apos_primeira_pagina_preserva_itens_colhidos(monkeypatch):
    """Falha posterior não apaga comunicações reais já recebidas."""
    chamadas = {"n": 0}
    cheia = [{"id": i} for i in range(djen.ITENS_POR_PAGINA)]

    async def _fetch(*args, **kwargs):
        chamadas["n"] += 1
        pagina = chamadas["n"]

        class _Resposta:
            def json(self):
                if pagina == 1:
                    return {"items": cheia}
                raise ValueError("não é JSON")

        return _Resposta()

    monkeypatch.setattr(djen, "fetch", _fetch)
    monkeypatch.setattr(djen, "PAUSA_ENTRE_PAGINAS", 0)

    itens = await djen._coletar_oab("123456", "MG", "2026-09-01", "2026-09-04")
    assert len(itens) == djen.ITENS_POR_PAGINA
