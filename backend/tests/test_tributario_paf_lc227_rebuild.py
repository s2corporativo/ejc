"""Regressões da regra federal do PAF reconstruída sobre a main atual."""
from datetime import date

import pytest
from fastapi import HTTPException

from app.routers import ramos
from app.routers.ramos_tributario_paf import ROTA_AUTO_INFRACAO
from app.services.homologacao_ferramentas import motivo_nao_homologada
from app.services.tributario_paf import (
    VERSAO_REGRA_PAF,
    calcular_prazo_impugnacao_paf,
    suspenso_paf_federal,
)


def test_suspensao_2026_nao_retroage_antes_da_vigencia() -> None:
    assert suspenso_paf_federal(date(2026, 1, 13)) is False
    assert suspenso_paf_federal(date(2026, 1, 14)) is True
    assert suspenso_paf_federal(date(2026, 1, 20)) is True
    assert suspenso_paf_federal(date(2026, 1, 21)) is False


def test_suspensao_integral_a_partir_do_fim_de_2026() -> None:
    assert suspenso_paf_federal(date(2026, 12, 20)) is True
    assert suspenso_paf_federal(date(2027, 1, 20)) is True
    assert suspenso_paf_federal(date(2027, 1, 21)) is False


def test_ciencia_anterior_lc227_preserva_regime_anterior_com_suspensao_incidente() -> None:
    out = calcular_prazo_impugnacao_paf(date(2026, 1, 10))
    assert out["criterio"] == "regime_anterior_30_corridos"
    assert set(out["componentes"]) == {"30_dias_corridos"}
    assert out["vencimento"] > date(2026, 2, 9)  # 30 corridos simples, sem a suspensão


def test_transicao_ate_31_marco_escolhe_vencimento_posterior() -> None:
    out = calcular_prazo_impugnacao_paf(date(2026, 3, 31))
    assert out["criterio"] == "transicao_adi_rfb_2_2026_maior_vencimento"
    assert out["vencimento"] == max(out["componentes"].values())


def test_apos_transicao_aplica_20_dias_uteis() -> None:
    out = calcular_prazo_impugnacao_paf(date(2026, 4, 1))
    assert out["criterio"] == "lc227_20_uteis"
    assert out["prazo"] == "20 dias úteis"


def test_paf_permanece_no_gate_de_homologacao() -> None:
    motivo = motivo_nao_homologada(ROTA_AUTO_INFRACAO)
    assert motivo is not None
    assert "não promover" in motivo


def test_agregador_monta_uma_unica_rota_paf_canonica() -> None:
    rotas = [
        rota
        for rota in ramos.router.routes
        if getattr(rota, "path", None) == ROTA_AUTO_INFRACAO
        and "GET" in getattr(rota, "methods", set())
    ]
    assert len(rotas) == 1
    assert rotas[0].endpoint.__module__.endswith("ramos_tributario_paf")
    assert ROTA_AUTO_INFRACAO in ramos.CAMINHOS_FERRAMENTAS_VALIDOS


@pytest.mark.asyncio
async def test_endpoint_federal_retorna_minuta_nao_homologada() -> None:
    out = await ramos.trib_auto_infracao_prazos(
        data_ciencia=date(2026, 4, 1),
        valor_multa=10_000.0,
        esfera="federal",
        cu=None,
    )
    assert out["prazo_impugnacao"] == "20 dias úteis"
    assert out["versao_regra_especifica"] == VERSAO_REGRA_PAF
    assert out["homologada"] is False
    assert out["fontes"]


@pytest.mark.asyncio
@pytest.mark.parametrize("esfera", ["estadual", "municipal"])
async def test_endpoint_nao_inventa_prazo_de_outro_ente(esfera: str) -> None:
    with pytest.raises(HTTPException) as exc:
        await ramos.trib_auto_infracao_prazos(
            data_ciencia=date(2026, 9, 1),
            valor_multa=1_000.0,
            esfera=esfera,
            cu=None,
        )
    assert exc.value.status_code == 422
    assert "Não é seguro reutilizar o prazo federal" in str(exc.value.detail)
