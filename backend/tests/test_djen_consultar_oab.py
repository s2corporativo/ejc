# ── tests/test_djen_consultar_oab.py ──────────────────────────────────────────
# A API Comunica pode devolver envelope ou lista. Falha externa não equivale a
# consulta válida com zero comunicações.
import app.services.djen_service as djen


async def test_consultar_oab_payload_lista_no_topo(monkeypatch):
    itens = [{"id": "1", "texto": "a"}, {"id": "2", "texto": "b"}]

    async def _fake(params):
        return itens

    monkeypatch.setattr(djen, "_djen_get", _fake)
    resultado = await djen.consultar_oab("123456", "MG")
    assert resultado.fonte_ok is True
    assert resultado.items == itens
    assert resultado.recebidas == 2


async def test_consultar_oab_payload_dict_com_items(monkeypatch):
    itens = [{"id": "9"}]

    async def _fake(params):
        return {"items": itens, "total": 1}

    monkeypatch.setattr(djen, "_djen_get", _fake)
    resultado = await djen.consultar_oab("123456", "MG")
    assert resultado.fonte_ok is True
    assert resultado.items == itens


async def test_consultar_oab_dict_sem_items_e_zero_legitimo(monkeypatch):
    async def _fake(params):
        return {"total": 0}

    monkeypatch.setattr(djen, "_djen_get", _fake)
    resultado = await djen.consultar_oab("123456", "MG")
    assert resultado.fonte_ok is True
    assert resultado.items == []
    assert resultado.erro is None


async def test_consultar_oab_erro_nao_retorna_sucesso_vazio(monkeypatch):
    async def _fake(params):
        raise RuntimeError("segredo-nao-pode-vazar")

    monkeypatch.setattr(djen, "_djen_get", _fake)
    resultado = await djen.consultar_oab("123456", "MG")
    assert resultado.fonte_ok is False
    assert resultado.items == []
    assert resultado.erro == "erro_interno"
    assert "segredo-nao-pode-vazar" not in str(resultado.to_dict())
