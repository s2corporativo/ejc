# ── tests/test_jurisprudencia_externa_fontes.py ───────────────────────────────
# Regressão: buscar_todas_fontes usava asyncio.coroutine(...) (REMOVIDO no
# Python 3.11) para a fonte desabilitada → AttributeError, quebrando a busca
# sempre que apenas UMA fonte era selecionada.
import app.services.jurisprudencia_externa as je


async def test_apenas_lexml_nao_quebra(monkeypatch):
    async def _lexml(palavras, pagina=1, por_pagina=10):
        return [{"titulo": "acórdão X"}]

    async def _tjmg(*a, **k):  # não deve ser chamado
        raise AssertionError("tjmg não deveria ser consultado")

    monkeypatch.setattr(je, "buscar_lexml", _lexml)
    monkeypatch.setattr(je, "buscar_tjmg", _tjmg)

    res = await je.buscar_todas_fontes("dano moral", fontes=["lexml"])
    assert res["total"] == 1
    assert res["fontes"]["lexml"]["total"] == 1
    assert res["fontes"]["tjmg"]["total"] == 0
    assert res["fontes"]["tjmg"]["itens"] == []
    assert res["todos"] == [{"titulo": "acórdão X"}]


async def test_apenas_tjmg_nao_quebra(monkeypatch):
    async def _tjmg(palavras, pagina=1, por_pagina=10):
        return [{"titulo": "ementa Y"}]

    monkeypatch.setattr(je, "buscar_tjmg", _tjmg)

    res = await je.buscar_todas_fontes("consumidor", fontes=["tjmg"])
    assert res["total"] == 1
    assert res["fontes"]["lexml"]["total"] == 0
    assert res["fontes"]["tjmg"]["total"] == 1
