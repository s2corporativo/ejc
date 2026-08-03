# ── app/services/calc/custas_tjmg.py ─────────────────────────────────────────
# Custas judiciais e Taxa Judiciária do TJMG (1ª instância) — exercício 2026.
#
# ⚠️ INTEGRIDADE DE DADOS: os valores abaixo foram transcritos da tabela
# OFICIAL do TJMG ("Tabela de Custas e Taxa Judiciária — Primeira Instância —
# Ano 2026", Corregedoria-Geral de Justiça/SEPLAN-CEJUR), que consolida o
# Anexo I da Lei estadual 14.939/2003 (custas) e a Tabela J da Lei 6.763/75
# (Taxa Judiciária), atualizados pela UFEMG do exercício.
#
# Fonte oficial (PDF, portal TJMG):
#   https://www.tjmg.jus.br/lumis/portal/file/fileDownload.jsp?fileId=8ACC80D09B101BA1019B46A0005B01E9
#   (página "Custas/Emolumentos" → Tabela de Custas e Taxa Judiciária 1ª
#   Instância/2026). Vigência: ano 2026.
#
# Regras de transcrição:
#   • Cada faixa guarda (de, até, custas, taxa, total) EXATAMENTE como
#     impressos na tabela oficial — inclusive quando custas+taxa difere do
#     total impresso por R$ 0,01 (arredondamento da própria tabela, que parte
#     de valores em UFEMG). Nenhum valor é recalculado aqui.
#   • Grupos 4 e 5 (precatórias e criminal) usam RUBRICAS FIXAS por histórico,
#     não faixas por valor da causa; ficam fora desta calculadora (fail-closed)
#     até carga própria conferida — a extração automática do PDF não permitiu
#     associar rótulo↔valor com certeza, e chutar mapeamento é inaceitável.
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException

VIGENCIA = "2026"
FONTE = (
    "Portal TJMG — Tabela de Custas e Taxa Judiciária, 1ª Instância, Ano 2026 "
    "(Anexo I da Lei estadual 14.939/2003 + Tabela J da Lei 6.763/75)"
)
FONTE_URL = (
    "https://www.tjmg.jus.br/lumis/portal/file/fileDownload.jsp"
    "?fileId=8ACC80D09B101BA1019B46A0005B01E9"
)

UFEMG_2026 = Decimal("5.7899")        # fonte: Tabela TJMG 2026
ISENCAO_TAXA_UFEMG = Decimal("25000")  # art. 10, Lei 14.941/2003 / Tabela
ISENCAO_TAXA_REAIS = (UFEMG_2026 * ISENCAO_TAXA_UFEMG).quantize(Decimal("0.01"))  # 144.747,50

_CENT = Decimal("0.01")


def _d(v: str) -> Decimal:
    return Decimal(v)


# Faixa: (de, ate | None p/ "acima de", custas, taxa_judiciaria, total_impresso)
_FAIXAS_GRUPO_1: list[tuple] = [
    (_d("0.00"), _d("46356.26"), _d("463.19"), _d("167.91"), _d("631.10")),
    (_d("46356.27"), _d("60724.47"), _d("602.15"), _d("167.91"), _d("770.06")),
    (_d("60724.48"), _d("81122.29"), _d("602.15"), _d("497.93"), _d("1100.08")),
    (_d("81122.30"), _d("139068.82"), _d("602.15"), _d("1053.76"), _d("1655.91")),
    (_d("139068.83"), _d("242909.46"), _d("926.38"), _d("1053.76"), _d("1980.15")),
    (_d("242909.47"), _d("463562.84"), _d("926.38"), _d("2223.32"), _d("3149.71")),
    (_d("463562.85"), _d("566472.24"), _d("1389.58"), _d("2223.32"), _d("3612.90")),
    (_d("566472.25"), _d("927125.69"), _d("1389.58"), _d("4701.40"), _d("6090.97")),
    (_d("927125.70"), _d("1213609.36"), _d("2084.36"), _d("4701.40"), _d("6785.76")),
    (_d("1213609.37"), _d("2317814.22"), _d("2084.36"), _d("8383.78"), _d("10468.14")),
    (_d("2317814.23"), _d("2427676.12"), _d("3010.75"), _d("8383.78"), _d("11394.52")),
    (_d("2427676.13"), _d("4045976.33"), _d("3010.75"), _d("13015.70"), _d("16026.44")),
    (_d("4045976.34"), None, _d("3010.75"), _d("17630.25"), _d("20640.99")),
]

