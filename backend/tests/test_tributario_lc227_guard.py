"""Regressões dos gates jurídicos tributários do Issue #1553.

O PAF federal possui correção temporal própria no PR #1554, mas permanece
não homologado até fechamento da revisão jurídica. A simulação geral da Reforma
Tributária também fica fora da cadeia de demonstrativo enquanto usar premissas
genéricas de alíquota/atividade sem proveniência completa de 2026.
"""
from app.services.homologacao_ferramentas import (
    FERRAMENTAS_NAO_HOMOLOGADAS,
    motivo_nao_homologada,
    selo_homologacao,
)

ROTA_PAF = "/tributario/ferramentas/auto-infracao-prazos"
ROTA_REFORMA = "/tributario/ferramentas/reforma-tributaria"


def test_prazo_auto_infracao_tributario_permanece_nao_homologado() -> None:
    assert ROTA_PAF in FERRAMENTAS_NAO_HOMOLOGADAS
    motivo = motivo_nao_homologada(ROTA_PAF)
    assert motivo is not None
    assert "LC 227/2026" in motivo


def test_reforma_tributaria_permanece_nao_homologada_ate_versionamento_2026() -> None:
    assert ROTA_REFORMA in FERRAMENTAS_NAO_HOMOLOGADAS
    motivo = motivo_nao_homologada(ROTA_REFORMA)
    assert motivo is not None
    assert "LC 227/2026" in motivo
    assert "receita bruta" in motivo


def test_normalizacao_nao_contorna_gates_tributarios() -> None:
    for rota in (ROTA_PAF, ROTA_REFORMA):
        for caminho in (
            rota,
            f"/api{rota}",
            f"/api/v1{rota}",
            f"{rota}/",
            f"{rota}?teste=1",
        ):
            assert motivo_nao_homologada(caminho) is not None, caminho


def test_selo_impede_promocao_silenciosa_do_resultado() -> None:
    paf = selo_homologacao(ROTA_PAF, {"prazo_impugnacao": "20 dias úteis"})
    reforma = selo_homologacao(
        ROTA_REFORMA,
        {"estimativa_informativa_iva_pleno": {"aliquota_referencia_pct": 26.5}},
    )

    for resposta in (paf, reforma):
        assert resposta["homologada"] is False
        assert "não homologado" in resposta["aviso_homologacao"]
