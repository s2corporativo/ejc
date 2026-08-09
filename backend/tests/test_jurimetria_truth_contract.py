from __future__ import annotations

import pytest

from app.routers import jurimetria, jurimetria_extra


def test_taxa_decidida_exclui_acordo_e_pendente_do_denominador():
    assert jurimetria._taxa_decidida(3, 2) == 0.6
    assert jurimetria._taxa_decidida(0, 0) is None


@pytest.mark.asyncio
async def test_analise_prospectiva_nao_conta_acordo_como_vitoria(monkeypatch):
    async def _fake_por_resultado(db, tribunal=None):
        return 12, [
            {"resultado_raw": "exito_total", "total": 2},
            {"resultado_raw": "exito_parcial", "total": 1},
            {"resultado_raw": "improcedente", "total": 2},
            {"resultado_raw": "acordo", "total": 7},
        ]

    monkeypatch.setattr(jurimetria_extra, "_por_resultado", _fake_por_resultado)
    r = await jurimetria_extra.analise_prospectiva(
        classe="1116",
        tribunal="TJMG",
        dias_estimados=365,
        db=object(),
        cu=object(),
    )

    assert r["fonte"] == "base interna"
    assert r["classe_filtrada"] is False
    assert r["amostra"] == 5
    assert r["favoraveis"] == 3
    assert r["desfavoraveis"] == 2
    assert r["acordos"] == 7
    assert r["taxa_historica_favoravel"] == 60.0
    assert r["probabilidade_provimento"] == 60.0  # alias legado
    assert r["nao_e_previsao_judicial"] is True
    assert "não entrou" in r["aviso"]


@pytest.mark.asyncio
async def test_analise_prospectiva_inclui_aliases_exito_e_derrota(monkeypatch):
    async def _fake_por_resultado(db, tribunal=None):
        return 10, [
            {"resultado_raw": "exito", "total": 2},
            {"resultado_raw": "exito_total", "total": 1},
            {"resultado_raw": "exito_parcial", "total": 1},
            {"resultado_raw": "derrota", "total": 1},
            {"resultado_raw": "improcedente", "total": 1},
            {"resultado_raw": "acordo", "total": 4},
        ]

    monkeypatch.setattr(jurimetria_extra, "_por_resultado", _fake_por_resultado)
    r = await jurimetria_extra.analise_prospectiva(
        classe="",
        tribunal="TJMG",
        dias_estimados=0,
        db=object(),
        cu=object(),
    )

    assert r["favoraveis"] == 4
    assert r["desfavoraveis"] == 2
    assert r["amostra_decidida"] == 6
    assert r["acordos"] == 4
    assert r["taxa_historica_favoravel"] == 66.7


@pytest.mark.asyncio
async def test_analise_prospectiva_omite_taxa_com_amostra_decidida_baixa(monkeypatch):
    async def _fake_por_resultado(db, tribunal=None):
        return 20, [
            {"resultado_raw": "exito_total", "total": 2},
            {"resultado_raw": "improcedente", "total": 1},
            {"resultado_raw": "acordo", "total": 17},
        ]

    monkeypatch.setattr(jurimetria_extra, "_por_resultado", _fake_por_resultado)
    r = await jurimetria_extra.analise_prospectiva(
        classe="",
        tribunal="TJMG",
        dias_estimados=0,
        db=object(),
        cu=object(),
    )

    assert r["total_encerrados"] == 20
    assert r["amostra_decidida"] == 3
    assert r["acordos"] == 17
    assert r["taxa_historica_favoravel"] is None
    assert r["probabilidade_provimento"] is None
    assert r["confianca"] == "insuficiente"


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class _MappingsResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class _StatsDB:
    def __init__(self):
        self.calls = 0

    async def execute(self, _stmt):
        self.calls += 1
        if self.calls == 1:
            return _ScalarResult(123)
        return _MappingsResult(
            [
                {"tribunal": "TJMG", "total": 12},
                {"tribunal": "STJ", "total": 3},
            ]
        )


@pytest.mark.asyncio
async def test_stats_internos_retorna_total_real_sem_derivar_do_top_15():
    r = await jurimetria_extra.stats_internos(db=_StatsDB(), cu=object())

    assert r["total_com_tribunal"] == 123
    assert sum(item["total"] for item in r["por_tribunal"]) == 15
    assert r["fonte"] == "base interna"


def test_rotas_internas_e_aliases_legados_coexistem():
    from app.main import app

    paths = {route.path: route for route in app.routes}
    for path in (
        "/api/jurimetria/interno/stats",
        "/api/jurimetria/interno/benchmarks",
        "/api/jurimetria/interno/analise-prospectiva",
        "/api/jurimetria/ext/stats",
        "/api/jurimetria/ext/benchmarks",
        "/api/jurimetria/ext/predicao/provimento",
        "/api/jurimetria/analise-prospectiva",
        "/api/jurimetria/predicao-exito",
    ):
        assert path in paths

    # Aliases antigos aparecem como deprecated no OpenAPI, sem quebrar clientes.
    assert paths["/api/jurimetria/ext/stats"].deprecated is True
    assert paths["/api/jurimetria/ext/benchmarks"].deprecated is True
    assert paths["/api/jurimetria/ext/predicao/provimento"].deprecated is True
    assert paths["/api/jurimetria/predicao-exito"].deprecated is True
