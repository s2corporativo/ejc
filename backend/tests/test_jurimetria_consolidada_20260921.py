from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.jurimetria import (
    _bucket,
    _resumo,
    classificar_resultado,
    intervalo_wilson,
)
from app.services.jurimetria_tribunais import agregacao
from app.services.tese_vinculo_service import normalizar_resultado_tese


def test_taxonomia_case_reconhece_write_path_e_aliases_historicos() -> None:
    assert _bucket("exito") == "exito_total"
    assert _bucket("exito_total") == "exito_total"
    assert _bucket("exito_parcial") == "exito_parcial"
    assert _bucket("derrota") == "improcedente"
    assert _bucket("improcedente") == "improcedente"
    assert _bucket("acordo") == "acordo"
    assert _bucket("desistencia") == "outro"
    assert _bucket("arquivado") == "outro"

    assert classificar_resultado("exito") == "favoravel"
    assert classificar_resultado("derrota") == "desfavoravel"
    assert classificar_resultado("acordo") == "acordo"
    assert classificar_resultado("desistencia") == "nao_decidido"


def test_taxa_judicial_exclui_acordo_e_sem_merito_do_denominador() -> None:
    resumo = _resumo(
        [
            _bucket("exito"),
            _bucket("derrota"),
            _bucket("acordo"),
            _bucket("desistencia"),
        ]
    )

    assert resumo["n"] == 4
    assert resumo["n_decididos"] == 2
    assert resumo["taxa_exito"] == 50.0
    assert resumo["taxa_improcedencia"] == 50.0
    assert resumo["distribuicao"]["acordo"] == 1
    assert resumo["n_nao_decididos"] == 1
    assert resumo["intervalo_confianca_95"]["metodo"] == "wilson"


def test_intervalo_wilson_evitar_falsa_precisao() -> None:
    ic = intervalo_wilson(6, 10)
    assert ic is not None
    assert ic["inferior"] == pytest.approx(31.3, abs=0.1)
    assert ic["superior"] == pytest.approx(83.2, abs=0.1)
    assert intervalo_wilson(0, 0) is None


def test_resultado_tese_novo_e_validado() -> None:
    assert normalizar_resultado_tese(None) == "pendente"
    assert normalizar_resultado_tese("procedente") == "procedente"
    with pytest.raises(ValueError):
        normalizar_resultado_tese("vitoria")


def test_jurimetria_externa_expoe_ic95() -> None:
    g = agregacao._grupo_vazio()
    g["n"] = 10
    g["n_com_desfecho"] = 10
    g[agregacao.tpu.PROCEDENCIA] = 6
    g[agregacao.tpu.IMPROCEDENCIA] = 4

    fechado = agregacao._fechar_grupo(g)
    assert fechado["taxa_procedencia"] == 0.6
    assert fechado["intervalo_confianca_95_procedencia"]["inferior"] == pytest.approx(
        31.3, abs=0.1
    )
    assert fechado["intervalo_confianca_95_procedencia"]["superior"] == pytest.approx(
        83.2, abs=0.1
    )


@pytest.mark.asyncio
async def test_por_magistrado_fica_fail_closed_sem_dado_confiavel() -> None:
    from app.routers.jurimetria import por_magistrado

    user = SimpleNamespace(role=SimpleNamespace(value="advogado"))
    with pytest.raises(HTTPException) as exc:
        await por_magistrado(area=None, limit=20, db=None, cu=user)

    assert exc.value.status_code == 409
    assert "desabilitada" in str(exc.value.detail).lower()
