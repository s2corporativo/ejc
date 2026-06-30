# ── app/services/calc/trabalhista.py ─────────────────────────────────────────
# Calculadora de verbas rescisórias (CLT) — gera memória de cálculo auditável.
# Usa as tabelas tributárias verificadas (tax_tables.py). HITL: o resultado é
# uma MINUTA de cálculo; o advogado revisa antes de usar em peça ou acordo.
#
# Cobre os tipos de rescisão mais comuns. Regras aplicadas (base legal):
#  • Aviso prévio proporcional: 30 dias + 3 dias/ano, máx. 90 (Lei 12.506/2011)
#  • 13º proporcional e férias proporcionais por avos (≥15 dias = 1/12)
#  • 1/3 constitucional sobre férias (CF art. 7º, XVII)
#  • Multa FGTS: 40% (sem justa causa) ou 20% (acordo art. 484-A CLT)
#  • Verbas indenizatórias (aviso indenizado, férias indenizadas, multa FGTS)
#    NÃO sofrem INSS/IRRF; saldo de salário e 13º sofrem (cálculo separado).
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from app.services.calc.tax_tables import inss as calc_inss, irrf as calc_irrf

_CENT = Decimal("0.01")


def _q(v: Decimal) -> Decimal:
    return v.quantize(_CENT, rounding=ROUND_HALF_UP)


# Tipos suportados e suas regras (verbas devidas + multa FGTS)
TIPOS = {
    "sem_justa_causa": {"rotulo": "Dispensa sem justa causa", "multa_fgts": Decimal("0.40"),
                         "aviso": True, "ferias_prop": True, "decimo_prop": True, "saque_fgts": True},
    "pedido_demissao": {"rotulo": "Pedido de demissão", "multa_fgts": Decimal("0"),
                        "aviso": False, "ferias_prop": True, "decimo_prop": True, "saque_fgts": False},
    "justa_causa":     {"rotulo": "Dispensa por justa causa", "multa_fgts": Decimal("0"),
                        "aviso": False, "ferias_prop": False, "decimo_prop": False, "saque_fgts": False},
    "acordo_484a":     {"rotulo": "Acordo (art. 484-A CLT)", "multa_fgts": Decimal("0.20"),
                        "aviso": True, "ferias_prop": True, "decimo_prop": True, "saque_fgts": True,
                        "aviso_metade": True},
}


@dataclass
class EntradaRescisao:
    salario: float
    admissao: date
    demissao: date
    tipo: str = "sem_justa_causa"
    aviso_indenizado: bool = True       # True = indenizado; False = trabalhado
    dias_trabalhados_mes: int | None = None   # saldo de salário; default = dia da demissão
    ferias_vencidas: bool = False       # há período de férias vencido não gozado?
    saldo_fgts: float = 0.0             # saldo depositado (para multa)
    dependentes: int = 0


def _meses_avos(ini: date, fim: date) -> int:
    """Conta avos (meses) considerando fração ≥ 15 dias como mês cheio."""
    meses = (fim.year - ini.year) * 12 + (fim.month - ini.month)
    if fim.day >= 15:
        meses += 1
    # avos do período aquisitivo de 13º/férias contam dentro do ano; clamp 0..12
    return max(0, min(meses, 12))


def _anos_completos(ini: date, fim: date) -> int:
    anos = fim.year - ini.year - ((fim.month, fim.day) < (ini.month, ini.day))
    return max(0, anos)


