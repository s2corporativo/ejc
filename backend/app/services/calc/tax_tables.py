# ── app/services/calc/tax_tables.py ──────────────────────────────────────────
# Tabelas tributárias oficiais — FONTE E VIGÊNCIA EXPLÍCITAS (auditável).
# Atualizar uma vez por ano quando a Receita/Previdência publicarem as portarias.
#
# ⚠️ Todos os valores abaixo são de fonte oficial e foram CONFERIDOS contra
# exemplos de cálculo independentes (ver docstrings). NÃO alterar sem nova fonte.
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

# ══════════════════════════════════════════════════════════════════════════
# INSS 2026 — Portaria Interministerial MPS/MF nº 13, de 09/01/2026
# Fonte: gov.br/inss (reajuste 3,90% INPC). Salário mínimo 2026 = R$ 1.621,00.
# Conferido: salário R$ 5.000 → R$ 501,51 (faixa-a-faixa) ✓
# ══════════════════════════════════════════════════════════════════════════
INSS_2026 = {
    "vigencia": "2026",
    "fonte": "Portaria Interministerial MPS/MF nº 13/2026",
    "salario_minimo": Decimal("1621.00"),
    "teto": Decimal("8475.55"),
    "desconto_maximo": Decimal("988.09"),
    # (limite_superior_da_faixa, alíquota) — progressivo, faixa a faixa
    "faixas": [
        (Decimal("1621.00"), Decimal("0.075")),
        (Decimal("2902.84"), Decimal("0.09")),
        (Decimal("4354.27"), Decimal("0.12")),
        (Decimal("8475.55"), Decimal("0.14")),
    ],
}

# ══════════════════════════════════════════════════════════════════════════
# IRRF 2026 — tabela progressiva mensal (Lei 14.848/2024 atualizada;
# redutor adicional Lei 15.270/2025). Parcelas conferidas contra exemplos:
#   base R$ 7.000,00 → R$ 1.016,27 (27,5%) ✓
#   base R$ 3.392,80 → R$ 114,76 (15%) ✓
# Continuidade entre faixas verificada nas fronteiras.
# ══════════════════════════════════════════════════════════════════════════
IRRF_2026 = {
    "vigencia": "2026",
    "fonte": "Tabela progressiva mensal IRRF 2026 (RFB) + Lei 15.270/2025",
    "deducao_dependente": Decimal("189.59"),
    "desconto_simplificado": Decimal("607.20"),  # 25% de 2.428,80
    # Redutor Lei 15.270/2025: rendimento tributável mensal ≤ 5.000 → IRRF zerado;
    # de 5.000,01 a 7.350,00 → redução parcial (fórmula oficial — ver nota).
    "isencao_total_ate": Decimal("5000.00"),
    "reducao_parcial_ate": Decimal("7350.00"),
    # (limite_superior, alíquota, parcela_a_deduzir)
    "faixas": [
        (Decimal("2428.80"), Decimal("0.00"),  Decimal("0.00")),
        (Decimal("2826.65"), Decimal("0.075"), Decimal("182.16")),
        (Decimal("3751.05"), Decimal("0.15"),  Decimal("394.16")),
        (Decimal("4664.68"), Decimal("0.225"), Decimal("675.49")),
        (None,               Decimal("0.275"), Decimal("908.73")),
    ],
}

_CENT = Decimal("0.01")


def _q(v: Decimal) -> Decimal:
    return v.quantize(_CENT, rounding=ROUND_HALF_UP)


