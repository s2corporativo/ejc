"""Regressões dos gates jurídicos tributários do Issue #1553.

PAF, prescrição/decadência, parcelamento genérico e simulação geral da Reforma
permanecem fora da cadeia de demonstrativo até revisão jurídica completa. O
objetivo destes testes é impedir promoção silenciosa de cálculo não homologado.
"""
from app.services.homologacao_ferramentas import (
    FERRAMENTAS_NAO_HOMOLOGADAS,
    motivo_nao_homologada,
    selo_homologacao,
)

ROTA_PAF = "/tributario/ferramentas/auto-infracao-prazos"
ROTA_PRESCRICAO = "/tributario/ferramentas/prescricao-decadencia"
ROTA_PARCELAMENTO = "/tributario/ferramentas/parcelamento"
ROTA_REFORMA = "/tributario/ferramentas/reforma-tributaria"


def test_prazo_auto_infracao_tributario_permanece_nao_homologado() -> None:
    assert ROTA_PAF in FERRAMENTAS_NAO_HOMOLOGADAS
    motivo = motivo_nao_homologada(ROTA_PAF)
    assert motivo is not None
    assert "LC 227/2026" in motivo


def test_prescricao_decadencia_desomologada_apos_lc236() -> None:
    assert ROTA_PRESCRICAO in FERRAMENTAS_NAO_HOMOLOGADAS
    motivo = motivo_nao_homologada(ROTA_PRESCRICAO)
    assert motivo is not None
    assert "LC 236/2026" in motivo
    assert "150/151/168/174" in motivo


def test_parcelamento_generico_nao_vira_demonstrativo_com_parametros_congelados() -> None:
    assert ROTA_PARCELAMENTO in FERRAMENTAS_NAO_HOMOLOGADAS
    motivo = motivo_nao_homologada(ROTA_PARCELAMENTO)
    assert motivo is not None
    assert "PERT/REFIS" in motivo
    assert "2026" in motivo
    assert "edital" in motivo


def test_reforma_tributaria_permanece_nao_homologada_ate_versionamento_2026() -> None:
    assert ROTA_REFORMA in FERRAMENTAS_NAO_HOMOLOGADAS
    motivo = motivo_nao_homologada(ROTA_REFORMA)
    assert motivo is not None
    assert "LC 227/2026" in motivo
    assert "LC 236/2026" in motivo
    assert "receita bruta" in motivo


def test_normalizacao_nao_contorna_gates_tributarios() -> None:
    for rota in (ROTA_PAF, ROTA_PRESCRICAO, ROTA_PARCELAMENTO, ROTA_REFORMA):
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
            ROTA_REFORMA,
            {"estimativa_informativa_iva_pleno": {"aliquota_referencia_pct": 26.5}},
        ),
    ]

    for resposta in respostas:
        assert resposta["homologada"] is False
        assert "não homologado" in resposta["aviso_homologacao"]
