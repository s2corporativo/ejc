# ── tests/test_djen_consultar_oab.py ──────────────────────────────────────────
# A API Comunica pode devolver envelope ou lista. Falha externa não equivale a
# consulta válida com zero comunicações, e janela truncada não equivale a sucesso.
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
    assert resultado.paginas == 1
    assert resultado.janela_dias == djen.JANELA_RECONCILIACAO_DIAS


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
    assert resultado.paginas == 1


async def test_consultar_oab_pagina_ate_provar_exaustao(monkeypatch):
    primeiro_lote = [
        {"id": f"p1-{indice}", "texto": "a"}
        for indice in range(djen.ITENS_POR_PAGINA)
    ]
    segundo_lote = [{"id": "p2-1", "texto": "b"}]
    paginas_chamadas = []

    async def _fake(params):
        paginas_chamadas.append(params["pagina"])
        if params["pagina"] == 1:
            return {"items": primeiro_lote}
        return {"items": segundo_lote}

    monkeypatch.setattr(djen, "_djen_get", _fake)
    resultado = await djen.consultar_oab("123456", "MG")

    assert resultado.fonte_ok is True
    assert resultado.recebidas == djen.ITENS_POR_PAGINA + 1
    assert resultado.paginas == 2
    assert paginas_chamadas == [1, 2]


async def test_consultar_oab_deduplica_id_repetido_entre_paginas(monkeypatch):
    monkeypatch.setattr(djen, "ITENS_POR_PAGINA", 2)

    async def _fake(params):
        if params["pagina"] == 1:
            return {"items": [{"id": "1"}, {"id": "2"}]}
        return {"items": [{"id": "2"}]}

    monkeypatch.setattr(djen, "_djen_get", _fake)
    resultado = await djen.consultar_oab("123456", "MG")

    assert resultado.fonte_ok is True
    assert [item["id"] for item in resultado.items] == ["1", "2"]
    assert resultado.paginas == 2


async def test_consultar_oab_teto_cheio_falha_sem_processar_parcial(monkeypatch):
    monkeypatch.setattr(djen, "ITENS_POR_PAGINA", 2)
    monkeypatch.setattr(djen, "MAX_PAGINAS", 2)

    async def _fake(params):
        pagina = params["pagina"]
        return {
            "items": [
                {"id": f"{pagina}-1"},
                {"id": f"{pagina}-2"},
            ]
        }

    monkeypatch.setattr(djen, "_djen_get", _fake)
    resultado = await djen.consultar_oab("123456", "MG")

    assert resultado.fonte_ok is False
    assert resultado.items == []
    assert resultado.recebidas == 0
    assert resultado.erro == "paginacao_truncada"
    assert resultado.paginas == 2


async def test_consultar_oab_limita_janela_a_intervalo_seguro(monkeypatch):
    parametros = []

    async def _fake(params):
        parametros.append(params)
        return {"items": []}

    monkeypatch.setattr(djen, "_djen_get", _fake)

    minimo = await djen.consultar_oab("123456", "MG", dias=0)
    maximo = await djen.consultar_oab("123456", "MG", dias=999)

    assert minimo.janela_dias == 1
    assert maximo.janela_dias == 90
    assert parametros[0]["itensPorPagina"] == djen.ITENS_POR_PAGINA
    assert parametros[0]["pagina"] == 1
    assert parametros[1]["pagina"] == 1


async def test_consultar_oab_erro_nao_retorna_sucesso_vazio(monkeypatch):
    async def _fake(params):
        raise RuntimeError("segredo-nao-pode-vazar")

    monkeypatch.setattr(djen, "_djen_get", _fake)
    resultado = await djen.consultar_oab("123456", "MG")
    assert resultado.fonte_ok is False
    assert resultado.items == []
    assert resultado.erro == "erro_interno"
    assert "segredo-nao-pode-vazar" not in str(resultado.to_dict())
