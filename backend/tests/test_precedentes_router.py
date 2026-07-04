"""Router /precedentes/buscar — filtra fontes e delega ao crawler agregador."""
import pytest

from app.routers import precedentes as pr

# Chama a função sem o wrapper de rate-limit do slowapi (que exige um Request real).
buscar = pr.buscar.__wrapped__
BuscaReq = pr.BuscaReq


class _User:
    id = "u1"
    role = type("R", (), {"value": "advogado"})()


async def test_buscar_delega_ao_agregador(monkeypatch):
    captured = {}

    async def fake_agg(*, termo, fontes, numero_cnj):
        captured["termo"] = termo
        captured["fontes"] = fontes
        captured["numero_cnj"] = numero_cnj
        return {"status": "success", "total_encontrado": 0, "precedentes": [], "fontes": {}}

    monkeypatch.setattr("app.services.crawler_precedentes.buscar_precedentes", fake_agg)

    r = await buscar(
        BuscaReq(termo="dano moral", fontes=["stj", "stf"], numero_cnj=None),
        request=None,
        cu=_User(),
    )
    assert r["status"] == "success"
    assert captured["fontes"] == ["stj", "stf"]


async def test_buscar_descarta_fonte_invalida_e_cai_no_default(monkeypatch):
    captured = {}

    async def fake_agg(*, termo, fontes, numero_cnj):
        captured["fontes"] = fontes
        return {"status": "success", "precedentes": [], "total_encontrado": 0, "fontes": {}}

    monkeypatch.setattr("app.services.crawler_precedentes.buscar_precedentes", fake_agg)

    await buscar(BuscaReq(termo="x", fontes=["invalida"]), request=None, cu=_User())
    # Nenhuma fonte válida → default seguro ["stj"].
    assert captured["fontes"] == ["stj"]
