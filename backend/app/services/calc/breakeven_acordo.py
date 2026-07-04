# ── app/services/calc/breakeven_acordo.py ────────────────────────────────────
# Calculadora determinística do ponto de equilíbrio (breakeven) entre ACORDO
# imediato e PROSSEGUIR com a ação (Visual Law — CalculadoraAcordo.tsx).
#
# Modelo (100% determinístico, sem IA — memória de cálculo auditável):
#   valor_esperado    = prob_exito × valor_causa
#   custos_estimados  = custas + sucumbência esperada
#       custas        = valor_causa × custas_pct/100          (adiantadas sempre)
#       sucumbência   = (1 − prob_exito) × valor_causa × honorarios_pct/100
#                       (só é devida em caso de derrota — ponderada pelo risco)
#   resultado_liquido = valor_esperado − custos_estimados     (nominal, futuro)
#   vpl_litigio       = resultado_liquido / (1 + selic_anual)^tempo_anos
#                       (desconto a valor presente pela Selic — custo de
#                        oportunidade de esperar a tramitação)
#   breakeven         = max(vpl_litigio, 0): um acordo HOJE nesse valor é
#                       financeiramente equivalente a litigar; acima dele o
#                       acordo tende a superar o litígio.
#   custo_do_tempo    = resultado_liquido − vpl_litigio (quanto a espera corrói)
from __future__ import annotations

# Tempo médio de tramitação (anos) por tribunal — estimativas conservadoras
# baseadas no Justiça em Números/CNJ; usadas apenas como default quando o
# advogado não informa tempo_anos.
TEMPO_MEDIO_ANOS: dict[str, float] = {
    "TJMG": 3.5,
    "TJSP": 3.0,
    "TRT3": 2.5,
    "TRF6": 4.0,
    "STJ": 2.0,
}
TEMPO_PADRAO_ANOS = 3.0

# Defaults dos parâmetros avançados (o frontend mostra "Padrão do sistema").
CUSTAS_PCT_PADRAO = 2.0                # custas judiciais típicas (% do valor da causa)
SUCUMBENCIA_PCT_PADRAO = 10.0          # CPC art. 85 §2º — piso de 10%
SELIC_ANUAL_FALLBACK = 0.15            # usado quando a API do BCB está indisponível


def _r2(v: float) -> float:
    return round(v + 0.0, 2)


def calcular_breakeven(
    *,
    valor_causa: float,
    prob_exito: float,
    tempo_anos: float | None = None,
    tribunal: str | None = None,
    custas_pct: float | None = None,
    honorarios_sucumbencia_pct: float | None = None,
    selic_anual: float = SELIC_ANUAL_FALLBACK,
    selic_fonte: str = "fallback",
) -> dict:
    """Cálculo puro do breakeven do acordo. Retorna o shape exato do
    BreakevenResponse consumido pelo frontend (types/visualLaw.ts)."""
    trib = tribunal.strip().upper() if tribunal else None
    if tempo_anos is None:
        tempo_anos = TEMPO_MEDIO_ANOS.get(trib or "", TEMPO_PADRAO_ANOS)
    if custas_pct is None:
        custas_pct = CUSTAS_PCT_PADRAO
    if honorarios_sucumbencia_pct is None:
        honorarios_sucumbencia_pct = SUCUMBENCIA_PCT_PADRAO

    valor_esperado = prob_exito * valor_causa
    custas = valor_causa * custas_pct / 100.0
    sucumbencia_esperada = (1.0 - prob_exito) * valor_causa * honorarios_sucumbencia_pct / 100.0
    custos_estimados = custas + sucumbencia_esperada
    resultado_liquido = valor_esperado - custos_estimados

    fator_desconto = (1.0 + selic_anual) ** tempo_anos
    vpl_litigio = resultado_liquido / fator_desconto

    breakeven = max(vpl_litigio, 0.0)
    sugestao_acordo = breakeven
    custo_do_tempo = resultado_liquido - vpl_litigio

    memoria = [
        f"Valor esperado = prob. de êxito {prob_exito:.0%} × valor da causa "
        f"R$ {valor_causa:,.2f} = R$ {valor_esperado:,.2f}",
        f"Custas processuais = {custas_pct:.1f}% do valor da causa = R$ {custas:,.2f}",
        f"Sucumbência esperada = (1 − {prob_exito:.0%}) × {honorarios_sucumbencia_pct:.1f}% "
        f"do valor da causa = R$ {sucumbencia_esperada:,.2f}",
        f"Resultado líquido nominal = R$ {valor_esperado:,.2f} − R$ {custos_estimados:,.2f} "
        f"= R$ {resultado_liquido:,.2f}",
        f"Desconto a valor presente: Selic {selic_anual:.2%} a.a. "
        f"({'BCB' if selic_fonte == 'bcb' else 'estimada'}) por {tempo_anos:g} ano(s) "
        f"→ fator {fator_desconto:.4f}",
        f"VPL do litígio = R$ {resultado_liquido:,.2f} ÷ {fator_desconto:.4f} "
        f"= R$ {vpl_litigio:,.2f}",
        f"Breakeven (acordo hoje equivalente a litigar) = R$ {breakeven:,.2f}",
        f"Custo do tempo = R$ {resultado_liquido:,.2f} − R$ {vpl_litigio:,.2f} "
        f"= R$ {custo_do_tempo:,.2f}",
    ]

    return {
        "parametros": {
            "valor_causa": _r2(valor_causa),
            "prob_exito": prob_exito,
            "tempo_anos": tempo_anos,
            "tribunal": trib,
            "selic_anual": selic_anual,
            "selic_fonte": selic_fonte,
            "custas_pct": custas_pct,
            "honorarios_sucumbencia_pct": honorarios_sucumbencia_pct,
        },
        "valor_esperado": _r2(valor_esperado),
        "custos_estimados": _r2(custos_estimados),
        "vpl_litigio": _r2(vpl_litigio),
        "sugestao_acordo": _r2(sugestao_acordo),
        "breakeven": _r2(breakeven),
        "comparativo": {
            "litigio_vpl": _r2(vpl_litigio),
            "acordo_imediato_equivalente": _r2(breakeven),
            "custo_do_tempo": _r2(custo_do_tempo),
        },
        "memoria_calculo": memoria,
    }
