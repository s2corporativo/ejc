"""
Cálculo de acordo — Valor Presente Líquido (VPL) do litígio e piso racional de
acordo. Motor DETERMINÍSTICO reutilizado por `visual_law_core` (breakeven).

Histórico: nasceu como `diplomacia_digital.DiplomaciaDigital`, ao lado de um
gerador de "dossiê de pressão" contra a parte contrária. CORTE-2 (decisão do
titular, plano-mestre 2026-08-24, executado em 2026-09-05): o gerador foi
removido — risco reputacional/disciplinar num sistema de advocacia — e só o
cálculo financeiro, que é neutro e testado (tests/test_visual_law.py), seguiu
aqui com nome que descreve o que faz.
"""
from math import pow


class CalculoAcordo:
    def __init__(self, selic_atual: float = 0.1075):
        self.selic = selic_atual

    def calcular_ponto_equilibrio(
        self,
        valor_causa: float,
        prob_exito: float,
        tempo_anos: float,
        selic_anual: float | None = None,
        custas_pct: float = 0.0,
        honorarios_sucumbencia_pct: float = 0.0,
    ):
        """
        VPL do processo para sugerir o acordo ideal.
        VPL = (Valor * Probabilidade - Custos) / (1 + Selic)^Tempo

        Com os defaults (sem custos, selic da instância) o resultado numérico é
        idêntico ao contrato original — chaves ADITIVAS: custos_estimados,
        custos_detalhe, selic_anual.
        """
        selic = self.selic if selic_anual is None else selic_anual
        valor_esperado = valor_causa * prob_exito
        custas = valor_causa * custas_pct
        # Sucumbência só é devida em caso de derrota → ponderada pela prob. de perda
        honorarios = valor_causa * honorarios_sucumbencia_pct * (1 - prob_exito)
        custos = custas + honorarios
        vpl = (valor_esperado - custos) / pow((1 + selic), tempo_anos)
        # Sugestão de acordo: VPL + 5% de margem de conveniência
        sugestao_acordo = vpl * 1.05
        return {
            "valor_causa": valor_causa,
            "probabilidade_exito": prob_exito,
            "tempo_estimado_anos": tempo_anos,
            "valor_presente_liquido": round(vpl, 2),
            "sugestao_acordo_ideal": round(sugestao_acordo, 2),
            "custo_oportunidade_perda": round(valor_esperado - vpl, 2),
            "custos_estimados": round(custos, 2),
            "custos_detalhe": {
                "custas": round(custas, 2),
                "honorarios_sucumbencia_esperados": round(honorarios, 2),
            },
            "selic_anual": selic,
        }
