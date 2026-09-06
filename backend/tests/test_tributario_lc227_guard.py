"""Regressões do gate P0 tributário após a LC 227/2026.

A correção definitiva do cálculo vive no Issue #1553. Enquanto o handler legado
continuar retornando 30 dias corridos, ele precisa permanecer fora da cadeia de
homologação para não virar demonstrativo/peça profissional.
"""
from app.services.homologacao_ferramentas import (
    FERRAMENTAS_NAO_HOMOLOGADAS,
    motivo_nao_homologada,
    selo_homologacao,
)

ROTA = "/tributario/ferramentas/auto-infracao-prazos"


def test_prazo_auto_infracao_tributario_permanece_nao_homologado() -> None:
    assert ROTA in FERRAMENTAS_NAO_HOMOLOGADAS
    motivo = motivo_nao_homologada(ROTA)
    assert motivo is not None
    assert "LC 227/2026" in motivo


def test_normalizacao_nao_contorna_gate_tributario() -> None:
    for caminho in (
        ROTA,
        f"/api{ROTA}",
        f"/api/v1{ROTA}",
        f"{ROTA}/",
        f"{ROTA}?esfera=federal",
    ):
        assert motivo_nao_homologada(caminho) is not None, caminho


def test_selo_impede_promocao_silenciosa_do_resultado() -> None:
    resposta = selo_homologacao(ROTA, {"prazo_impugnacao": "30 dias corridos"})
    assert resposta["homologada"] is False
    assert "não homologado" in resposta["aviso_homologacao"]