_FAIXAS_GRUPO_2: list[tuple] = [
    (_d("0.00"), _d("46356.26"), _d("231.60"), _d("92.64"), _d("324.23")),
    (_d("46356.27"), _d("60724.47"), _d("324.23"), _d("92.64"), _d("416.87")),
    (_d("60724.48"), _d("81122.29"), _d("324.23"), _d("295.28"), _d("619.52")),
    (_d("81122.30"), _d("139068.82"), _d("324.23"), _d("665.84"), _d("990.07")),
    (_d("139068.83"), _d("242909.46"), _d("463.19"), _d("665.84"), _d("1129.03")),
    (_d("242909.47"), _d("463562.84"), _d("463.19"), _d("1406.95"), _d("1870.14")),
    (_d("463562.85"), _d("566472.24"), _d("694.79"), _d("1406.95"), _d("2101.73")),
    (_d("566472.25"), _d("927125.69"), _d("694.79"), _d("3039.70"), _d("3734.49")),
    (_d("927125.70"), _d("1213609.36"), _d("926.38"), _d("3039.70"), _d("3966.08")),
    (_d("1213609.37"), _d("2317814.22"), _d("926.38"), _d("5373.03"), _d("6299.41")),
    (_d("2317814.23"), _d("2427676.12"), _d("1157.98"), _d("5373.03"), _d("6531.01")),
    (_d("2427676.13"), _d("4045976.33"), _d("1157.98"), _d("8534.31"), _d("9692.29")),
    (_d("4045976.34"), None, _d("1157.98"), _d("11128.19"), _d("12286.17")),
]

_FAIXAS_GRUPO_3: list[tuple] = [
    (_d("0.00"), _d("60724.47"), _d("0.00"), _d("92.64"), _d("92.64")),
    (_d("60724.48"), _d("81122.29"), _d("0.00"), _d("295.28"), _d("295.28")),
    (_d("81122.30"), _d("144747.55"), _d("0.00"), _d("665.84"), _d("665.84")),
    (_d("144747.56"), _d("242909.46"), _d("324.23"), _d("665.84"), _d("990.07")),
    (_d("242909.47"), _d("324493.96"), _d("324.23"), _d("1406.95"), _d("1731.18")),
    (_d("324493.97"), _d("566472.24"), _d("463.19"), _d("1406.95"), _d("1870.14")),
    (_d("566472.25"), _d("602631.67"), _d("463.19"), _d("3039.70"), _d("3502.89")),
    (_d("602631.68"), _d("927125.69"), _d("694.79"), _d("3039.70"), _d("3734.49")),
    (_d("927125.70"), _d("1213609.36"), _d("926.38"), _d("3039.70"), _d("3966.08")),
    (_d("1213609.37"), _d("1854251.37"), _d("926.38"), _d("5373.03"), _d("6299.41")),
    (_d("1854251.38"), _d("2317814.22"), _d("1157.98"), _d("5373.03"), _d("6531.01")),
    (_d("2317814.23"), _d("2427676.12"), _d("2315.96"), _d("5373.03"), _d("7688.99")),
    (_d("2427676.13"), _d("4045976.33"), _d("2315.96"), _d("8534.31"), _d("10850.27")),
    (_d("4045976.34"), None, _d("2315.96"), _d("11128.19"), _d("13444.15")),
]

