"""Gate de homologação: calculadora não homologada não vira documento formal.

Auditoria 2026-07-26 — corta o caminho "regra errada → resultado plausível →
documento formal → uso externo". O cálculo continua livre; só a materialização
em Peças exige status `homologada`.
"""
from __future__ import annotations

from app.core.homologacao_ferramentas import (
    mapa_status,
    pode_gerar_documento,
    status_ferramenta,
)


def test_ferramenta_desconhecida_e_fail_closed():
    # Calculadora nova (ou payload sem identificação) nasce bloqueada.
    assert pode_gerar_documento("/ramo-novo/ferramentas/qualquer") is False
    assert pode_gerar_documento(None) is False
    assert pode_gerar_documento("") is False
    assert status_ferramenta(None).status == "em_revisao"


def test_ferramentas_corrigidas_ficam_em_revisao_ate_ato_humano():
    # Correção técnica não substitui homologação jurídica.
    for endpoint in (
        "/civel/ferramentas/prazos-contestacao",
        "/penal/ferramentas/prazos-processuais",
        "/trabalhista-esp/ferramentas/prazos",
        "/transito/ferramentas/prazos-recurso",
        "/previdenciario/ferramentas/carencia",
    ):
        assert status_ferramenta(endpoint).status == "em_revisao", endpoint
        assert pode_gerar_documento(endpoint) is False, endpoint


def test_pendencias_juridicas_conhecidas_ficam_bloqueadas():
    for endpoint in (
        "/civel/ferramentas/calculo-dano-moral",
        "/civel/ferramentas/alimentos-calcular",
    ):
        st = status_ferramenta(endpoint)
        assert st.status == "bloqueada", endpoint
        assert st.nota, "toda pendência precisa registrar o motivo"


def test_trailing_slash_nao_burla_o_gate():
    assert (
        status_ferramenta("/civel/ferramentas/calculo-dano-moral/").status
        == "bloqueada"
    )


def test_mapa_exposto_a_ui_tem_apenas_status_conhecidos():
    valores = set(mapa_status().values())
    assert valores <= {"homologada", "em_revisao", "bloqueada"}
    # Enquanto nada foi homologado, o mapa não pode liberar nada por engano.
    assert "homologada" not in valores
