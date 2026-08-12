from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.dpt360.radar_service import (
    RADAR_CLASSIFICATION_LIMIT,
    RADAR_ITEM_LIMIT,
    build_today_radar,
    classify_area,
    impact_level,
)


def test_classificacao_do_radar_por_termos_objetivos():
    assert classify_area("IBAMA", "Licenciamento ambiental", None) == "ambiental"
    assert classify_area("PGFN", "Transação tributária", None) == "tributario"
    assert classify_area("ANPD", "Dados pessoais", None) == "lgpd_ia"
    assert classify_area(None, "Tema sem vocabulário cadastrado", None) == "geral"


def test_impacto_so_existe_com_sinal_objetivo_da_empresa():
    assert impact_level("ambiental", {"ambiental"}) == "alta"
    assert impact_level("administrativo", {"licitacoes"}) == "alta"
    assert impact_level("tributario", {"trabalhista"}) is None
    assert impact_level("geral", {"empresarial"}) is None


def _scalar_result(value):
    result = MagicMock()
    result.scalar.return_value = value
    return result


def _scalars_result(rows):
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


def _rows_result(rows):
    result = MagicMock()
    result.all.return_value = rows
    return result


def _alert(index: int, *, titulo: str = "Publicação geral"):
    return SimpleNamespace(
        id=f"a{index}",
        keyword_match=None,
        titulo=titulo,
        resumo=None,
        fonte="dou",
        link=None,
        data_publicacao=None,
    )


@pytest.mark.anyio
async def test_radar_mantem_total_exato_e_sinaliza_classificacao_parcial():
    user = SimpleNamespace(id="u1", role="admin")
    alerts = [_alert(index) for index in range(RADAR_CLASSIFICATION_LIMIT)]
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                _scalar_result(RADAR_CLASSIFICATION_LIMIT + 50),
                _scalars_result(alerts),
                _rows_result([]),
            ]
        )
    )

    result = await build_today_radar(db, user, hours=24)

    assert result["total_publicacoes"] == RADAR_CLASSIFICATION_LIMIT + 50
    assert result["publicacoes_classificadas"] == RADAR_CLASSIFICATION_LIMIT
    assert result["cobertura"] == "parcial"
    assert len(result["itens"]) == RADAR_ITEM_LIMIT


@pytest.mark.anyio
async def test_radar_completo_usa_indice_minimo_de_empresa_e_caso():
    user = SimpleNamespace(id="u1", role="admin")
    alerts = [_alert(1, titulo="IBAMA publica regra de licenciamento ambiental")]
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                _scalar_result(1),
                _scalars_result(alerts),
                _rows_result([("c1", "Empresa A", None, "ambiental")]),
            ]
        )
    )

    result = await build_today_radar(db, user, hours=24)

    assert result["total_publicacoes"] == 1
    assert result["publicacoes_classificadas"] == 1
    assert result["cobertura"] == "completa"
    assert result["por_area"] == {"ambiental": 1}
    assert result["empresas_potencialmente_impactadas"] == 1
    assert result["itens"][0]["impactos"][0]["client_id"] == "c1"
    assert result["itens"][0]["impactos"][0]["empresa"] == "Empresa A"
