# ── tests/test_djen_consultar_oab.py ──────────────────────────────────────────
# Regressão: a API Comunica (DJEN) devolve ora {"items": [...]}, ora um array no
# topo. O código antigo fazia data.get("items", ...) mesmo quando data era lista
# → AttributeError engolido pelo except → advogado recebia ZERO intimações.
import app.services.djen_service as djen


async def test_consultar_oab_payload_lista_no_topo(monkeypatch):
    itens = [{"id": "1", "texto": "a"}, {"id": "2", "texto": "b"}]

    async def _fake(params):
        return itens

    monkeypatch.setattr(djen, "_djen_get", _fake)
    res = await djen.consultar_oab("123456", "MG")
    assert res == itens


async def test_consultar_oab_payload_dict_com_items(monkeypatch):
    itens = [{"id": "9"}]

    async def _fake(params):
        return {"items": itens, "total": 1}

    monkeypatch.setattr(djen, "_djen_get", _fake)
    res = await djen.consultar_oab("123456", "MG")
    assert res == itens


async def test_consultar_oab_dict_sem_items_retorna_vazio(monkeypatch):
    async def _fake(params):
        return {"total": 0}

    monkeypatch.setattr(djen, "_djen_get", _fake)
    assert await djen.consultar_oab("123456", "MG") == []


async def test_consultar_oab_erro_retorna_vazio(monkeypatch):
    async def _fake(params):
        raise RuntimeError("boom")

    monkeypatch.setattr(djen, "_djen_get", _fake)
    assert await djen.consultar_oab("123456", "MG") == []
