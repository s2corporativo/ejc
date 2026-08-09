"""Análise prospectiva interna (jurimetria_extra) — honestidade estatística.

Auditoria IA 2026-08-08:
  - n decidido < MIN_AMOSTRA (=5) => taxa None + aviso (nunca inventa número);
  - acordos ficam fora do denominador de desfecho judicial;
  - a base interna (tabela cases) não tem classe processual (TPU): a `classe`
    digitada nunca entra no cálculo (classe_filtrada=False, apenas ecoada);
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


async def test_amostra_decidida_insuficiente_devolve_none_e_aviso(monkeypatch):
    # n decidido=1 < MIN_AMOSTRA: não pode virar percentual.
    por = [
        {
            "resultado": "Êxito total",
            "resultado_raw": "exito_total",
            "total": 1,
            "pct": 100.0,
        }
    ]
    monkeypatch.setattr(
        jurimetria_extra, "_por_resultado", _fake_por_resultado(por, 1)
    )
    out = await jurimetria_extra.analise_prospectiva(
        classe="Procedimento Comum",
        tribunal="TJMG",
        dias_estimados=0,
        db=_DummyDB(),
        cu=_DummyUser(),
    )
    assert out["probabilidade_provimento"] is None
    assert out["taxa_historica_favoravel"] is None
    assert out["amostra"] == 1
    assert out["metodo"] == "amostra decidida insuficiente"
    assert out["confianca"] == "insuficiente"
    assert str(MIN_AMOSTRA) in out["aviso"]
    assert out["fonte"] == "base interna"


async def test_amostra_suficiente_exclui_acordos_do_denominador(monkeypatch):
    # Encerrados=8; decididos=6: 3 favoráveis / (3 favoráveis + 3 improcedentes)
    # = 50%. Os 2 acordos permanecem visíveis, mas fora da taxa judicial.
    por = [
        {
            "resultado": "Êxito total",
            "resultado_raw": "exito_total",
            "total": 3,
            "pct": 37.5,
        },
        {
            "resultado": "Acordo",
            "resultado_raw": "acordo",
            "total": 2,
            "pct": 25.0,
        },
        {
            "resultado": "Improcedente",
            "resultado_raw": "improcedente",
            "total": 3,
            "pct": 37.5,
        },
    ]
    monkeypatch.setattr(
        jurimetria_extra, "_por_resultado", _fake_por_resultado(por, 8)
    )
    out = await jurimetria_extra.analise_prospectiva(
        classe="Execução Fiscal",
        tribunal="TJMG",
        dias_estimados=120,
        db=_DummyDB(),
        cu=_DummyUser(),
    )
    assert out["taxa_historica_favoravel"] == 50.0
    assert out["probabilidade_provimento"] == 50.0
    assert out["amostra"] == 6
    assert out["acordos"] == 2
    assert out["classe_filtrada"] is False
    assert out["classe"] == "Execução Fiscal"
    assert "classe" in out["aviso"].lower()
    assert "histórico interno" in out["metodo"].lower()
    assert out["fonte"] == "base interna"


async def test_limiar_exato_min_amostra_decidida_ja_calcula(monkeypatch):
    # Fronteira: n decidido == MIN_AMOSTRA já calcula (piso é >=, não >).
    por = [
        {
            "resultado": "Êxito total",
            "resultado_raw": "exito_total",
            "total": MIN_AMOSTRA,
            "pct": 100.0,
        }
    ]
    monkeypatch.setattr(
        jurimetria_extra,
        "_por_resultado",
        _fake_por_resultado(por, MIN_AMOSTRA),
    )
    out = await jurimetria_extra.analise_prospectiva(
        classe="",
        tribunal="",
        dias_estimados=0,
        db=_DummyDB(),
        cu=_DummyUser(),
    )
    assert out["taxa_historica_favoravel"] == 100.0
    assert out["probabilidade_provimento"] == 100.0
    assert out["amostra"] == MIN_AMOSTRA
    assert out["classe_filtrada"] is False
    assert out["fonte"] == "base interna"
