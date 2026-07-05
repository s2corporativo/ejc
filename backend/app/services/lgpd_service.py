# ── app/services/lgpd_service.py ──────────────────────────────────────────────
# Lógica pura do ROPA / RIPD (LGPD arts. 37-38). Sem dependência de banco —
# testável isoladamente (espelha services/sociedades_service.py).
#
# A avaliação de risco é DETERMINÍSTICA e HONESTA (NÃO usa IA): é uma heurística
# de triagem baseada em fatores legais objetivos do próprio registro, com os
# fatores explicitados para entrarem no RIPD. Não substitui a análise do
# encarregado (DPO) — apenas prioriza quais operações exigem RIPD formal.
from __future__ import annotations

from app.models.lgpd_tratamento import BaseLegal, NivelRisco


def _attr(registro, nome: str):
    """Lê o campo de um registro que pode ser o ORM RegistroTratamento OU o
    payload Pydantic de criação (ambos expõem os mesmos atributos)."""
    return getattr(registro, nome, None)


def _base_legal_valor(registro) -> str | None:
    """base_legal pode vir como str (ORM) ou enum BaseLegal (payload)."""
    v = _attr(registro, "base_legal")
    return v.value if isinstance(v, BaseLegal) else v


def avaliar_risco(registro) -> tuple[str, list[str]]:
    """Heurística determinística de risco do tratamento → (nível, fatores).

    Regra (score aditivo, sem IA):
      • dados sensíveis (art. 11)                    → +2  (categoria de maior tutela)
      • transferência internacional (arts. 33-36)    → +1  (exige salvaguardas)
      • base legal 'legítimo interesse' (art. 10)     → +1  (exige LIA documentada)

    Mapa do score → nível:  0 = baixo · 1 = médio · ≥2 = alto.

    Assim: operação simples → baixo; legítimo interesse (sozinho) → médio (pede
    LIA); dado sensível → alto. `fatores` lista, em linguagem jurídica, o que
    elevou o nível — consumido pelo RIPD e pela tela.
    """
    score = 0
    fatores: list[str] = []

    if bool(_attr(registro, "dados_sensiveis")):
        score += 2
        fatores.append(
            "Tratamento de dados pessoais SENSÍVEIS (art. 11 da LGPD) — categoria "
            "de maior proteção legal; requer base legal específica e RIPD."
        )

    if bool(_attr(registro, "transferencia_internacional")):
        score += 1
        fatores.append(
            "Transferência internacional de dados (arts. 33 a 36 da LGPD) — exige "
            "salvaguardas (país adequado, cláusulas-padrão ou garantias equivalentes)."
        )

    if _base_legal_valor(registro) == BaseLegal.legitimo_interesse.value:
        score += 1
        fatores.append(
            "Base legal 'legítimo interesse' (art. 10 da LGPD) — exige Avaliação de "
            "Legítimo Interesse (LIA) e teste de proporcionalidade documentado."
        )

    if score >= 2:
        nivel = NivelRisco.alto.value
    elif score == 1:
        nivel = NivelRisco.medio.value
    else:
        nivel = NivelRisco.baixo.value

    return nivel, fatores


def montar_resumo(registros: list) -> dict:
    """Estatísticas do ROPA do cliente (header da tela + capa do RIPD):
    total de operações, quantas com dados sensíveis, quantas com transferência
    internacional e a distribuição por nível de risco."""
    total = len(registros)
    com_sensiveis = sum(1 for r in registros if bool(_attr(r, "dados_sensiveis")))
    com_transferencia = sum(
        1 for r in registros if bool(_attr(r, "transferencia_internacional"))
    )
    distribuicao = {NivelRisco.baixo.value: 0,
                    NivelRisco.medio.value: 0,
                    NivelRisco.alto.value: 0}
    for r in registros:
        nivel = _attr(r, "risco") or NivelRisco.baixo.value
        if nivel in distribuicao:
            distribuicao[nivel] += 1

    return {
        "total_operacoes": total,
        "com_dados_sensiveis": com_sensiveis,
        "com_transferencia_internacional": com_transferencia,
        "distribuicao_risco": distribuicao,
    }