# Grupos 6 (cautelar/jurisdição voluntária) e 7 (mandado de segurança) têm a
# MESMA tabela de faixas na publicação oficial de 2026.
_FAIXAS_GRUPOS_6_7: list[tuple] = [
    (_d("0.00"), _d("46356.26"), _d("231.60"), _d("115.80"), _d("347.39")),
    (_d("46356.27"), _d("60724.47"), _d("324.23"), _d("115.80"), _d("440.03")),
    (_d("60724.48"), _d("81122.29"), _d("324.23"), _d("370.55"), _d("694.79")),
    (_d("81122.30"), _d("139068.82"), _d("324.23"), _d("833.75"), _d("1157.98")),
    (_d("139068.83"), _d("242909.46"), _d("463.19"), _d("833.75"), _d("1296.94")),
    (_d("242909.47"), _d("463562.84"), _d("463.19"), _d("1760.13"), _d("2223.32")),
    (_d("463562.85"), _d("566472.24"), _d("694.79"), _d("1760.13"), _d("2454.92")),
    (_d("566472.25"), _d("927125.69"), _d("694.79"), _d("3798.17"), _d("4492.96")),
    (_d("927125.70"), _d("1213609.36"), _d("926.38"), _d("3798.17"), _d("4724.56")),
    (_d("1213609.37"), _d("2317814.22"), _d("926.38"), _d("6716.28"), _d("7642.67")),
    (_d("2317814.23"), _d("2427676.12"), _d("1157.98"), _d("6716.28"), _d("7874.26")),
    (_d("2427676.13"), _d("4045976.33"), _d("1157.98"), _d("10665.00"), _d("11822.98")),
    (_d("4045976.34"), None, _d("1157.98"), _d("13907.34"), _d("15065.32")),
]

# Valor inestimável: (custas, taxa, total) impressos por grupo.
GRUPOS: dict[int, dict] = {
    1: {
        "descricao": (
            "Vara Cível, Vara de Fazenda Pública, Vara de Falência e "
            "Concordata e Vara de Registros Públicos"
        ),
        "faixas": _FAIXAS_GRUPO_1,
        "inestimavel": (_d("370.55"), _d("167.91"), _d("538.46")),
    },
    2: {
        "descricao": (
            "Vara de Família, Vara de Conflitos Agrários e Juizados Especiais "
            "Cíveis (inclusive Juizado da Fazenda Pública, quando for o caso)"
        ),
        "faixas": _FAIXAS_GRUPO_2,
        "inestimavel": (_d("231.60"), _d("92.64"), _d("324.23")),
    },
    3: {
        "descricao": "Vara de Sucessões (inventário/arrolamento)",
        "faixas": _FAIXAS_GRUPO_3,
        "inestimavel": None,  # a tabela oficial do Grupo 3 não traz linha própria
    },
    6: {
        "descricao": "Processo cautelar e procedimento de jurisdição voluntária",
        "faixas": _FAIXAS_GRUPOS_6_7,
        "inestimavel": (_d("231.60"), _d("115.80"), _d("347.39")),
    },
    7: {
        "descricao": "Mandado de Segurança (1º impetrante)",
        "faixas": _FAIXAS_GRUPOS_6_7,
        "inestimavel": (_d("231.60"), _d("115.80"), _d("347.39")),
        "observacao": (
            "Segundo impetrante e seguintes (cada um): custas R$ 28,95 + taxa "
            "R$ 57,90 = R$ 86,85. Taxa judiciária devida ao final se o MS for "
            "denegado (Lei 6.763/75 art. 107, II, f; Prov. Conj. 75/2018 art. 10, III)."
        ),
    },
}

#: Grupos publicados na tabela oficial mas NÃO carregados aqui (rubricas fixas
#: por histórico; carga exige conferência manual rótulo↔valor).
GRUPOS_NAO_CARREGADOS: dict[int, str] = {
    4: "Precatórias cíveis e criminais (rubricas fixas por histórico)",
    5: "Vara Criminal e Execuções Criminais (rubricas fixas por histórico)",
}

# Alvará autônomo da Lei 6.858/80 (isenção do art. 8º, III, Lei 14.939/2003
# até 25.000 UFEMG): acima do limite, valores impressos na tabela oficial.
ALVARA_LEI_6858 = {
    "isento_ate": ISENCAO_TAXA_REAIS,
    "acima": (_d("231.60"), _d("167.91"), _d("399.50")),
}

# Compat: consumidores antigos checavam esta lista para saber se a tabela foi
# carregada; hoje ela espelha o Grupo 1 no formato legado (ate, custas).
FAIXAS_CUSTAS: list[tuple] = [(ate, custas) for (_de, ate, custas, _t, _tot) in _FAIXAS_GRUPO_1]
TABELA_OFICIAL_CARREGADA = bool(FAIXAS_CUSTAS)


