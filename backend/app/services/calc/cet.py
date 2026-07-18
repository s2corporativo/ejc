# ── app/services/calc/cet.py ─────────────────────────────────────────────────
# Calculadora determinística de CET — Custo Efetivo Total.
# Base normativa vigente: Resolução CMN nº 4.881/2020 e IN BCB nº 83/2021.
# Sem IA: TIR resolvida numericamente sobre o fluxo de caixa em Decimal, com
# memória de cálculo auditável. HITL: o resultado é MINUTA de cálculo — o
# advogado revisa antes de usar em peça ou parecer.
#
# Convenção (Resolução CMN nº 4.881/2020 e IN BCB nº 83/2021):
#   FC0 = Σ FCj / (1 + CET)^(dj/365)
# onde FC0 é o valor LÍQUIDO entregue ao tomador na data da liberação
# (valor liberado − tarifas − IOF cobrados na contratação), FCj cada
# pagamento (parcela) e dj os dias corridos entre a liberação e o pagamento.
# O CET anual é a taxa que zera essa equação; o mensal deriva de
# (1+CET_aa)^(1/12) − 1.
#
# Convergência (documentada):
#   1) Newton-Raphson a partir de i0 = 50% a.a.; g(i) é estritamente
#      DECRESCENTE em i (todos os fluxos FCj > 0 e dj > 0), logo tem no
#      máximo uma raiz. Critérios: |Δi| < 1e-12 ou |g(i)| < tol; máx. 100
#      iterações; passos que saiam do domínio (i ≤ −0,9999) abortam p/ fallback.
#   2) Fallback: BISSEÇÃO em intervalo com troca de sinal garantida pela
#      monotonicidade de g (expande o teto até g(hi) < 0; máx. 300 iterações).
# Toda a aritmética é Decimal (potência via exp/ln com precisão local 40).
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP, localcontext

_CENT = Decimal("0.01")
_DIAS_ANO = Decimal("365")
_TOL_I = Decimal("1e-12")       # tolerância no passo da taxa
_MAX_NEWTON = 100
_MAX_BISSECAO = 300
_LIMIAR_DIVERGENCIA_PP = Decimal("0.5")   # p.p. anuais (Res. 4.881/2020 + CDC 46/52)

NORMA_CET_VIGENTE = "Resolução CMN nº 4.881/2020"
NORMA_OPERACIONAL_CET = "Instrução Normativa BCB nº 83/2021"

BASE_LEGAL_CET = [
    f"{NORMA_CET_VIGENTE} (cálculo e informação obrigatória do CET)",
    f"{NORMA_OPERACIONAL_CET} (esclarecimentos operacionais e demonstrativo do CET)",
    "CDC art. 46 (conhecimento prévio do conteúdo do contrato)",
    "CDC art. 52 (informação de juros, acréscimos e total a pagar)",
]

AVISOS_HITL = [
    "MINUTA DE CÁLCULO — sujeita à revisão do advogado responsável (HITL).",
    "O CET calculado considera apenas os fluxos informados; seguros, tributos ou "
    "tarifas não informados alteram o resultado.",
]


def _dec(v) -> Decimal:
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def _q(v: Decimal) -> Decimal:
    return v.quantize(_CENT, rounding=ROUND_HALF_UP)


def _pow(base: Decimal, expoente: Decimal) -> Decimal:
    """base**expoente em Decimal (base > 0), via exp(expoente·ln(base))."""
    if base <= 0:
        raise ValueError("Base de potência deve ser positiva")
    with localcontext() as ctx:
        ctx.prec = 40
        return (expoente * base.ln()).exp()


def add_months(d: date, meses: int) -> date:
    """Soma meses mantendo o dia (clamp no fim do mês). Sem dependência externa."""
    import calendar
    m = d.month - 1 + meses
    ano, mes = d.year + m // 12, m % 12 + 1
    return date(ano, mes, min(d.day, calendar.monthrange(ano, mes)[1]))


def parcela_price(pv: Decimal, i_m: Decimal, n: int) -> Decimal:
    """Prestação pela Tabela Price: PMT = PV·i / (1 − (1+i)^−n). Decimal puro."""
    pv, i_m = _dec(pv), _dec(i_m)
    if n <= 0:
        raise ValueError("Número de parcelas deve ser positivo")
    if pv <= 0:
        raise ValueError("Valor presente deve ser positivo")
    if i_m == 0:
        return _q(pv / Decimal(n))
    if i_m <= Decimal("-1"):
        raise ValueError("Taxa mensal inválida")
    fator = _pow(Decimal(1) + i_m, Decimal(-n))
    return _q(pv * i_m / (Decimal(1) - fator))


