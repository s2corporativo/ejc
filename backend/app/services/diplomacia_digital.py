"""
Módulo de Diplomacia Digital — EJC v3.0
Gestão de Ativos Financeiros Judiciais e Estratégia de Liquidez.
"""
import logging
from math import pow

logger = logging.getLogger("ejc.diplomacia_digital")

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

    async def gerar_dossie_pressao(self, dados_acordo: dict) -> dict:
        """
        Gera os argumentos para o Dossiê de Pressão (Visual Law).

        P1 (2026-07-05): antes retornava string fixa; agora chama o gateway
        central de IA (task_type="estrategia" — cadeia Ollama→Anthropic→Groq,
        com barreira LGPD do próprio gateway). O prompt contém apenas dados
        NUMÉRICOS do cálculo (sem PII). Saída é RASCUNHO (HITL): o router
        registra AILog e marca is_rascunho.

        Retorna dict com argumentacao/prompt/modelo/provedor/tokens — o
        contrato antigo (string) não tinha nenhum consumidor.
        """
        prompt = f"""
        Gere um argumento de negociação para o advogado da parte contrária.
        Dados: Valor da Causa {dados_acordo['valor_causa']}, Probabilidade de Perda deles: {dados_acordo['probabilidade_exito']}.
        Tempo estimado de processo: {dados_acordo['tempo_estimado_anos']} anos.
        Valor Presente Líquido do litígio: {dados_acordo.get('valor_presente_liquido')}.
        Sugestão de acordo: {dados_acordo.get('sugestao_acordo_ideal')} (Selic anual considerada: {dados_acordo.get('selic_anual')}).

        Foque em mostrar que o acordo hoje é a única decisão racional para o cliente deles evitar prejuízos maiores com custas e juros.
        """
        from app.services import ai_gateway
        resp = await ai_gateway.chat(
            messages=[{"role": "user", "content": prompt}],
            task_type="estrategia", temperature=0.3, max_tokens=1200,
        )
        return {
            "argumentacao": resp.texto,
            "prompt": prompt.strip(),
            "modelo": resp.modelo,
            "provedor": resp.provedor,
            "input_tokens": resp.input_tokens,
            "output_tokens": resp.output_tokens,
        }

diplomacia = DiplomaciaDigital()