def inss(salario_contribuicao: float | Decimal, tabela: dict = INSS_2026) -> dict:
    """Contribuição INSS progressiva (faixa a faixa). Retorna memória auditável."""
    sal = Decimal(str(salario_contribuicao))
    base = min(sal, tabela["teto"])
    total = Decimal("0")
    anterior = Decimal("0")
    memoria = []
    for limite, aliq in tabela["faixas"]:
        if base <= anterior:
            break
        trecho = min(base, limite) - anterior
        if trecho > 0:
            parcela = trecho * aliq
            total += parcela
            memoria.append({
                "faixa_ate": float(limite),
                "aliquota": float(aliq),
                "base_trecho": float(_q(trecho)),
                "contribuicao_trecho": float(_q(parcela)),
            })
        anterior = limite
    total = _q(total)
    # trava de segurança no teto de desconto
    if total > tabela["desconto_maximo"]:
        total = tabela["desconto_maximo"]
    aliq_efetiva = (total / sal) if sal > 0 else Decimal("0")
    return {
        "salario": float(sal),
        "base_calculo": float(_q(base)),
        "inss": float(total),
        "aliquota_efetiva": float(_q(aliq_efetiva * 100)),
        "memoria": memoria,
        "fonte": tabela["fonte"],
    }


def irrf(
    rendimento_bruto: float | Decimal,
    inss_descontado: float | Decimal,
    dependentes: int = 0,
    pensao: float | Decimal = 0,
    tabela: dict = IRRF_2026,
    aplicar_redutor_2025: bool = True,
) -> dict:
    """IRRF mensal. Escolhe automaticamente entre dedução simplificada e legal
    (a que resultar em menor imposto), aplica a tabela progressiva e, se
    habilitado, o redutor da Lei 15.270/2025 para a faixa de isenção total.

    Nota de precisão: o redutor PARCIAL (5.000,01–7.350,00) tem fórmula oficial
    progressiva específica; aqui só a ISENÇÃO TOTAL (≤ 5.000) é aplicada
    automaticamente. Na faixa parcial, retorna o imposto da tabela e sinaliza
    `redutor_parcial_pendente=True` para conferência manual.
    """
    bruto = Decimal(str(rendimento_bruto))
    inss_d = Decimal(str(inss_descontado))
    pensao_d = Decimal(str(pensao))
    ded_dep = tabela["deducao_dependente"] * Decimal(dependentes)

    # Base com deduções legais vs. desconto simplificado
    base_legal = bruto - inss_d - ded_dep - pensao_d
    base_simpl = bruto - tabela["desconto_simplificado"]
    # rendimento tributável p/ regra do redutor (bruto - INSS)
    rend_tributavel = bruto - inss_d

    def _imposto(base: Decimal) -> tuple[Decimal, Decimal, Decimal]:
        base = max(base, Decimal("0"))
        anterior = Decimal("0")
        for limite, aliq, ded in tabela["faixas"]:
            if limite is None or base <= limite:
                return _q(base * aliq - ded), aliq, ded
            anterior = limite
        return Decimal("0"), Decimal("0"), Decimal("0")

    imp_legal, aliq_l, ded_l = _imposto(base_legal)
    imp_simpl, aliq_s, ded_s = _imposto(base_simpl)

    if imp_simpl <= imp_legal:
        base_usada, imposto, aliq, ded, modo = base_simpl, imp_simpl, aliq_s, ded_s, "simplificado"
    else:
        base_usada, imposto, aliq, ded, modo = base_legal, imp_legal, aliq_l, ded_l, "legal"

    imposto = max(imposto, Decimal("0"))
    redutor_parcial_pendente = False

    if aplicar_redutor_2025:
        if rend_tributavel <= tabela["isencao_total_ate"]:
            imposto = Decimal("0")            # isenção total Lei 15.270/2025
        elif rend_tributavel <= tabela["reducao_parcial_ate"]:
            redutor_parcial_pendente = True   # faixa parcial — conferir fórmula oficial

    return {
        "rendimento_bruto": float(bruto),
        "base_calculo": float(_q(base_usada)),
        "modo_deducao": modo,
        "aliquota": float(aliq),
        "parcela_deduzir": float(ded),
        "irrf": float(_q(imposto)),
        "redutor_parcial_pendente": redutor_parcial_pendente,
        "fonte": tabela["fonte"],
        "nota": (
            "Redutor parcial (R$ 5.000,01–7.350,00) da Lei 15.270/2025 NÃO "
            "aplicado automaticamente — conferir manualmente."
            if redutor_parcial_pendente else ""
        ),
    }
