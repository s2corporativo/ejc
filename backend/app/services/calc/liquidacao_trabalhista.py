# ── app/services/calc/liquidacao_trabalhista.py ─────────────────────────────
# Liquidação de sentença trabalhista — calculadora DETERMINÍSTICA e STATELESS
# (sem IA, sem persistência, sem migration). A partir das verbas deferidas na
# sentença, monta a planilha de liquidação com memória auditável.
#
# HONESTIDADE (índices de correção são matéria jurídica sensível):
#   • Correção monetária + juros: regime do ADC 58/59 do STF. A partir do
#     AJUIZAMENTO a taxa SELIC engloba correção E juros de mora (não se soma
#     juros por fora). Antes do ajuizamento incide o IPCA-E. Para a fase Selic
#     usamos a Selic acumulada REAL do BCB (SGS 4390) — reuso de bcb_service.
#     A fase IPCA-E só é aplicada se o usuário informar o fator real do período
#     ("fator_ipcae_pre_ajuizamento"); do contrário NÃO estimamos: emitimos
#     ALERTA e o principal segue sem essa correção.
#   • FGTS 8% + multa 40%: percentuais legais CLAROS, aplicados sobre a base de
#     natureza SALARIAL (o usuário marca cada verba salarial|indenizatoria).
#   • INSS/IRRF: como as tabelas mudam a cada ano, NÃO chutamos alíquota —
#     destacamos a base de cálculo e marcamos o valor como "a apurar" (alerta).
#
# HITL: toda a saída é MINUTA — o contador/advogado confere antes de usar.
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from app.services import bcb_service

_CENT = Decimal("0.01")

# Percentuais legais claros (base legal citada na saída).
FGTS_ALIQUOTA = Decimal("0.08")        # Lei 8.036/90, art. 15
MULTA_FGTS_ALIQUOTA = Decimal("0.40")  # Lei 8.036/90, art. 18, §1º
_HON_MIN = Decimal("5")                 # CLT art. 791-A — honorários sucumbenciais
_HON_MAX = Decimal("15")

NATUREZAS = ("salarial", "indenizatoria")

BASE_LEGAL = [
    "ADC 58 e ADC 59/STF — critério de atualização dos créditos trabalhistas: "
    "IPCA-E na fase pré-judicial e taxa SELIC (que engloba correção e juros de "
    "mora) a partir do ajuizamento da ação.",
    "Lei 8.036/90, art. 15 (FGTS 8%) e art. 18, §1º (multa de 40%).",
    "Súmula 462/TST — FGTS integra a condenação quando há reconhecimento em juízo.",
    "CLT art. 791-A (Lei 13.467/2017) — honorários sucumbenciais de 5% a 15% "
    "sobre o valor que resultar da liquidação da sentença.",
    "Lei 8.212/91 e Decreto 3.048/99 (INSS) · RIR/2018 e IN RFB (IRRF) — "
    "incidem sobre as parcelas de natureza salarial/tributável (tabela do ano).",
]

AVISO_HITL = (
    "MINUTA DE LIQUIDAÇÃO — sujeita à conferência do contador/advogado "
    "responsável (HITL). Os índices de correção e as tabelas de INSS/IRRF são "
    "matéria sensível: confira o regime aplicado e os valores marcados como "
    "'a apurar' antes de peticionar."
)


