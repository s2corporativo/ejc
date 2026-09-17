"""Regressões dos gates jurídicos tributários do Issue #1553.

PAF, prescrição/decadência, parcelamento, comparativo de regimes e Reforma
permanecem fora da cadeia de demonstrativo até revisão jurídica completa.
"""
from datetime import date

import pytest

from app.routers import ramos
from app.services.homologacao_ferramentas import (
    FERRAMENTAS_NAO_HOMOLOGADAS,
    motivo_nao_homologada,
    selo_homologacao,
)

ROTA_PAF = "/tributario/ferramentas/auto-infracao-prazos"
ROTA_PRESCRICAO = "/tributario/ferramentas/prescricao-decadencia"
ROTA_PARCELAMENTO = "/tributario/ferramentas/parcelamento"
ROTA_REGIME = "/tributario/ferramentas/regime-tributario"
ROTA_REFORMA = "/tributario/ferramentas/reforma-tributaria"


def _endpoint_get(caminho: str):
    rotas = [
        rota
        for rota in ramos.router.routes
        if getattr(rota, "path", None) == caminho
        and "GET" in getattr(rota, "methods", set())
    ]
    assert len(rotas) == 1, caminho
    return rotas[0].endpoint


def test_prazo_auto_infracao_tributario_permanece_nao_homologado() -> None:
    motivo = motivo_nao_homologada(ROTA_PAF)
    assert ROTA_PAF in FERRAMENTAS_NAO_HOMOLOGADAS
    assert motivo is not None and "LC 227/2026" in motivo


def test_prescricao_decadencia_desomologada_apos_lc236() -> None:
    motivo = motivo_nao_homologada(ROTA_PRESCRICAO)
    assert ROTA_PRESCRICAO in FERRAMENTAS_NAO_HOMOLOGADAS
    assert motivo is not None
    assert "LC 236/2026" in motivo
    assert "150/151/168/174" in motivo


def test_parcelamento_generico_nao_vira_demonstrativo_com_parametros_congelados() -> None:
    motivo = motivo_nao_homologada(ROTA_PARCELAMENTO)
    assert ROTA_PARCELAMENTO in FERRAMENTAS_NAO_HOMOLOGADAS
    assert motivo is not None
    assert "PERT/REFIS" in motivo
    assert "2026" in motivo
    assert "edital" in motivo


def test_comparativo_regimes_desomologado_apos_lc224() -> None:
    motivo = motivo_nao_homologada(ROTA_REGIME)
    assert ROTA_REGIME in FERRAMENTAS_NAO_HOMOLOGADAS
    assert motivo is not None
    assert "LC 224/2025" in motivo
    assert "IRPJ/CSLL" in motivo
    assert "período" in motivo


def test_reforma_tributaria_permanece_nao_homologada_ate_versionamento_2026() -> None:
    motivo = motivo_nao_homologada(ROTA_REFORMA)
    assert ROTA_REFORMA in FERRAMENTAS_NAO_HOMOLOGADAS
    assert motivo is not None
    assert "LC 227/2026" in motivo
    assert "LC 236/2026" in motivo
    assert "receita bruta" in motivo


def test_normalizacao_nao_contorna_gates_tributarios() -> None:
    rotas = (ROTA_PAF, ROTA_PRESCRICAO, ROTA_PARCELAMENTO, ROTA_REGIME, ROTA_REFORMA)
    for rota in rotas:
        for caminho in (
            rota,
            f"/api{rota}",
            f"/api/v1{rota}",
            f"{rota}/",
            f"{rota}?teste=1",
        ):
            assert motivo_nao_homologada(caminho) is not None, caminho


def test_selo_impede_promocao_silenciosa_do_resultado() -> None:
    respostas = [
        selo_homologacao(ROTA_PAF, {"prazo_impugnacao": "20 dias úteis"}),
        selo_homologacao(
            ROTA_PRESCRICAO,
            {"instituto": "PRESCRIÇÃO", "prazo": "5 anos"},
        ),
        selo_homologacao(
            ROTA_PARCELAMENTO,
            {"parcelas_simuladas": 120, "reducoes_potenciais": {"juros_pct": 65}},
        ),
        selo_homologacao(
            ROTA_REGIME,
            {"lucro_presumido": {"carga_anual_estimada": 1000}},
        ),
        selo_homologacao(
            ROTA_REFORMA,
            {"estimativa_informativa_iva_pleno": {"aliquota_referencia_pct": 26.5}},
        ),
    ]

    for resposta in respostas:
        assert resposta["homologada"] is False
        assert "não homologado" in resposta["aviso_homologacao"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("caminho", "kwargs"),
    [
        (
            ROTA_PRESCRICAO,
            {
                "data_fato_gerador": date(2024, 1, 15),
                "tipo": "homologacao",
                "cu": None,
            },
        ),
        (
            ROTA_PARCELAMENTO,
            {
                "valor_total_debito": 12_000.0,
                "parcelas": 12,
                "modalidade": "parcelamento_comum",
                "cu": None,
            },
        ),
        (
            ROTA_REGIME,
            {
                "receita_bruta_anual": 1_000_000.0,
                "lucro_estimado_pct": 20.0,
                "atividade": "servicos",
                "cu": None,
            },
        ),
        (
            ROTA_REFORMA,
            {
                "receita_bruta_anual": 1_000_000.0,
                "regime_atual": "lucro_presumido",
                "atividade": "servicos",
                "ano_analise": "2026",
                "cu": None,
            },
        ),
    ],
)
async def test_resposta_real_da_api_carrega_selo_de_nao_homologacao(
    caminho: str,
    kwargs: dict,
) -> None:
    endpoint = _endpoint_get(caminho)
    resposta = await endpoint(**kwargs)

    assert resposta["homologada"] is False
    assert "não homologado" in resposta["aviso_homologacao"]
