"""Ingestor que falha em TUDO não pode reportar execução sadia.

Classe de defeito recorrente nesta base: `except` por item/tema/órgão que
segue adiante é correto para falha PARCIAL, mas quando a falha é TOTAL o
retorno `(0, 0)` fica indistinguível de "a fonte não tinha nada novo". Foi
assim que a federação LexML e o monitor do DOU passaram tempo indeterminado
entregando zero com o painel verde.

Estes testes travam a distinção nos ingestores que ainda não a tinham. Os
casos PARCIAIS continuam tolerados — é essa a diferença que importa.
"""
from __future__ import annotations

import pytest


class _FakeDB:
    async def commit(self):
        return None

    async def rollback(self):
        return None


# ── STJ ──────────────────────────────────────────────────────────────────────

async def test_stj_todos_os_orgaos_falhando_levanta(monkeypatch):
    from app.services.ingestors import stj

    async def _fetch_quebrado(*a, **k):
        raise ConnectionError("portal fora")

    monkeypatch.setattr(stj, "fetch", _fetch_quebrado)

    with pytest.raises(RuntimeError, match="todos os .* órgãos falharam"):
        await stj.ingerir(_FakeDB())


async def test_stj_falha_parcial_segue_e_reporta_zero(monkeypatch):
    """Um órgão fora não invalida a execução — só todos."""
    from app.services.ingestors import stj

    chamadas = {"n": 0}

    async def _fetch_alternado(*a, **k):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise ConnectionError("um órgão fora")

        class _R:
            def json(self):
                return []          # lista válida, sem acórdãos

        return _R()

    async def _ultimo_json_ok(orgao):
        return {"url": "https://exemplo/stj.json"}

    monkeypatch.setattr(stj, "fetch", _fetch_alternado)
    monkeypatch.setattr(stj, "_ultimo_json", _ultimo_json_ok)

    assert await stj.ingerir(_FakeDB()) == (0, 0)
    assert chamadas["n"] > 1


async def test_stj_contrato_invalido_em_todos_tambem_levanta(monkeypatch):
    """Resposta que deixou de ser lista é falha, não 'órgão sem acórdãos'."""
    from app.services.ingestors import stj

    async def _ultimo_json_ok(orgao):
        return {"url": "https://exemplo/stj.json"}

    async def _fetch_html(*a, **k):
        class _R:
            def json(self):
                return {"erro": "portal reformulado"}   # dict, não lista

        return _R()

    monkeypatch.setattr(stj, "_ultimo_json", _ultimo_json_ok)
    monkeypatch.setattr(stj, "fetch", _fetch_html)

    with pytest.raises(RuntimeError, match="contrato"):
        await stj.ingerir(_FakeDB())


# ── TJMG ─────────────────────────────────────────────────────────────────────

async def test_tjmg_todos_os_temas_falhando_levanta(monkeypatch):
    from app.services.ingestors import tjmg

    async def _busca_quebrada(*a, **k):
        raise ConnectionError("TJMG fora")

    monkeypatch.setattr(tjmg, "buscar_tjmg", _busca_quebrada)

    with pytest.raises(RuntimeError, match="todos os .* temas"):
        await tjmg.ingerir(_FakeDB())


async def test_tjmg_falha_parcial_nao_levanta(monkeypatch):
    from app.services.ingestors import tjmg

    chamadas = {"n": 0}

    async def _busca_alternada(*a, **k):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise ConnectionError("instabilidade")
        return []

    monkeypatch.setattr(tjmg, "buscar_tjmg", _busca_alternada)

    novos, total = await tjmg.ingerir(_FakeDB())
    assert (novos, total) == (0, 0)
    assert chamadas["n"] > 1


# ── DJEN ─────────────────────────────────────────────────────────────────────

async def test_djen_json_invalido_na_primeira_pagina_levanta(monkeypatch):
    """Num sistema de PRAZOS, 'a fonte não respondeu' virar 'sem intimação'
    é o erro mais caro possível."""
    from app.services.ingestors import djen

    async def _fetch_html(*a, **k):
        class _R:
            def json(self):
                raise ValueError("não é JSON")

        return _R()

    monkeypatch.setattr(djen, "fetch", _fetch_html)

    with pytest.raises(djen.DjenContratoError, match="primeira página"):
        await djen._coletar_oab("123456", "MG", "2026-09-01", "2026-09-04")


async def test_djen_json_invalido_em_pagina_seguinte_aproveita_o_colhido(monkeypatch):
    """Depois da primeira página já há itens reais: parar e usá-los é correto."""
    from app.services.ingestors import djen

    chamadas = {"n": 0}
    cheia = [{"id": i} for i in range(djen.ITENS_POR_PAGINA)]

    async def _fetch(*a, **k):
        chamadas["n"] += 1
        n = chamadas["n"]

        class _R:
            def json(self_inner):
                if n == 1:
                    return {"items": cheia}
                raise ValueError("não é JSON")

        return _R()

    monkeypatch.setattr(djen, "fetch", _fetch)
    monkeypatch.setattr(djen, "PAUSA_ENTRE_PAGINAS", 0)

    itens = await djen._coletar_oab("123456", "MG", "2026-09-01", "2026-09-04")
    assert len(itens) == djen.ITENS_POR_PAGINA