def _g(ia: Decimal, fluxos: list[tuple[Decimal, Decimal]], liquido: Decimal) -> Decimal:
    """g(ia) = Σ FCj·(1+ia)^(−tj) − FC0. Raiz de g = CET anual."""
    um_mais = Decimal(1) + ia
    return sum(p * _pow(um_mais, -t) for p, t in fluxos) - liquido


def _g_derivada(ia: Decimal, fluxos: list[tuple[Decimal, Decimal]]) -> Decimal:
    um_mais = Decimal(1) + ia
    return sum(-t * p * _pow(um_mais, -t - 1) for p, t in fluxos)


def _resolver_tir(fluxos: list[tuple[Decimal, Decimal]], liquido: Decimal) -> dict:
    """Resolve a TIR anual. Newton-Raphson; bisseção como fallback garantido."""
    tol_g = max(liquido * Decimal("1e-10"), Decimal("1e-6"))

    # ── Newton-Raphson ──
    ia = Decimal("0.5")
    for it in range(1, _MAX_NEWTON + 1):
        g = _g(ia, fluxos, liquido)
        if abs(g) < tol_g:
            return {"taxa": ia, "metodo": "newton-raphson", "iteracoes": it,
                    "residuo": g}
        d = _g_derivada(ia, fluxos)
        if d == 0:
            break
        novo = ia - g / d
        if novo <= Decimal("-0.9999") or novo > Decimal("1e6"):
            break  # saiu do domínio — bisseção resolve
        if abs(novo - ia) < _TOL_I:
            return {"taxa": novo, "metodo": "newton-raphson", "iteracoes": it,
                    "residuo": _g(novo, fluxos, liquido)}
        ia = novo

    # ── Bisseção (g estritamente decrescente ⇒ troca de sinal única) ──
    total = sum(p for p, _ in fluxos)
    if total > liquido:                      # raiz positiva
        lo, hi = Decimal(0), Decimal(1)
        while _g(hi, fluxos, liquido) > 0 and hi < Decimal("1e6"):
            hi *= 2
    else:                                    # taxa ≤ 0 (fluxo devolve menos que o líquido)
        lo, hi = Decimal("-0.9999"), Decimal(0)
    for it in range(1, _MAX_BISSECAO + 1):
        meio = (lo + hi) / 2
        g = _g(meio, fluxos, liquido)
        if abs(g) < tol_g or (hi - lo) < _TOL_I:
            return {"taxa": meio, "metodo": "bissecao", "iteracoes": it, "residuo": g}
        if g > 0:
            lo = meio
        else:
            hi = meio
    raise ValueError("TIR não convergiu (fluxo de caixa inconsistente)")