def _dec(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _q(v: Decimal) -> Decimal:
    return v.quantize(_CENT, rounding=ROUND_HALF_UP)


def _moeda(v: Decimal) -> str:
    inteiro, _, dec = f"{_q(v):,.2f}".partition(".")
    return "R$ " + inteiro.replace(",", ".") + "," + dec


async def calcular_liquidacao(
    verbas: list[dict],
    data_ajuizamento: date,
    data_calculo: date,
    percentual_honorarios,
    fator_ipcae_pre_ajuizamento=None,
    hoje: date | None = None,
) -> dict:
    """Calcula a planilha de liquidação de sentença trabalhista.

    verbas: lista de {"rubrica": str, "valor": Decimal|num, "natureza":
        "salarial"|"indenizatoria"}. A natureza define a base de FGTS/INSS.
    data_ajuizamento / data_calculo: delimitam a fase SELIC (ADC 58).
    percentual_honorarios: percentual (0–100) sobre o principal corrigido.
    fator_ipcae_pre_ajuizamento: fator IPCA-E REAL do período do débito até o
        ajuizamento (opcional). Se ausente, a fase IPCA-E NÃO é aplicada e um
        alerta é emitido — nunca estimamos o índice.
    """
    hoje = hoje or date.today()

    # ── Validações ────────────────────────────────────────────────────────────
    if not verbas:
        raise ValueError("Informe ao menos uma verba deferida.")
    if data_calculo <= data_ajuizamento:
        raise ValueError("data_calculo deve ser posterior à data_ajuizamento.")
    if data_calculo > hoje:
        raise ValueError("data_calculo não pode ser futura (a Selic real ainda "
                         "não foi divulgada para o período).")
    pct_hon = _dec(percentual_honorarios)
    if pct_hon < 0 or pct_hon > 100:
        raise ValueError("percentual_honorarios deve estar entre 0 e 100.")

    alertas: list[str] = []
    base_salarial = Decimal("0")
    base_indenizatoria = Decimal("0")
    verbas_norm: list[dict] = []
    for i, item in enumerate(verbas, 1):
        rubrica = str(item.get("rubrica") or f"Verba {i}")
        natureza = str(item.get("natureza") or "").lower()
        if natureza not in NATUREZAS:
            raise ValueError(f"Verba '{rubrica}': natureza deve ser "
                             f"'salarial' ou 'indenizatoria'.")
        valor = _dec(item.get("valor"))
        if valor <= 0:
            raise ValueError(f"Verba '{rubrica}': valor deve ser positivo.")
        if natureza == "salarial":
            base_salarial += valor
        else:
            base_indenizatoria += valor
        verbas_norm.append({"rubrica": rubrica, "valor": float(_q(valor)),
                            "natureza": natureza})

    principal_bruto = base_salarial + base_indenizatoria

    # ── FGTS + multa 40% (percentuais legais claros, sobre a base SALARIAL) ────
    fgts = _q(base_salarial * FGTS_ALIQUOTA)
    multa_fgts = _q(fgts * MULTA_FGTS_ALIQUOTA)

    memoria: list[str] = [
        f"1. Principal bruto (soma das verbas deferidas): {_moeda(principal_bruto)} "
        f"— base salarial {_moeda(base_salarial)} + base indenizatória "
        f"{_moeda(base_indenizatoria)}.",
        f"2. FGTS = 8% da base salarial ({_moeda(base_salarial)}) = {_moeda(fgts)} "
        "(Lei 8.036/90, art. 15; Súmula 462/TST).",
        f"3. Multa do FGTS = 40% do FGTS ({_moeda(fgts)}) = {_moeda(multa_fgts)} "
        "(Lei 8.036/90, art. 18, §1º).",
    ]

    # ── Correção monetária + juros (ADC 58) ───────────────────────────────────
    # Fase 1 (pré-ajuizamento): IPCA-E — só se o fator real for informado.
    if fator_ipcae_pre_ajuizamento is not None:
        fator_ipcae = _dec(fator_ipcae_pre_ajuizamento)
        if fator_ipcae <= 0:
            raise ValueError("fator_ipcae_pre_ajuizamento deve ser positivo.")
        principal_pos_ipcae = _q(principal_bruto * fator_ipcae)
        memoria.append(
            f"4. Fase IPCA-E (pré-ajuizamento, ADC 58): fator informado "
            f"{fator_ipcae} × principal {_moeda(principal_bruto)} = "
            f"{_moeda(principal_pos_ipcae)}.")
    else:
        fator_ipcae = None
        principal_pos_ipcae = principal_bruto
        alertas.append(
            "IPCA-E pré-ajuizamento NÃO aplicado: informe "
            "'fator_ipcae_pre_ajuizamento' (fator real do IPCA-E entre a data do "
            "débito e o ajuizamento) ou calcule esse índice à parte. O principal "
            "segue sem a correção da fase pré-judicial (ADC 58).")
        memoria.append(
            "4. Fase IPCA-E (pré-ajuizamento): não aplicada — fator não informado "
            "(ver alertas). Principal mantido em " + _moeda(principal_bruto) + ".")

    # Fase 2 (a partir do ajuizamento): SELIC acumulada REAL do BCB (SGS 4390),
    # que já engloba correção + juros de mora (ADC 58). Fail-soft se o BCB cair.
    fator_selic = Decimal("1")
    fonte_selic = "indisponível"
    meses_selic = 0
    try:
        corr = await bcb_service.atualizar_valor(
            valor=float(principal_pos_ipcae),
            data_inicial=data_ajuizamento,
            data_final=data_calculo,
            indice="selic",
        )
        fator_selic = _dec(corr["fator_correcao"])
        meses_selic = int(corr.get("meses_aplicados") or 0)
        fonte_selic = corr.get("fonte", "Banco Central — SGS série 4390")
        if meses_selic == 0:
            alertas.append(
                "Selic acumulada = 0 meses no período informado (o BCB ainda não "
                "divulgou índices para a janela). Correção da fase Selic não "
                "aplicada — reavalie a data_calculo.")
    except Exception as exc:  # noqa: BLE001 — fail-soft: nunca inventa fator
        alertas.append(
            f"Selic do BCB indisponível ({exc}); a correção da fase Selic (ADC 58) "
            "NÃO foi aplicada. Reprocesse quando o Banco Central responder — o "
            "fator de correção não é estimado.")

    principal_corrigido = _q(principal_pos_ipcae * fator_selic)
    memoria.append(
        f"5. Fase SELIC (do ajuizamento {data_ajuizamento.isoformat()} ao cálculo "
        f"{data_calculo.isoformat()}, ADC 58 — a Selic engloba correção e juros): "
        f"fator {fator_selic} ({meses_selic} mês(es), fonte: {fonte_selic}) × "
        f"{_moeda(principal_pos_ipcae)} = principal corrigido "
        f"{_moeda(principal_corrigido)}.")

    # ── Honorários sucumbenciais sobre o principal corrigido ──────────────────
    honorarios = _q(principal_corrigido * pct_hon / Decimal("100"))
    if pct_hon != 0 and (pct_hon < _HON_MIN or pct_hon > _HON_MAX):
        alertas.append(
            f"Percentual de honorários ({pct_hon}%) fora da faixa legal de 5% a "
            "15% (CLT art. 791-A). Confirme o percentual arbitrado na sentença.")
    memoria.append(
        f"6. Honorários sucumbenciais = {pct_hon}% × principal corrigido "
        f"({_moeda(principal_corrigido)}) = {_moeda(honorarios)} "
        "(CLT art. 791-A — 5% a 15%).")

    # ── INSS / IRRF: base destacada, valor "a apurar" (tabela do ano) ─────────
    # A base salarial é apresentada em valor nominal E corrigido; o valor exato
    # depende da tabela vigente no ano — não chutamos alíquota.
    base_salarial_corrigida = _q(base_salarial * fator_ipcae * fator_selic) \
        if fator_ipcae is not None else _q(base_salarial * fator_selic)
    inss = {
        "base_calculo": float(base_salarial_corrigida),
        "base_calculo_nominal": float(_q(base_salarial)),
        "valor": None,
        "status": "a_apurar",
        "observacao": (
            "INSS incide sobre as parcelas salariais/tributáveis. Valor NÃO "
            "calculado: aplique a tabela progressiva do INSS vigente no ano-base "
            "(Lei 8.212/91), respeitando o teto e o regime de competências."),
    }
    irrf = {
        "base_calculo": float(base_salarial_corrigida),
        "valor": None,
        "status": "a_apurar",
        "observacao": (
            "IRRF incide sobre os rendimentos tributáveis (deduzido o INSS). "
            "Valor NÃO calculado: aplique a tabela do IRRF vigente e o regime de "
            "rendimentos recebidos acumuladamente (RRA), quando cabível."),
    }
    alertas.append(
        "INSS e IRRF marcados como 'a apurar': as tabelas mudam por ano — "
        "aplique a vigente sobre a base salarial destacada antes de fechar o "
        "líquido.")
    memoria.append(
        f"7. INSS/IRRF: base salarial destacada {_moeda(base_salarial_corrigida)} "
        "(corrigida) — valor 'a apurar' pela tabela do ano (não estimado).")

    # ── Totais ────────────────────────────────────────────────────────────────
    subtotal_credito = _q(principal_corrigido + fgts + multa_fgts)
    total_bruto_com_honorarios = _q(subtotal_credito + honorarios)
    total_liquido_estimado = subtotal_credito  # antes das deduções "a apurar"
    memoria.append(
        f"8. Subtotal do crédito trabalhista = principal corrigido "
        f"{_moeda(principal_corrigido)} + FGTS {_moeda(fgts)} + multa "
        f"{_moeda(multa_fgts)} = {_moeda(subtotal_credito)}.")
    memoria.append(
        f"9. Total bruto com honorários sucumbenciais = "
        f"{_moeda(total_bruto_com_honorarios)}. Líquido estimado ao reclamante "
        f"= {_moeda(total_liquido_estimado)} ANTES das deduções de INSS/IRRF "
        "('a apurar').")

    return {
        "data_ajuizamento": data_ajuizamento.isoformat(),
        "data_calculo": data_calculo.isoformat(),
        "verbas": verbas_norm,
        "principal_bruto": float(_q(principal_bruto)),
        "base_salarial": float(_q(base_salarial)),
        "base_indenizatoria": float(_q(base_indenizatoria)),
        "fgts": {
            "aliquota_pct": 8.0, "base": float(_q(base_salarial)),
            "valor": float(fgts),
            "base_legal": "Lei 8.036/90, art. 15; Súmula 462/TST",
        },
        "multa_fgts": {
            "aliquota_pct": 40.0, "base": float(fgts), "valor": float(multa_fgts),
            "base_legal": "Lei 8.036/90, art. 18, §1º",
        },
        "correcao": {
            "regime": "ADC 58/59 STF — IPCA-E até o ajuizamento; SELIC "
                      "(engloba correção e juros) a partir do ajuizamento",
            "fator_ipcae_pre_ajuizamento": (float(fator_ipcae)
                                            if fator_ipcae is not None else None),
            "principal_pos_ipcae": float(principal_pos_ipcae),
            "fator_selic": float(fator_selic),
            "fonte_selic": fonte_selic,
            "meses_selic": meses_selic,
            "principal_corrigido": float(principal_corrigido),
        },
        "honorarios": {
            "percentual_pct": float(pct_hon),
            "base": float(principal_corrigido), "valor": float(honorarios),
            "base_legal": "CLT art. 791-A (Lei 13.467/2017) — 5% a 15%",
        },
        "inss": inss,
        "irrf": irrf,
        "subtotal_credito_trabalhista": float(subtotal_credito),
        "total_bruto_com_honorarios": float(total_bruto_com_honorarios),
        "total_liquido_estimado": float(total_liquido_estimado),
        "memoria_calculo": memoria,
        "alertas": alertas,
        "base_legal": BASE_LEGAL,
        "aviso_hitl": AVISO_HITL,
    }
