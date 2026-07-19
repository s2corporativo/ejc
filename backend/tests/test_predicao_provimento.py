"""Predicao de provimento (jurimetria_extra) — honestidade estatistica.

Auditoria IA 2026-07-18:
  - n < MIN_AMOSTRA (=5) => probabilidade None + aviso (nunca inventa numero);
  - a base interna (tabela cases) nao tem classe processual (TPU): a `classe`
    digitada nunca entra no calculo (classe_filtrada=False, apenas ecoada) e o
    percentual e a TAXA GLOBAL DO TRIBUNAL;
  - fonte permanece 'base interna' (nunca DataJud/externo).
"""
from app.routers import jurimetria_extra
from app.services.jurimetria import MIN_AMOSTRA


class _DummyDB:
    pass


class _DummyUser:
    id = "u-1"


def _fake_por_resultado(por_resultado, total):
    async def _fn(db, tribunal=None):
        return total, por_resultado
    return _fn


async def test_amostra_insuficiente_devolve_none_e_aviso(monkeypatch):
    # n=1 < MIN_AMOSTRA: NAO pode virar percentual (estatistica inventada).
    por = [{"resultado": "Êxito total", "resultado_raw": "exito_total",
            "total": 1, "pct": 100.0}]
    monkeypatch.setattr(jurimetria_extra, "_por_resultado", _fake_por_resultado(por, 1))
    out = await jurimetria_extra.predicao_provimento(
        classe="Procedimento Comum", tribunal="TJMG", dias_estimados=0,
        db=_DummyDB(), cu=_DummyUser())
    assert out["probabilidade_provimento"] is None
    assert out["amostra"] == 1
    assert out["metodo"] == "amostra insuficiente"
    assert out["confianca"] == "insuficiente"
    assert str(MIN_AMOSTRA) in out["aviso"]
    assert out["fonte"] == "base interna"


async def test_amostra_suficiente_calcula_taxa_global(monkeypatch):
    # n=8 >= MIN_AMOSTRA: (exito_total 3 + acordo 2) / 8 = 62.5%, taxa GLOBAL.
    por = [
        {"resultado": "Êxito total", "resultado_raw": "exito_total", "total": 3, "pct": 37.5},
        {"resultado": "Acordo", "resultado_raw": "acordo", "total": 2, "pct": 25.0},
        {"resultado": "Improcedente", "resultado_raw": "improcedente", "total": 3, "pct": 37.5},
    ]
    monkeypatch.setattr(jurimetria_extra, "_por_resultado", _fake_por_resultado(por, 8))
    out = await jurimetria_extra.predicao_provimento(
        classe="Execução Fiscal", tribunal="TJMG", dias_estimados=120,
        db=_DummyDB(), cu=_DummyUser())
    assert out["probabilidade_provimento"] == 62.5
    assert out["amostra"] == 8
    # classe NUNCA entra no calculo — so ecoada; resposta deixa isso explicito.
    assert out["classe_filtrada"] is False
    assert out["classe"] == "Execução Fiscal"
    assert "classe" in out["aviso"].lower()
    assert "global" in out["metodo"].lower()
    assert out["fonte"] == "base interna"


async def test_limiar_exato_min_amostra_ja_calcula(monkeypatch):
    # Fronteira: n == MIN_AMOSTRA ja calcula (piso e '>=', nao '>').
    por = [{"resultado": "Êxito total", "resultado_raw": "exito_total",
            "total": MIN_AMOSTRA, "pct": 100.0}]
    monkeypatch.setattr(jurimetria_extra, "_por_resultado",
                        _fake_por_resultado(por, MIN_AMOSTRA))
    out = await jurimetria_extra.predicao_provimento(
        classe="", tribunal="", dias_estimados=0, db=_DummyDB(), cu=_DummyUser())
    assert out["probabilidade_provimento"] == 100.0
    assert out["amostra"] == MIN_AMOSTRA
    assert out["classe_filtrada"] is False
    assert out["fonte"] == "base interna"
