"""Vertical Previdenciário — regras de transição da EC 103/2019 + coeficiente RMI.

Cobertura:
  • elegibilidade por pontos (caso conferível à mão) e caso inelegível com
    `o_que_falta` preenchido;
  • coeficiente do art. 26 (60% + 2%/ano acima de 20 H / 15 F) e RMI só quando a
    média é informada (honestidade: sem CNIS → null com observação);
  • melhor_regra escolhe a de maior coeficiente entre as elegíveis;
  • pedágio 50% com coeficiente indeterminado (fator previdenciário) → null;
  • schema de resposta valida (SimulacaoPrevidOut);
  • guarda de payload no PDF (limites de Field).
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.calc.previdenciario_beneficio import (
    simular_aposentadoria, coeficiente_ec103,
)


def _sim(sexo, idade, tempo, media, ano):
    return simular_aposentadoria(
        sexo=sexo, idade=Decimal(str(idade)),
        tempo_contribuicao=Decimal(str(tempo)),
        media_salarios=(Decimal(str(media)) if media is not None else None),
        ano=ano,
    )


def _regra(res, rid):
    return next(r for r in res["regras"] if r["regra_id"] == rid)


# ── Coeficiente (art. 26) ─────────────────────────────────────────────────────

def test_coeficiente_homem_25_anos_70pct():
    # H: 60% + 2% × (25-20) = 70%
    assert coeficiente_ec103(True, Decimal("25")) == Decimal("0.7000")


def test_coeficiente_mulher_no_piso_60pct():
    # F com exatamente 15 anos → piso de 60%
    assert coeficiente_ec103(False, Decimal("15")) == Decimal("0.6000")


def test_coeficiente_conta_apenas_anos_completos():
    # 25,9 anos (H) conta 5 anos excedentes completos → 70%
    assert coeficiente_ec103(True, Decimal("25.9")) == Decimal("0.7000")


# ── Elegibilidade por pontos (art. 15) ────────────────────────────────────────

def test_pontos_elegivel_mulher_2022():
    # F, 57 anos, 32 de contribuição, 2022 → pontuação F exigida = 89.
    # 57+32 = 89 ≥ 89 e tempo 32 ≥ 30 → elegível.
    res = _sim("F", 57, 32, None, 2022)
    r = _regra(res, "pontos")
    assert r["elegivel"] is True
    assert r["o_que_falta"] == []
    assert "pontos" in res["regras_elegiveis"]


def test_pontos_inelegivel_com_o_que_falta():
    # F, 50 anos, 25 de contribuição, 2022 → 75 pts < 89 e tempo 25 < 30.
    res = _sim("F", 50, 25, None, 2022)
    r = _regra(res, "pontos")
    assert r["elegivel"] is False
    assert len(r["o_que_falta"]) == 2
    assert any("pontos" in x for x in r["o_que_falta"])
    assert any("tempo de contribuição" in x for x in r["o_que_falta"])


# ── RMI: honestidade (só com média do CNIS) ───────────────────────────────────

def test_rmi_null_sem_media():
    res = _sim("M", 65, 25, None, 2026)
    r = _regra(res, "pontos")
    assert r["coeficiente_rmi"] == Decimal("0.7000")
    assert r["rmi_estimada"] is None
    assert res["media_informada"] is False


def test_rmi_calculada_com_media():
    # H, 25 anos, coef 70%, média 4000 → RMI 2800.00
    res = _sim("M", 65, 25, 4000, 2026)
    r = _regra(res, "pontos")
    assert r["coeficiente_rmi"] == Decimal("0.7000")
    assert r["rmi_estimada"] == Decimal("2800.00")
    assert res["media_informada"] is True


# ── Pedágio 50%: coeficiente indeterminado (fator previdenciário) ─────────────

def test_pedagio50_coeficiente_null_honesto():
    res = _sim("M", 65, 40, 5000, 2026)
    r = _regra(res, "pedagio_50")
    assert r["coeficiente_rmi"] is None
    assert r["rmi_estimada"] is None  # não estima mesmo com média
    assert any("fator" in o.lower() for o in r["observacoes"])


# ── Pedágio 100%: RMI integral (coeficiente 100%) ─────────────────────────────

def test_pedagio100_coeficiente_integral():
    res = _sim("M", 65, 40, 5000, 2026)
    r = _regra(res, "pedagio_100")
    assert r["coeficiente_rmi"] == Decimal("1.00")
    # RMI = 100% da média
    assert r["rmi_estimada"] == Decimal("5000.00")


# ── melhor_regra: maior coeficiente entre elegíveis ───────────────────────────

def test_melhor_regra_maior_coeficiente_pedagio100():
    # H, 66 anos, 39 de contribuição, 2026: elegível em pontos (coef art.26 = 98%)
    # e no pedágio 100% (coef integral 100%). melhor_regra deve ser pedagio_100,
    # pois o coeficiente integral supera o do art. 26.
    res = _sim("M", 66, 39, 5000, 2026)
    r100 = _regra(res, "pedagio_100")
    rpontos = _regra(res, "pontos")
    assert r100["elegivel"] is True and rpontos["elegivel"] is True
    assert rpontos["coeficiente_rmi"] == Decimal("0.9800")
    assert r100["coeficiente_rmi"] == Decimal("1.00")
    assert res["melhor_regra"]["id"] == "pedagio_100"
    assert "coeficiente" in res["melhor_regra"]["motivo"]


def test_melhor_regra_mais_proxima_quando_ninguem_elegivel():
    # Jovem sem tempo: nenhuma regra elegível → melhor_regra aponta a mais próxima.
    res = _sim("M", 40, 12, None, 2026)
    assert res["regras_elegiveis"] == []
    assert res["melhor_regra"]["id"] is not None
    assert "mais próxima" in res["melhor_regra"]["motivo"]


# ── Schema de resposta valida ─────────────────────────────────────────────────

def test_schema_resposta_valida():
    from app.routers.previdenciario_beneficio import SimulacaoPrevidOut
    res = _sim("F", 62, 20, 3000, 2026)
    out = SimulacaoPrevidOut.model_validate(res)
    assert out.sexo == "feminino"
    assert len(out.regras) == 5
    assert out.base_legal_geral


# ── Guarda de payload no PDF (limites de Field) ───────────────────────────────

def test_pdf_payload_guard_rejeita_texto_gigante():
    from pydantic import ValidationError
    from app.routers.previdenciario_beneficio import SimulacaoPrevidOut
    res = _sim("F", 62, 20, 3000, 2026)
    res["aviso_hitl"] = "x" * 7000  # excede _TXT_LONGO (6000)
    with pytest.raises(ValidationError):
        SimulacaoPrevidOut.model_validate(res)


def test_pdf_payload_guard_rejeita_lista_gigante():
    from pydantic import ValidationError
    from app.routers.previdenciario_beneficio import SimulacaoPrevidOut
    res = _sim("F", 62, 20, 3000, 2026)
    res["regras_elegiveis"] = ["x"] * 50  # excede max_length=10
    with pytest.raises(ValidationError):
        SimulacaoPrevidOut.model_validate(res)
