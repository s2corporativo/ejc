from __future__ import annotations


class _FakeDB:
    async def commit(self):
        return None

    async def rollback(self):
        return None


async def test_stj_falha_parcial_continua_tolerada(monkeypatch):
    from app.services.ingestors import stj

    chamadas = {"n": 0}

    async def _ultimo_json(_orgao):
        return {"url": "https://exemplo/stj.json"}

    async def _fetch(*args, **kwargs):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise ConnectionError("um órgão fora")

        class _Resposta:
            def json(self):
                return []

        return _Resposta()

    monkeypatch.setattr(stj, "_ultimo_json", _ultimo_json)
    monkeypatch.setattr(stj, "fetch", _fetch)

    assert await stj.ingerir(_FakeDB()) == (0, 0)
    assert chamadas["n"] > 1