def calcular(e: EntradaRescisao) -> dict:
    """Calcula as verbas rescisórias. Retorna memória completa e auditável."""
    if e.tipo not in TIPOS:
        raise ValueError(f"Tipo inválido. Use: {list(TIPOS)}")
    regra = TIPOS[e.tipo]
    sal = Decimal(str(e.salario))
    if sal <= 0:
        raise ValueError("Salário deve ser positivo")
    if e.demissao < e.admissao:
        raise ValueError("Demissão anterior à admissão")

    salario_dia = sal / Decimal("30")
    proventos: list[dict] = []
    descontos: list[dict] = []

    # 1) Saldo de salário
    dias = e.dias_trabalhados_mes if e.dias_trabalhados_mes is not None else e.demissao.day
    dias = max(0, min(dias, 30))
    saldo_salario = _q(salario_dia * Decimal(dias))
    proventos.append({"verba": f"Saldo de salário ({dias} dias)", "valor": float(saldo_salario),
                      "incide_inss": True, "incide_irrf": True})

    # 2) Aviso prévio
    anos = _anos_completos(e.admissao, e.demissao)
    aviso_dias = min(30 + 3 * anos, 90)
    aviso_valor = Decimal("0")
    if regra["aviso"] and e.aviso_indenizado:
        aviso_valor = _q(salario_dia * Decimal(aviso_dias))
        if regra.get("aviso_metade"):    # acordo 484-A: aviso indenizado pela metade
            aviso_valor = _q(aviso_valor / 2)
        proventos.append({"verba": f"Aviso prévio indenizado ({aviso_dias} dias"
                          f"{' — 50% acordo' if regra.get('aviso_metade') else ''})",
                          "valor": float(aviso_valor),
                          "incide_inss": False, "incide_irrf": False})

    # Projeção do aviso indenizado estende a data-base p/ avos de 13º/férias
    fim_projetado = e.demissao
    if regra["aviso"] and e.aviso_indenizado:
        # projeção simples: soma dias do aviso (Súmula 371 TST / OJ 82 SDI-1)
        from datetime import timedelta
        fim_projetado = e.demissao + timedelta(days=aviso_dias)

    # 3) 13º proporcional
    if regra["decimo_prop"]:
        meses13 = _meses_avos(date(fim_projetado.year, 1, 1)
                              if e.admissao.year < fim_projetado.year else e.admissao,
                              fim_projetado)
        decimo = _q(sal / Decimal("12") * Decimal(meses13))
        proventos.append({"verba": f"13º salário proporcional ({meses13}/12)",
                          "valor": float(decimo), "incide_inss": True,
                          "incide_irrf": True, "tributo_separado": True})

    # 4) Férias proporcionais + 1/3
    if regra["ferias_prop"]:
        # avos do período aquisitivo em curso (desde o último aniversário de admissão)
        ult_aniv = date(fim_projetado.year, e.admissao.month, e.admissao.day) \
            if (e.admissao.month, e.admissao.day) <= (fim_projetado.month, fim_projetado.day) \
            else date(fim_projetado.year - 1, e.admissao.month, e.admissao.day)
        mfp = _meses_avos(ult_aniv, fim_projetado)
        ferias_prop = _q(sal / Decimal("12") * Decimal(mfp))
        terco_prop = _q(ferias_prop / Decimal("3"))
        proventos.append({"verba": f"Férias proporcionais ({mfp}/12)", "valor": float(ferias_prop),
                          "incide_inss": False, "incide_irrf": False})
        proventos.append({"verba": "1/3 sobre férias proporcionais", "valor": float(terco_prop),
                          "incide_inss": False, "incide_irrf": False})

    # 5) Férias vencidas + 1/3 (se houver)
    if e.ferias_vencidas:
        ferias_venc = sal
        terco_venc = _q(sal / Decimal("3"))
        proventos.append({"verba": "Férias vencidas + 1/3", "valor": float(_q(ferias_venc + terco_venc)),
                          "incide_inss": False, "incide_irrf": False})

    # 6) Multa FGTS (sobre saldo depositado informado)
    multa_fgts = Decimal("0")
    if regra["multa_fgts"] > 0 and e.saldo_fgts > 0:
        multa_fgts = _q(Decimal(str(e.saldo_fgts)) * regra["multa_fgts"])
        proventos.append({"verba": f"Multa FGTS ({int(regra['multa_fgts']*100)}%)",
                          "valor": float(multa_fgts), "incide_inss": False, "incide_irrf": False})

    # ── Descontos: INSS e IRRF ───────────────────────────────────────────────
    # INSS sobre saldo de salário
    inss_saldo = Decimal(str(calc_inss(float(saldo_salario))["inss"]))
    descontos.append({"verba": "INSS sobre saldo de salário", "valor": float(inss_saldo)})
    # INSS sobre 13º (cálculo separado — Súmula/normativo: 13º tem tributação própria)
    inss_13 = Decimal("0")
    decimo_val = next((Decimal(str(p["valor"])) for p in proventos
                       if p["verba"].startswith("13º")), Decimal("0"))
    if decimo_val > 0:
        inss_13 = Decimal(str(calc_inss(float(decimo_val))["inss"]))
        descontos.append({"verba": "INSS sobre 13º salário", "valor": float(inss_13)})

    # IRRF sobre saldo de salário (base = saldo − INSS_saldo)
    irrf_saldo_r = calc_irrf(float(saldo_salario), float(inss_saldo), dependentes=e.dependentes)
    irrf_saldo = Decimal(str(irrf_saldo_r["irrf"]))
    if irrf_saldo > 0:
        descontos.append({"verba": "IRRF sobre saldo de salário", "valor": float(irrf_saldo)})
    # IRRF sobre 13º (separado)
    irrf_13 = Decimal("0")
    if decimo_val > 0:
        irrf_13_r = calc_irrf(float(decimo_val), float(inss_13), dependentes=e.dependentes)
        irrf_13 = Decimal(str(irrf_13_r["irrf"]))
        if irrf_13 > 0:
            descontos.append({"verba": "IRRF sobre 13º salário", "valor": float(irrf_13)})

    total_proventos = _q(sum(Decimal(str(p["valor"])) for p in proventos))
    total_descontos = _q(sum(Decimal(str(d["valor"])) for d in descontos))
    liquido = _q(total_proventos - total_descontos)

    return {
        "tipo": regra["rotulo"],
        "parametros": {
            "salario": float(sal),
            "admissao": e.admissao.isoformat(),
            "demissao": e.demissao.isoformat(),
            "anos_completos": anos,
            "aviso_dias": aviso_dias if regra["aviso"] else 0,
            "aviso_indenizado": bool(regra["aviso"] and e.aviso_indenizado),
            "data_projetada_aviso": fim_projetado.isoformat(),
            "dependentes": e.dependentes,
        },
        "proventos": proventos,
        "descontos": descontos,
        "total_proventos": float(total_proventos),
        "total_descontos": float(total_descontos),
        "liquido": float(liquido),
        "saque_fgts_liberado": regra["saque_fgts"],
        "avisos": [
            "MINUTA DE CÁLCULO — sujeita à revisão do advogado responsável (HITL).",
            "Verbas indenizatórias (aviso/férias indenizadas, multa FGTS) não sofrem INSS/IRRF.",
            "13º e saldo de salário têm INSS/IRRF calculados separadamente.",
            "Não inclui: horas extras, adicionais, reflexos, descontos de adiantamentos/benefícios.",
        ],
        "fonte_tributaria": "INSS Portaria MPS/MF 13/2026 · IRRF tabela 2026 (RFB)",
    }
