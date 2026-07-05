"""Liquidação de sentença trabalhista — calculadora determinística e stateless.

Cobertura:
  • separação base salarial × indenizatória; FGTS 8% e multa 40% conferíveis;
  • honorários 10% sobre o principal CORRIGIDO;
  • Selic real do BCB MOCKADA (sem rede) — fator aplicado ao principal;
  • sem IPCA-E informado → alerta presente (nunca estima o índice);
  • IPCA-E informado → aplicado antes da Selic;
  • INSS/IRRF "a apurar" (não chuta alíquota);
  • schema de resposta (LiquidacaoOut) valida; guarda de payload gigante no PDF.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.services import bcb_service
from app.services.calc import liquidacao_trabalhista as liq
from app.routers import trabalhista_liquidacao as tl


_AJUIZ = date(2023, 1, 10)
_CALC = date(2024, 1, 10)
_HOJE = date(2024, 6, 1)

_VERBAS = [
    {"rubrica": "Horas extras", "valor": Decimal("8000"), "natureza": "salarial"},
    {"rubrica": "Indenização art. 477", "valor": Decimal("2000"),
     "natureza": "indenizatoria"},
]


def _mock_selic(monkeypatch, fator=1.10, meses=12, fonte="bcb"):
    """Mocka bcb_service.atualizar_valor (sem rede) — mesmo padrão do
    test_cet_abusividade que mocka o Olinda do BCB."""
    chamadas = []

    async def fake(valor, data_inicial, data_final, indice="ipca",
                   juros_mora_pct_mes=0.0):
        chamadas.append({"valor": valor, "indice": indice,
                         "ini": data_inicial, "fim": data_final})
        return {"fator_correcao": fator, "valor_corrigido": valor * fator,
                "meses_aplicados": meses, "fonte": fonte, "memoria_calculo": []}

    monkeypatch.setattr(bcb_service, "atualizar_valor", fake)
    return chamadas


# ══════════════════════════════════════════════════════════════════════════
# Caso conferível à mão
# ══════════════════════════════════════════════════════════════════════════
async def test_separacao_base_fgts_multa(monkeypatch):
    _mock_selic(monkeypatch, fator=1.0)  # sem correção → conferir FGTS/multa
    r = await liq.calcular_liquidacao(
        verbas=_VERBAS, data_ajuizamento=_AJUIZ, data_calculo=_CALC,
        percentual_honorarios=Decimal("10"), hoje=_HOJE)

    assert r["principal_bruto"] == 10_000.0
    assert r["base_salarial"] == 8_000.0
    assert r["base_indenizatoria"] == 2_000.0
    # FGTS 8% de 8.000 = 640; multa 40% de 640 = 256 (base salarial, nominal)
    assert r["fgts"]["valor"] == 640.0
    assert r["fgts"]["base"] == 8_000.0
    assert r["multa_fgts"]["valor"] == 256.0
    assert any("8.036" in b for b in r["base_legal"])
    assert any("462" in b for b in r["base_legal"])


async def test_selic_aplicada_e_honorarios_sobre_corrigido(monkeypatch):
    chamadas = _mock_selic(monkeypatch, fator=1.10, meses=12)
    r = await liq.calcular_liquidacao(
        verbas=_VERBAS, data_ajuizamento=_AJUIZ, data_calculo=_CALC,
        percentual_honorarios=Decimal("10"), hoje=_HOJE)

    # fator Selic aplicado ao principal: 10.000 × 1,10 = 11.000
    assert r["correcao"]["fator_selic"] == 1.10
    assert r["correcao"]["principal_corrigido"] == 11_000.0
    assert r["correcao"]["meses_selic"] == 12
    # honorários 10% sobre o CORRIGIDO: 10% de 11.000 = 1.100
    assert r["honorarios"]["valor"] == 1_100.0
    assert r["honorarios"]["base"] == 11_000.0
    assert any("791-A" in b for b in r["base_legal"])
    # a consulta usou a janela ajuizamento→cálculo e a série Selic
    assert chamadas and chamadas[0]["indice"] == "selic"
    assert chamadas[0]["ini"] == _AJUIZ and chamadas[0]["fim"] == _CALC
    # subtotal = corrigido + fgts + multa = 11.000 + 640 + 256 = 11.896
    assert r["subtotal_credito_trabalhista"] == 11_896.0


async def test_sem_ipcae_gera_alerta(monkeypatch):
    _mock_selic(monkeypatch, fator=1.10)
    r = await liq.calcular_liquidacao(
        verbas=_VERBAS, data_ajuizamento=_AJUIZ, data_calculo=_CALC,
        percentual_honorarios=Decimal("10"), hoje=_HOJE)
    assert r["correcao"]["fator_ipcae_pre_ajuizamento"] is None
    assert any("IPCA-E" in a for a in r["alertas"])
    # sem IPCA-E o principal pré-Selic é o bruto
    assert r["correcao"]["principal_pos_ipcae"] == 10_000.0


async def test_ipcae_informado_aplicado_antes_da_selic(monkeypatch):
    _mock_selic(monkeypatch, fator=1.10)
    r = await liq.calcular_liquidacao(
        verbas=_VERBAS, data_ajuizamento=_AJUIZ, data_calculo=_CALC,
        percentual_honorarios=Decimal("10"),
        fator_ipcae_pre_ajuizamento=Decimal("1.05"), hoje=_HOJE)
    # 10.000 × 1,05 (IPCA-E) = 10.500 → × 1,10 (Selic) = 11.550
    assert r["correcao"]["principal_pos_ipcae"] == 10_500.0
    assert r["correcao"]["principal_corrigido"] == 11_550.0
    assert not any("IPCA-E pré-ajuizamento NÃO aplicado" in a for a in r["alertas"])


async def test_inss_irrf_a_apurar(monkeypatch):
    _mock_selic(monkeypatch, fator=1.0)
    r = await liq.calcular_liquidacao(
        verbas=_VERBAS, data_ajuizamento=_AJUIZ, data_calculo=_CALC,
        percentual_honorarios=Decimal("10"), hoje=_HOJE)
    assert r["inss"]["valor"] is None and r["inss"]["status"] == "a_apurar"
    assert r["irrf"]["valor"] is None and r["irrf"]["status"] == "a_apurar"
    assert any("a apurar" in a.lower() for a in r["alertas"])


async def test_bcb_fora_fail_soft_nao_inventa(monkeypatch):
    async def caiu(*a, **k):
        raise RuntimeError("timeout BCB")

    monkeypatch.setattr(bcb_service, "atualizar_valor", caiu)
    r = await liq.calcular_liquidacao(
        verbas=_VERBAS, data_ajuizamento=_AJUIZ, data_calculo=_CALC,
        percentual_honorarios=Decimal("10"), hoje=_HOJE)
    # fail-soft: fator 1 (não estima) + alerta
    assert r["correcao"]["fator_selic"] == 1.0
    assert r["correcao"]["principal_corrigido"] == 10_000.0
    assert any("Selic" in a and "indisponível" in a for a in r["alertas"])


async def test_validacoes(monkeypatch):
    _mock_selic(monkeypatch)
    with pytest.raises(ValueError):   # verbas vazias
        await liq.calcular_liquidacao(
            verbas=[], data_ajuizamento=_AJUIZ, data_calculo=_CALC,
            percentual_honorarios=Decimal("10"), hoje=_HOJE)
    with pytest.raises(ValueError):   # data_calculo <= ajuizamento
        await liq.calcular_liquidacao(
            verbas=_VERBAS, data_ajuizamento=_CALC, data_calculo=_AJUIZ,
            percentual_honorarios=Decimal("10"), hoje=_HOJE)
    with pytest.raises(ValueError):   # data_calculo futura
        await liq.calcular_liquidacao(
            verbas=_VERBAS, data_ajuizamento=_AJUIZ, data_calculo=date(2099, 1, 1),
            percentual_honorarios=Decimal("10"), hoje=_HOJE)
    with pytest.raises(ValueError):   # natureza inválida
        await liq.calcular_liquidacao(
            verbas=[{"rubrica": "x", "valor": 100, "natureza": "outra"}],
            data_ajuizamento=_AJUIZ, data_calculo=_CALC,
            percentual_honorarios=Decimal("10"), hoje=_HOJE)


# ══════════════════════════════════════════════════════════════════════════
# Endpoint / schema
# ══════════════════════════════════════════════════════════════════════════
async def test_endpoint_calcular_shape(monkeypatch):
    _mock_selic(monkeypatch, fator=1.10)
    req = tl.LiquidacaoIn(
        verbas=[{"rubrica": "Horas extras", "valor": 8000, "natureza": "salarial"},
                {"rubrica": "Multa 477", "valor": 2000,
                 "natureza": "indenizatoria"}],
        data_ajuizamento=_AJUIZ, data_calculo=_CALC, percentual_honorarios=10)
    r = await tl.calcular(req, cu=None)
    # response_model valida a saída (LiquidacaoOut)
    out = tl.LiquidacaoOut.model_validate(r)
    assert out.principal_bruto == 10_000.0
    assert out.correcao.principal_corrigido == 11_000.0
    assert out.honorarios.valor == 1_100.0
    for k in ("fgts", "multa_fgts", "correcao", "honorarios", "inss", "irrf",
              "memoria_calculo", "alertas", "base_legal", "aviso_hitl"):
        assert hasattr(out, k)


def test_pdf_guarda_payload_gigante():
    # rubrica acima de _TXT (2000) deve estourar a validação do schema do PDF
    with pytest.raises(Exception):
        tl.VerbaOut(rubrica="x" * 3000, valor=1.0, natureza="salarial")
    # lista de verbas acima do teto (MAX_VERBAS) rejeitada na entrada
    with pytest.raises(Exception):
        tl.LiquidacaoIn(
            verbas=[{"rubrica": "v", "valor": 1, "natureza": "salarial"}]
            * (tl.MAX_VERBAS + 1),
            data_ajuizamento=_AJUIZ, data_calculo=_CALC, percentual_honorarios=10)
