# ── app/services/calc/custas_tjmg.py ─────────────────────────────────────────
# Custas judiciais e Taxa Judiciária do TJMG (1ª instância).
#
# ⚠️ INTEGRIDADE DE DADOS: as custas iniciais seguem as FAIXAS do Anexo I da
# Lei estadual 14.939/2003 e a Taxa Judiciária segue a Tabela J da Lei 6.763/75
# (Decreto 38.886/97) — ambas TABELAS ESCALONADAS, atualizadas anualmente por
# UFEMG. Os valores exatos das faixas NÃO estão embutidos aqui para não correr
# risco de imprecisão. Esta estrutura entrega os primitivos VERIFICADOS e um
# ponto único para carga da tabela oficial (preencher `FAIXAS_CUSTAS` a partir
# do PDF oficial do TJMG do exercício).
#
# Valores conferidos (fonte: Portal TJMG, Tabela de Custas 1ª Instância/2026):
#   • UFEMG 2026 = R$ 5,7899
#   • Isenção da Taxa Judiciária: valor da causa ≤ 25.000 UFEMG = R$ 144.747,50
from __future__ import annotations

from fastapi import HTTPException
from decimal import Decimal, ROUND_HALF_UP

UFEMG_2026 = Decimal("5.7899")        # fonte: Tabela TJMG 2026
ISENCAO_TAXA_UFEMG = Decimal("25000")  # art. 10, Lei 14.941/2003 / Tabela
ISENCAO_TAXA_REAIS = (UFEMG_2026 * ISENCAO_TAXA_UFEMG).quantize(Decimal("0.01"))  # 144.747,50

# Faixas oficiais de custas (Anexo I, Lei 14.939/2003) — PENDENTE DE CARGA.
# Formato sugerido quando preenchido com a tabela oficial do exercício:
#   (valor_causa_ate: Decimal | None, custas_reais: Decimal)
FAIXAS_CUSTAS: list[tuple] = []        # ← preencher com a tabela oficial 2026
TABELA_OFICIAL_CARREGADA = bool(FAIXAS_CUSTAS)

_CENT = Decimal("0.01")


def ufemg_para_reais(qtd_ufemg: float | Decimal, ufemg: Decimal = UFEMG_2026) -> float:
    """Converte um valor em UFEMG para reais (vigência 2026)."""
    return float((Decimal(str(qtd_ufemg)) * ufemg).quantize(_CENT, ROUND_HALF_UP))


def reais_para_ufemg(valor_reais: float | Decimal, ufemg: Decimal = UFEMG_2026) -> float:
    """Converte reais para UFEMG (vigência 2026)."""
    return float((Decimal(str(valor_reais)) / ufemg).quantize(Decimal("0.0001"), ROUND_HALF_UP))


def analisar(valor_causa: float | Decimal) -> dict:
    """Analisa custas/taxa judiciária para um valor de causa."""
    if not FAIXAS_CUSTAS:
        raise HTTPException(
            status_code=503,
            detail="Tabela de faixas de custas TJMG não configurada. "
                   "Preencha FAIXAS_CUSTAS conforme Anexo I, Lei 14.939/2003.",
        )
    vc = Decimal(str(valor_causa))
    em_ufemg = (vc / UFEMG_2026).quantize(Decimal("0.01"))
    isento_taxa = vc <= ISENCAO_TAXA_REAIS

    resultado = {
        "valor_causa": float(vc),
        "ufemg_2026": float(UFEMG_2026),
        "valor_causa_em_ufemg": float(em_ufemg),
        "isencao_taxa_judiciaria": {
            "limite_ufemg": float(ISENCAO_TAXA_UFEMG),
            "limite_reais": float(ISENCAO_TAXA_REAIS),
            "isento": isento_taxa,
            "base_legal": "Lei estadual 6.763/75 (Taxa Judiciária) — tabela TJMG",
        },
        "custas_iniciais": None,
        "fonte": "Portal TJMG — Tabela de Custas 1ª Instância/2026",
        "avisos": [
            "MINUTA (HITL) — conferir na guia oficial (Sistema Guias na Web do TJMG).",
            "Custas e despesas seguem faixas do Anexo I da Lei 14.939/2003.",
        ],
    }

    if TABELA_OFICIAL_CARREGADA:
        custas = None
        for limite, valor in FAIXAS_CUSTAS:
            if limite is None or vc <= limite:
                custas = valor
                break
        resultado["custas_iniciais"] = float(custas) if custas is not None else None
    else:
        resultado["tabela_faixas_pendente"] = True
        resultado["avisos"].insert(
            0,
            "TABELA DE FAIXAS DE CUSTAS NÃO CARREGADA — preencher `FAIXAS_CUSTAS` "
            "com a tabela oficial do TJMG (Anexo I, Lei 14.939/2003) do exercício. "
            "Conversão UFEMG e isenção da taxa judiciária abaixo já são valores oficiais.",
        )
    return resultado
