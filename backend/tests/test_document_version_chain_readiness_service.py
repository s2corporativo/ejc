from __future__ import annotations

from dataclasses import asdict

from app.services.document_version_chain_readiness_service import (
    AuditoriaLinearidadeVersoes,
)


def _auditoria(**overrides) -> AuditoriaLinearidadeVersoes:
    dados = {
        "predecessores_com_multiplos_sucessores": 0,
        "arestas_versao_invalidas": 0,
        "grupos_ponta_historica_deletada": 0,
    }
    dados.update(overrides)
    return AuditoriaLinearidadeVersoes(**dados)


def test_cadeia_linear_quando_todas_as_anomalias_sao_zero():
    assert _auditoria().cadeia_linear is True


def test_qualquer_anomalia_bloqueia_linearidade():
    for campo in (
        "predecessores_com_multiplos_sucessores",
        "arestas_versao_invalidas",
        "grupos_ponta_historica_deletada",
    ):
        assert _auditoria(**{campo: 1}).cadeia_linear is False


def test_resultado_contem_somente_contagens():
    payload = asdict(_auditoria())
    assert set(payload) == {
        "predecessores_com_multiplos_sucessores",
        "arestas_versao_invalidas",
        "grupos_ponta_historica_deletada",
    }
    assert all(isinstance(valor, int) for valor in payload.values())
