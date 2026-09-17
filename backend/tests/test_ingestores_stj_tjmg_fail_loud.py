from __future__ import annotations

import pytest


class _FakeDB:
    async def commit(self):
        return None

    async def rollback(self):
        return None


async def test_stj_falha_total_nao_vira_zero_sadio(monkeypatch):
    from app.services.ingestors import stj

    async def _quebra(*args, **kwargs):
        raise ConnectionError("portal fora")

    monkeypatch.setattr(stj, "fetch", _quebra)

    with pytest.raises(RuntimeError, match="todos os .* órgãos falharam"):
        await stj.ingerir(_FakeDB())


async def test_stj_contrato_invalido_em_todos_os_orgaos_falha(monkeypatch):
    from app.services.ingestors import stj

    async def _ultimo_json(_orgao):
        return {"url": "https://exemplo/stj.json"}

    async def _fetch(*args, **kwargs):
        class _R:
            def json(self):
                return {"erro": "contrato alterado"}
        return _R()

    monkeypatch.setattr(stj, "_ultimo_json", _ultimo_json)
    monkeypatch.setattr(stj, "fetch", _fetch)

    with pytest.raises(RuntimeError, match="contrato inválido"):
        await stj.ingerir(_FakeDB())


async def test_tjmg_falha_total_nao_vira_zero_sadio(monkeypatch):
    from app.services.ingestors import tjmg

    async def _quebra(*args, **kwargs):
        raise ConnectionError("TJMG fora")

    monkeypatch.setattr(tjmg, "buscar_tjmg", _quebra)

    with pytest.raises(RuntimeError, match="todos os .* temas"):
        await tjmg.ingerir(_FakeDB())


async def test_tjmg_falha_parcial_continua_tolerada(monkeypatch):
    from app.services.ingestors import tjmg

    chamadas = {"n": 0}

    async def _alternada(*args, **kwargs):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise ConnectionError("instabilidade")
        return []

    monkeypatch.setattr(tjmg, "buscar_tjmg", _alternada)

    assert await tjmg.ingerir(_FakeDB()) == (0, 0)
    assert chamadas["n"] > 1
