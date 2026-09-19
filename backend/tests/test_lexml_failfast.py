from __future__ import annotations

import pytest

import app.services.ingestors.lexml as lexml
from app.services.jurisprudencia_externa import LexMLBloqueadoError


class _FakeDB:
    pass


async def test_lexml_antibot_interrompe_plano_na_primeira_consulta(monkeypatch):
    chamadas = 0

    monkeypatch.setattr(
        lexml,
        "_plano_federacao",
        lambda cfg: [
            ("consulta 1", "legislacao", None),
            ("consulta 2", "jurisprudencia", None),
            ("consulta 3", "legislacao", None),
        ],
    )

    async def bloqueado(*args, **kwargs):
        nonlocal chamadas
        chamadas += 1
        raise LexMLBloqueadoError("desafio anti-bot")

    monkeypatch.setattr(lexml, "buscar_lexml", bloqueado)

    with pytest.raises(LexMLBloqueadoError, match="interrompida"):
        await lexml.ingerir(_FakeDB())

    assert chamadas == 1
