# ── app/services/calc/previdenciario_beneficio.py ────────────────────────────
# Motor determinístico das 5 regras de transição da EC 103/2019 (reforma da
# Previdência) para aposentadoria por tempo de contribuição / idade, + o
# coeficiente da RMI (art. 26). STATELESS, sem IA, sem persistência.
#
# ⚠️ PRINCÍPIO DE HONESTIDADE (é cálculo previdenciário real):
#   • A RMI REAL depende do CNIS (salários de contribuição desde 07/1994). Este
#     motor NÃO inventa a média. Calcula o COEFICIENTE e só devolve a RMI quando
#     o usuário informa `media_salarios`; senão a RMI fica null com observação.
#   • As tabelas de progressão implementadas (pontos +1/ano; idade mínima da
#     regra progressiva +6 meses/ano) são as conhecidas com CERTEZA. Onde o
#     parâmetro de um ano é incerto, NÃO se chuta: clampa-se o que é seguro e
#     emite-se alerta pedindo conferência com a tabela oficial do ano.
#   • O pedágio depende do tempo de contribuição em 13/11/2019 (data da EC).
#     Aqui ele é ESTIMADO a partir do tempo atual e sinalizado para conferência
#     no CNIS — nunca apresentado como número fechado.
#   • Tudo é SIMULAÇÃO DE ELEGIBILIDADE (HITL), não concessão. O INSS analisa o
#     CNIS real.
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from datetime import date
from typing import Optional

_D0 = Decimal("0")
_CENT = Decimal("0.01")
_PCT = Decimal("0.0001")

# Data de promulgação da EC 103/2019 — marco das regras de transição/pedágio.
ANO_REFORMA = 2019

AVISO_HITL = (
    "SIMULAÇÃO DE ELEGIBILIDADE — não é concessão de benefício. A RMI real "
    "depende dos salários de contribuição do CNIS (desde 07/1994); o INSS "
    "analisa o extrato real. Revisão humana obrigatória (HITL). Confira os "
    "parâmetros do ano com a tabela oficial vigente."
)
BASE_LEGAL_GERAL = "EC 103/2019 (Reforma da Previdência); Lei 8.213/91."


# ── Helpers de formatação ─────────────────────────────────────────────────────

def _q_pct(v: Decimal) -> Decimal:
    return v.quantize(_PCT, rounding=ROUND_HALF_UP)


def _q_cent(v: Decimal) -> Decimal:
    return v.quantize(_CENT, rounding=ROUND_HALF_UP)


def _fmt_anos(v: Decimal) -> str:
    """Formata uma quantidade de anos em 'X anos' ou 'X anos e 6 meses'."""
    anos = int(v)
    meses = int((v - anos) * 12 + Decimal("0.0001"))  # tolerância de arredond.
    if meses <= 0:
        return f"{anos} anos"
    return f"{anos} anos e {meses} meses"


# ── Tabelas de progressão (EC 103/2019) ───────────────────────────────────────

def _pontos_exigidos(homem: bool, ano: int) -> tuple[int, bool]:
    """Regra de pontos (art. 15): idade+tempo. H 96(2019)→105(2028);
    F 86(2019)→100(2033), +1 ponto/ano. Retorna (pontos, incerto)."""
    base = 96 if homem else 86
    teto = 105 if homem else 100
    if ano < ANO_REFORMA:
        return base, True  # antes da EC não havia regra de transição
    return min(base + (ano - ANO_REFORMA), teto), False


def _idade_min_progressiva(homem: bool, ano: int) -> tuple[Decimal, bool]:
    """Idade mínima da regra por idade progressiva (art. 16): H 61(2019)→65(2027);
    F 56(2019)→62(2031), +6 meses/ano. Retorna (idade_min, incerto)."""
    base = Decimal("61") if homem else Decimal("56")
    teto = Decimal("65") if homem else Decimal("62")
    if ano < ANO_REFORMA:
        return base, True
    idade = base + Decimal("0.5") * (ano - ANO_REFORMA)
    return min(idade, teto), False


def _idade_min_aposentadoria(homem: bool, ano: int) -> tuple[Decimal, bool]:
    """Idade da aposentadoria por idade (art. 18): H 65 fixo; F 60(2019)→62(2023),
    +6 meses/ano a partir de 2020. Retorna (idade_min, incerto)."""
    if homem:
        return Decimal("65"), False
    if ano < ANO_REFORMA:
        return Decimal("60"), True
    idade = Decimal("60") + Decimal("0.5") * max(0, ano - 2019)
    return min(idade, Decimal("62")), False


