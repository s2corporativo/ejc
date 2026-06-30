"""
Constantes legais centralizadas — 2026.
Ponto único de atualização para valores monetários legais.
Fonte: Portaria MPS/MF, tabelas INSS/IRRF vigentes e consolidação CLT.
"""
from __future__ import annotations

from decimal import Decimal

# ── Salário Mínimo ────────────────────────────────────────────────────────────
SM_2026 = Decimal("1518.00")           # MP 1.294/2025, vigência jan/2026
SM_HORA = (SM_2026 / 220).quantize(Decimal("0.01"))   # 220h mensais (CLT art. 58)
SM_DIA = (SM_2026 / 30).quantize(Decimal("0.01"))

# ── INSS 2026 — Tabela de contribuição (empregado) ────────────────────────────
# Portaria MPS/MF 2025 — alíquotas progressivas (Emenda 103/2019)
INSS_FAIXAS_2026: list[tuple[Decimal, Decimal]] = [
    (Decimal("1518.00"),  Decimal("0.075")),   # até 1 SM
    (Decimal("2793.88"),  Decimal("0.09")),
    (Decimal("4190.83"),  Decimal("0.12")),
    (Decimal("8157.41"),  Decimal("0.14")),
    (None,                Decimal("0.14")),    # teto — contribuição máxima
]
INSS_TETO_2026 = Decimal("8157.41")
INSS_MAX_2026 = Decimal("908.86")              # contribuição máxima mensal

# ── IRRF 2026 — Tabela progressiva mensal ─────────────────────────────────────
# Lei 14.848/2024 — vigência 2026
IRRF_FAIXAS_2026: list[tuple[Decimal | None, Decimal, Decimal]] = [
    (Decimal("2259.20"),  Decimal("0"),      Decimal("0")),       # isento
    (Decimal("2826.65"),  Decimal("0.075"),  Decimal("169.44")),
    (Decimal("3751.05"),  Decimal("0.15"),   Decimal("381.44")),
    (Decimal("4664.68"),  Decimal("0.225"),  Decimal("662.77")),
    (None,                Decimal("0.275"),  Decimal("896.00")),  # acima
]
IRRF_DEDUCAO_DEPENDENTE_2026 = Decimal("189.59")  # por dependente

# ── Limites trabalhistas TST/CLT ──────────────────────────────────────────────
TETO_DANO_MORAL_CLT = SM_2026 * 50             # CLT art. 223-G, §1°, IV (teto)
LIMITE_INDENIZACAO_DISPENSA = SM_2026 * 40 * Decimal("1.4")  # FGTS + 40% multa
HORAS_EXTRAS_PERCENTUAL_MIN = Decimal("0.50")  # CLT art. 59 — mínimo 50%
HORAS_EXTRAS_DOMINICAL_MIN = Decimal("1.00")   # CLT art. 67 — 100% no repouso

# ── FGTS ──────────────────────────────────────────────────────────────────────
FGTS_ALIQUOTA = Decimal("0.08")                # 8% sobre remuneração (CLT art. 15)
FGTS_MULTA_DISPENSA_SEM_JUSTA = Decimal("0.40")  # 40% do saldo (Lei 8.036/90)

# ── Rescisão — datas e cálculos ───────────────────────────────────────────────
AVISO_PREVIO_BASE_DIAS = 30                    # CLT art. 487
AVISO_PREVIO_ADICIONAL_ANO = 3                 # Lei 12.506/2011 — 3d/ano completo
AVISO_PREVIO_MAXIMO_DIAS = 90                  # teto Lei 12.506/2011

# ── Utilidades ────────────────────────────────────────────────────────────────

def calcular_aviso_previo(anos_servico: int) -> int:
    """Retorna dias de aviso prévio proporcional (Lei 12.506/2011)."""
    dias = AVISO_PREVIO_BASE_DIAS + (anos_servico * AVISO_PREVIO_ADICIONAL_ANO)
    return min(dias, AVISO_PREVIO_MAXIMO_DIAS)


def calcular_inss(salario_bruto: Decimal) -> Decimal:
    """Calcula contribuição INSS empregado (progressiva, 2026)."""
    total = Decimal("0")
    anterior = Decimal("0")
    for teto, aliquota in INSS_FAIXAS_2026:
        limite = teto if teto is not None else salario_bruto
        base = min(salario_bruto, limite) - anterior
        if base <= 0:
            break
        total += base * aliquota
        anterior = limite
        if teto is None or salario_bruto <= teto:
            break
    return min(total, INSS_MAX_2026).quantize(Decimal("0.01"))


def calcular_irrf(base_calculo: Decimal, num_dependentes: int = 0) -> Decimal:
    """Calcula IRRF mensal (tabela progressiva 2026)."""
    base = base_calculo - (IRRF_DEDUCAO_DEPENDENTE_2026 * num_dependentes)
    for teto, aliquota, deducao in IRRF_FAIXAS_2026:
        if teto is None or base <= teto:
            resultado = (base * aliquota) - deducao
            return max(resultado, Decimal("0")).quantize(Decimal("0.01"))
    return Decimal("0")