def ufemg_para_reais(qtd_ufemg: float | Decimal, ufemg: Decimal = UFEMG_2026) -> float:
    """Converte um valor em UFEMG para reais (vigência 2026)."""
    return float((Decimal(str(qtd_ufemg)) * ufemg).quantize(_CENT, ROUND_HALF_UP))


def reais_para_ufemg(valor_reais: float | Decimal, ufemg: Decimal = UFEMG_2026) -> float:
    """Converte reais para UFEMG (vigência 2026)."""
    return float((Decimal(str(valor_reais)) / ufemg).quantize(Decimal("0.0001"), ROUND_HALF_UP))


def analisar(valor_causa: float | Decimal, grupo: int = 1) -> dict:
    """Custas iniciais + Taxa Judiciária TJMG por valor da causa e grupo.

    `grupo` segue a tabela oficial: 1 cível/fazenda, 2 família/JEC,
    3 sucessões, 6 cautelar/jurisdição voluntária, 7 mandado de segurança.
    Grupos 4/5 (rubricas fixas) respondem 503 fail-closed até carga própria.
    """
    if grupo in GRUPOS_NAO_CARREGADOS:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Grupo {grupo} ({GRUPOS_NAO_CARREGADOS[grupo]}) usa rubricas "
                "fixas por histórico e ainda não foi carregado — consulte a "
                "tabela oficial do TJMG."
            ),
        )
    if grupo not in GRUPOS:
        raise HTTPException(
            status_code=422,
            detail=f"Grupo inválido: {grupo}. Aceitos: {sorted(GRUPOS)} "
                   f"(não carregados: {sorted(GRUPOS_NAO_CARREGADOS)}).",
        )

    g = GRUPOS[grupo]
    vc = Decimal(str(valor_causa))
    em_ufemg = (vc / UFEMG_2026).quantize(Decimal("0.01"))
    isento_taxa = vc <= ISENCAO_TAXA_REAIS

    faixa_aplicada = None
    for de, ate, custas, taxa, total in g["faixas"]:
        if ate is None or vc <= ate:
            faixa_aplicada = {
                "de": float(de),
                "ate": float(ate) if ate is not None else None,
                "custas_iniciais": float(custas),
                "taxa_judiciaria": float(taxa),
                "total_a_recolher": float(total),
            }
            break

    resultado = {
        "valor_causa": float(vc),
        "grupo": grupo,
        "grupo_descricao": g["descricao"],
        "ufemg_2026": float(UFEMG_2026),
        "valor_causa_em_ufemg": float(em_ufemg),
        "faixa": faixa_aplicada,
        "custas_iniciais": faixa_aplicada["custas_iniciais"] if faixa_aplicada else None,
        "taxa_judiciaria": faixa_aplicada["taxa_judiciaria"] if faixa_aplicada else None,
        "total_a_recolher": faixa_aplicada["total_a_recolher"] if faixa_aplicada else None,
        "isencao_taxa_judiciaria": {
            "limite_ufemg": float(ISENCAO_TAXA_UFEMG),
            "limite_reais": float(ISENCAO_TAXA_REAIS),
            "isento": isento_taxa,
            "base_legal": (
                "Isenção de 25.000 UFEMG — aplicável nas hipóteses legais "
                "(ex.: alvará da Lei 6.858/80, art. 8º, III, Lei 14.939/2003); "
                "a tabela do grupo prevalece quando cobrar taxa na faixa."
            ),
        },
        "vigencia": VIGENCIA,
        "fonte": FONTE,
        "fonte_url": FONTE_URL,
        "avisos": [
            "MINUTA (HITL) — conferir e emitir a guia no sistema oficial do "
            "TJMG (Guias na Web/eproc) antes de qualquer recolhimento.",
            "Vale o valor VIGENTE na data do efetivo pagamento (observação "
            "geral da tabela oficial 2026).",
            "Incluir a verba indenizatória do Oficial de Justiça (Tabela D) "
            "quando houver, e demais despesas (Tabelas C, E, F e G) conforme o ato.",
        ],
    }
    if g.get("observacao"):
        resultado["observacao_grupo"] = g["observacao"]
    if g.get("inestimavel"):
        c, t, tot = g["inestimavel"]
        resultado["valor_inestimavel"] = {
            "custas_iniciais": float(c),
            "taxa_judiciaria": float(t),
            "total_a_recolher": float(tot),
        }
    return resultado