# ── Coeficiente da RMI — regra geral EC 103 (art. 26) ─────────────────────────

def coeficiente_ec103(homem: bool, tempo_contribuicao: Decimal) -> Decimal:
    """Coeficiente do salário de benefício (art. 26 EC 103/2019): 60% + 2% por
    ano que EXCEDER 20 anos (homem) / 15 anos (mulher). Contam anos completos.
    Sem teto no coeficiente — a RMI é limitada pelo teto do salário de
    contribuição (não modelado aqui)."""
    limiar = 20 if homem else 15
    anos_completos = int(tempo_contribuicao)  # anos inteiros de contribuição
    excedente = max(0, anos_completos - limiar)
    return _q_pct(Decimal("0.60") + Decimal("0.02") * excedente)


# ── Motor principal ───────────────────────────────────────────────────────────

def simular_aposentadoria(
    sexo: str,
    idade: Decimal,
    tempo_contribuicao: Decimal,
    media_salarios: Optional[Decimal],
    ano: int,
    hoje: Optional[date] = None,
) -> dict:
    """Avalia elegibilidade nas 5 regras de transição da EC 103/2019 e consolida.

    Args:
        sexo: "M" | "F" (case-insensitive; qualquer coisa começando com F = mulher).
        idade: idade atual em anos (Decimal, pode ser fracionária).
        tempo_contribuicao: tempo de contribuição em anos (Decimal).
        media_salarios: média dos salários de contribuição (CNIS). Se None, a
            RMI não é calculada — só o coeficiente.
        ano: ano-base da análise (parâmetros de transição variam por ano).
        hoje: injeção para testes (não usado no cálculo principal; reservado).
    """
    homem = not sexo.strip().upper().startswith("F")
    tempo_min = Decimal("35") if homem else Decimal("30")
    tem_media = media_salarios is not None and media_salarios > _D0

    # Coeficiente geral (art. 26) — mesmo tempo em todas as regras que o adotam.
    coef_geral = coeficiente_ec103(homem, tempo_contribuicao)

    def rmi(coef: Optional[Decimal]) -> Optional[Decimal]:
        if coef is None or not tem_media:
            return None
        return _q_cent(media_salarios * coef)

    regras: list[dict] = []

    # ── 1. Pontos (art. 15) ───────────────────────────────────────────────────
    pts_exig, pts_incerto = _pontos_exigidos(homem, ano)
    pontos = idade + tempo_contribuicao
    falta1: list[str] = []
    obs1: list[str] = []
    if pontos < pts_exig:
        falta1.append(f"faltam {pts_exig - pontos} pontos (soma idade+tempo)")
    if tempo_contribuicao < tempo_min:
        falta1.append(f"faltam {_fmt_anos(tempo_min - tempo_contribuicao)} "
                      "de tempo de contribuição")
    if pts_incerto:
        obs1.append("Ano fora da vigência da EC 103/2019 (a partir de 2019) — "
                    "pontuação-base não confirmada; confira a tabela oficial.")
    obs1.append(f"Pontuação exigida em {ano}: {pts_exig} (sobe 1 ponto/ano).")
    eleg1 = not falta1
    regras.append({
        "regra_id": "pontos", "nome": "Regra de transição por pontos",
        "base_legal": "EC 103/2019, art. 15",
        "elegivel": eleg1, "o_que_falta": falta1,
        "coeficiente_rmi": coef_geral, "rmi_estimada": rmi(coef_geral),
        "observacoes": obs1,
        "_deficit": max(_D0, pts_exig - pontos) + max(_D0, tempo_min - tempo_contribuicao),
    })

    # ── 2. Idade progressiva (art. 16) ────────────────────────────────────────
    idade_min2, idade2_incerto = _idade_min_progressiva(homem, ano)
    falta2: list[str] = []
    obs2: list[str] = []
    if idade < idade_min2:
        falta2.append(f"faltam {_fmt_anos(idade_min2 - idade)} de idade "
                      f"(mínima {_fmt_anos(idade_min2)})")
    if tempo_contribuicao < tempo_min:
        falta2.append(f"faltam {_fmt_anos(tempo_min - tempo_contribuicao)} "
                      "de tempo de contribuição")
    if idade2_incerto:
        obs2.append("Ano fora da vigência da EC 103/2019 — idade mínima-base não "
                    "confirmada; confira a tabela oficial.")
    obs2.append(f"Idade mínima em {ano}: {_fmt_anos(idade_min2)} "
                "(sobe 6 meses/ano).")
    eleg2 = not falta2
    regras.append({
        "regra_id": "idade_progressiva",
        "nome": "Regra de transição por idade progressiva",
        "base_legal": "EC 103/2019, art. 16",
        "elegivel": eleg2, "o_que_falta": falta2,
        "coeficiente_rmi": coef_geral, "rmi_estimada": rmi(coef_geral),
        "observacoes": obs2,
        "_deficit": max(_D0, idade_min2 - idade) + max(_D0, tempo_min - tempo_contribuicao),
    })

    # ── Tempo de contribuição em 13/11/2019 (ESTIMADO p/ pedágios) ────────────
    # O pedágio depende do tempo na data da EC. Estimamos assumindo contribuição
    # contínua entre 13/11/2019 e o ano-base. É uma ESTIMATIVA sinalizada.
    anos_desde_reforma = max(0, ano - ANO_REFORMA)
    tempo_em_2019 = tempo_contribuicao - anos_desde_reforma
    if tempo_em_2019 < _D0:
        tempo_em_2019 = _D0
    faltava_em_2019 = max(_D0, tempo_min - tempo_em_2019)
    obs_pedagio_base = (
        f"Tempo em 13/11/2019 ESTIMADO em {_fmt_anos(tempo_em_2019)} "
        "(assume contribuição contínua desde a reforma) — CONFIRA no CNIS, pois "
        "o pedágio depende do tempo exato naquela data."
    )

    # ── 3. Pedágio 50% (art. 17) ──────────────────────────────────────────────
    # Só para quem em 13/11/2019 estava a ≤2 anos do tempo mínimo. Exige tempo
    # mínimo + 50% do que faltava. Sem idade mínima. A RMI usa o FATOR
    # PREVIDENCIÁRIO (expectativa de sobrevida IBGE) — não calculado aqui.
    pode_pedagio50 = tempo_em_2019 >= (tempo_min - 2)
    tempo_exig_p50 = tempo_min + _q_cent(faltava_em_2019 * Decimal("0.5"))
    falta3: list[str] = []
    obs3: list[str] = [obs_pedagio_base]
    if not pode_pedagio50:
        falta3.append("em 13/11/2019 faltava mais de 2 anos para o tempo mínimo "
                      "(regra do pedágio 50% indisponível)")
    if tempo_contribuicao < tempo_exig_p50:
        falta3.append(f"faltam {_fmt_anos(tempo_exig_p50 - tempo_contribuicao)} "
                      f"de tempo (exigido {_fmt_anos(tempo_exig_p50)} = mínimo + "
                      "50% do pedágio)")
    obs3.append("RMI = salário de benefício × FATOR PREVIDENCIÁRIO — depende da "
                "expectativa de sobrevida (tábua IBGE); coeficiente não estimado "
                "aqui para não induzir a erro.")
    eleg3 = not falta3
    regras.append({
        "regra_id": "pedagio_50",
        "nome": "Regra de transição do pedágio de 50%",
        "base_legal": "EC 103/2019, art. 17",
        "elegivel": eleg3, "o_que_falta": falta3,
        "coeficiente_rmi": None, "rmi_estimada": None,  # honesto: depende do fator
        "observacoes": obs3,
        "_deficit": (max(_D0, tempo_exig_p50 - tempo_contribuicao)
                     + (Decimal("99") if not pode_pedagio50 else _D0)),
    })

    # ── 4. Pedágio 100% (art. 20) ─────────────────────────────────────────────
    # Idade mínima H 60 / F 57 + tempo mínimo + 100% do que faltava em 2019.
    # A RMI é INTEGRAL: 100% do salário de benefício (sem coeficiente reduzido).
    idade_min_p100 = Decimal("60") if homem else Decimal("57")
    tempo_exig_p100 = tempo_min + faltava_em_2019  # 100% do pedágio
    falta4: list[str] = []
    obs4: list[str] = [obs_pedagio_base]
    if idade < idade_min_p100:
        falta4.append(f"faltam {_fmt_anos(idade_min_p100 - idade)} de idade "
                      f"(mínima {_fmt_anos(idade_min_p100)})")
    if tempo_contribuicao < tempo_exig_p100:
        falta4.append(f"faltam {_fmt_anos(tempo_exig_p100 - tempo_contribuicao)} "
                      f"de tempo (exigido {_fmt_anos(tempo_exig_p100)} = mínimo + "
                      "100% do pedágio)")
    coef_p100 = Decimal("1.00")  # RMI integral do salário de benefício (art. 20)
    obs4.append("RMI INTEGRAL: 100% do salário de benefício (média), sem o "
                "coeficiente reduzido do art. 26.")
    eleg4 = not falta4
    regras.append({
        "regra_id": "pedagio_100",
        "nome": "Regra de transição do pedágio de 100%",
        "base_legal": "EC 103/2019, art. 20",
        "elegivel": eleg4, "o_que_falta": falta4,
        "coeficiente_rmi": coef_p100, "rmi_estimada": rmi(coef_p100),
        "observacoes": obs4,
        "_deficit": max(_D0, idade_min_p100 - idade) + max(_D0, tempo_exig_p100 - tempo_contribuicao),
    })

    # ── 5. Aposentadoria por idade (art. 18) ──────────────────────────────────
    idade_min5, idade5_incerto = _idade_min_aposentadoria(homem, ano)
    carencia_anos = Decimal("15")  # 180 meses de carência
    falta5: list[str] = []
    obs5: list[str] = []
    if idade < idade_min5:
        falta5.append(f"faltam {_fmt_anos(idade_min5 - idade)} de idade "
                      f"(mínima {_fmt_anos(idade_min5)})")
    if tempo_contribuicao < carencia_anos:
        falta5.append(f"faltam {_fmt_anos(carencia_anos - tempo_contribuicao)} "
                      "para a carência de 15 anos")
    if idade5_incerto:
        obs5.append("Ano fora da vigência da EC 103/2019 — idade mínima-base "
                    "feminina não confirmada; confira a tabela oficial.")
    obs5.append(f"Idade mínima em {ano}: {_fmt_anos(idade_min5)}; carência de 15 "
                "anos (180 contribuições). Coeficiente pelo art. 26.")
    eleg5 = not falta5
    regras.append({
        "regra_id": "idade",
        "nome": "Aposentadoria por idade",
        "base_legal": "EC 103/2019, art. 18; Lei 8.213/91, art. 25 II",
        "elegivel": eleg5, "o_que_falta": falta5,
        "coeficiente_rmi": coef_geral, "rmi_estimada": rmi(coef_geral),
        "observacoes": obs5,
        "_deficit": max(_D0, idade_min5 - idade) + max(_D0, carencia_anos - tempo_contribuicao),
    })

    # ── Consolidação ──────────────────────────────────────────────────────────
    elegiveis = [r for r in regras if r["elegivel"]]
    ids_elegiveis = [r["regra_id"] for r in elegiveis]

    melhor = _escolher_melhor(regras, elegiveis)

    # Remove a chave interna de seleção antes de devolver.
    for r in regras:
        r.pop("_deficit", None)

    return {
        "sexo": "masculino" if homem else "feminino",
        "idade": idade, "tempo_contribuicao": tempo_contribuicao, "ano": ano,
        "media_informada": tem_media,
        "media_salarios_contribuicao": media_salarios if tem_media else None,
        "regras": regras,
        "regras_elegiveis": ids_elegiveis,
        "melhor_regra": melhor,
        "aviso_hitl": AVISO_HITL,
        "base_legal_geral": BASE_LEGAL_GERAL,
    }