def calcular_cet(
    valor_liberado,
    data_liberacao: date,
    parcelas: list[dict] | None = None,
    n_parcelas: int | None = None,
    valor_parcela=None,
    primeiro_vencimento: date | None = None,
    tarifas_incluidas=0,
    iof=0,
    cet_informado_aa_pct=None,
) -> dict:
    """Calcula o CET (mensal e anual) de uma operação de crédito.

    Entrada de fluxo em UM dos dois modos:
      • ``parcelas``: lista de {"valor", "vencimento"} (datas reais do contrato); OU
      • ``n_parcelas`` + ``valor_parcela`` + ``primeiro_vencimento`` (série mensal).
    ``tarifas_incluidas`` e ``iof`` são encargos cobrados na contratação e
    REDUZEM o valor líquido entregue (FC0) — é isso que faz o CET superar a
    taxa de juros nominal. ``cet_informado_aa_pct`` (opcional) dispara a
    verificação de divergência (> 0,5 p.p. a.a. = achado).
    """
    vl = _dec(valor_liberado)
    tarifas = _dec(tarifas_incluidas or 0)
    iof_d = _dec(iof or 0)
    if vl <= 0:
        raise ValueError("valor_liberado deve ser positivo")
    if tarifas < 0 or iof_d < 0:
        raise ValueError("tarifas_incluidas e iof não podem ser negativos")
    liquido = vl - tarifas - iof_d
    if liquido <= 0:
        raise ValueError("Valor líquido (liberado − tarifas − IOF) deve ser positivo")

    # ── Normaliza o fluxo de pagamentos ──────────────────────────────────────
    serie: list[tuple[date, Decimal]] = []
    if parcelas:
        for i, p in enumerate(parcelas, 1):
            venc = p["vencimento"]
            if isinstance(venc, str):
                venc = date.fromisoformat(venc)
            serie.append((venc, _dec(p["valor"])))
    elif n_parcelas and valor_parcela is not None and primeiro_vencimento:
        vp = _dec(valor_parcela)
        for k in range(int(n_parcelas)):
            serie.append((add_months(primeiro_vencimento, k), vp))
    else:
        raise ValueError("Informe 'parcelas' OU (n_parcelas, valor_parcela, primeiro_vencimento)")

    if not serie:
        raise ValueError("Fluxo de pagamentos vazio")
    fluxos: list[tuple[Decimal, Decimal]] = []   # (valor, t em anos)
    fluxo_detalhe = []
    for venc, valor in sorted(serie, key=lambda x: x[0]):
        if valor <= 0:
            raise ValueError("Toda parcela deve ter valor positivo")
        dias = (venc - data_liberacao).days
        if dias <= 0:
            raise ValueError(f"Vencimento {venc.isoformat()} não é posterior à liberação")
        fluxos.append((valor, Decimal(dias) / _DIAS_ANO))
        fluxo_detalhe.append({"vencimento": venc.isoformat(), "valor": float(_q(valor)),
                              "dias": dias})

    # ── TIR anual → CET mensal ───────────────────────────────────────────────
    sol = _resolver_tir(fluxos, liquido)
    ia = sol["taxa"]
    im = _pow(Decimal(1) + ia, Decimal(1) / Decimal(12)) - Decimal(1)
    cet_aa_pct = (ia * 100).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    cet_am_pct = (im * 100).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    total_pago = sum(p for p, _ in fluxos)
    memoria = [
        f"1. Valor liberado: R$ {_q(vl)} − tarifas R$ {_q(tarifas)} − IOF R$ {_q(iof_d)} "
        f"= valor líquido entregue (FC0) R$ {_q(liquido)}.",
        f"2. Fluxo de pagamentos: {len(fluxos)} parcela(s), total R$ {_q(total_pago)}; "
        f"prazos de {fluxo_detalhe[0]['dias']} a {fluxo_detalhe[-1]['dias']} dias corridos.",
        f"3. Equação do CET ({NORMA_CET_VIGENTE}; {NORMA_OPERACIONAL_CET}): "
        "FC0 = Σ FCj / (1 + CET)^(dj/365).",
        f"4. Resolução numérica: método {sol['metodo']}, {sol['iteracoes']} iteração(ões), "
        f"resíduo |g| = {abs(sol['residuo']):.2E} (aritmética Decimal).",
        f"5. CET anual = {cet_aa_pct}% a.a.; CET mensal = (1+CET_aa)^(1/12) − 1 "
        f"= {cet_am_pct}% a.m.",
    ]

    # ── Divergência com o CET informado no contrato ──────────────────────────
    divergencia = None
    if cet_informado_aa_pct is not None:
        informado = _dec(cet_informado_aa_pct)
        dif = abs(cet_aa_pct - informado)
        memoria.append(
            f"6. CET informado no contrato: {informado}% a.a.; diferença de "
            f"{dif.quantize(Decimal('0.0001'))} p.p. (limiar: {_LIMIAR_DIVERGENCIA_PP} p.p.)."
        )
        if dif > _LIMIAR_DIVERGENCIA_PP:
            divergencia = {
                "achado": "CET informado diverge do calculado",
                "cet_informado_aa_pct": float(informado),
                "cet_calculado_aa_pct": float(cet_aa_pct),
                "diferenca_pp": float(dif.quantize(Decimal("0.0001"))),
                "limiar_pp": float(_LIMIAR_DIVERGENCIA_PP),
                "base_legal": BASE_LEGAL_CET,
                "observacao": (
                    "A divergência entre o CET informado e o efetivamente praticado "
                    "pode caracterizar violação ao dever de informação (CDC arts. 46 e "
                    f"52; {NORMA_CET_VIGENTE}). Verificar se todos os encargos foram "
                    "considerados antes de alegar em juízo."
                ),
            }

    return {
        "cet_mensal_pct": float(cet_am_pct),
        "cet_anual_pct": float(cet_aa_pct),
        "valor_liberado_liquido": float(_q(liquido)),
        "total_pago": float(_q(total_pago)),
        "fluxo": fluxo_detalhe,
        "convergencia": {"metodo": sol["metodo"], "iteracoes": sol["iteracoes"],
                         "residuo": float(sol["residuo"])},
        "memoria_calculo": memoria,
        "divergencia": divergencia,
        "base_legal": BASE_LEGAL_CET,
        "avisos": AVISOS_HITL,
    }
