"""
Módulo de Diplomacia Digital — EJC v3.0
Gestão de Ativos Financeiros Judiciais e Estratégia de Liquidez.
"""
import logging
from math import pow

logger = logging.getLogger("diplomacia_digital")

class DiplomaciaDigital:
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
        Calcula o Valor Presente Líquido (VPL) do processo para sugerir o acordo ideal.
        VPL = (Valor * Probabilidade - Custos) / (1 + Selic)^Tempo

        Retrocompatível: com os defaults (sem custos, selic da instância) o
        resultado numérico é idêntico ao contrato original usado por
        /diplomacia-v3/calcular-acordo — apenas chaves ADITIVAS foram incluídas
        (custos_estimados, custos_detalhe, selic_anual).
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

    async def gerar_dossie_pressao(self, dados_acordo: dict):
        """
        Gera os argumentos para o Dossiê de Pressão (Visual Law).
        """
        prompt = f"""
        Gere um argumento de negociação para o advogado da parte contrária.
        Dados: Valor da Causa {dados_acordo['valor_causa']}, Probabilidade de Perda deles: {dados_acordo['probabilidade_exito']}.
        Tempo estimado de processo: {dados_acordo['tempo_estimado_anos']} anos.
        
        Foque em mostrar que o acordo hoje é a única decisão racional para o cliente deles evitar prejuízos maiores com custas e juros.
        """
        # Aqui usaria o ai_brain para gerar o texto do dossiê
        return "Argumentação gerada com base em dados estatísticos."

diplomacia = DiplomaciaDigital()