def _escolher_melhor(regras: list[dict], elegiveis: list[dict]) -> dict:
    """Melhor regra: entre as ELEGÍVEIS, a de maior coeficiente/RMI. Se todas as
    elegíveis têm coeficiente indeterminado (só pedágio 50%), aponta-a com a
    ressalva. Se nenhuma é elegível, indica a MAIS PRÓXIMA (menor déficit)."""
    if elegiveis:
        com_coef = [r for r in elegiveis if r["coeficiente_rmi"] is not None]
        if com_coef:
            melhor = max(com_coef, key=lambda r: r["coeficiente_rmi"])
            pct = _q_pct(melhor["coeficiente_rmi"] * 100)
            return {
                "id": melhor["regra_id"],
                "motivo": f"maior coeficiente da RMI ({pct}%) entre as regras "
                          "elegíveis.",
            }
        # Só regra(s) elegível(is) com coeficiente indeterminado (fator prev.).
        melhor = elegiveis[0]
        return {
            "id": melhor["regra_id"],
            "motivo": "única regra elegível; coeficiente da RMI depende do fator "
                      "previdenciário (não estimado). Confira no CNIS.",
        }
    # Nenhuma elegível: a mais próxima pelo menor déficit somado.
    if not regras:
        return {"id": None, "motivo": "nenhuma regra avaliada."}
    mais_proxima = min(regras, key=lambda r: r["_deficit"])
    faltas = "; ".join(mais_proxima["o_que_falta"]) or "condições ainda não atingidas"
    return {
        "id": mais_proxima["regra_id"],
        "motivo": f"nenhuma regra elegível ainda; a mais próxima é "
                  f"'{mais_proxima['nome']}' ({faltas}).",
    }
