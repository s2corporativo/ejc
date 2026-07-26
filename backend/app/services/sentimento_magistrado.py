"""
IA de Análise de Sentimento de Magistrados — EJC v3.0
Identifica tendências e "humor" decisório em tempo real.
"""
import logging
from app.core.ai_brain import ai_brain

logger = logging.getLogger("ejc.sentimento_magistrado")

class SentimentoMagistrado:
    def __init__(self):
        self.ai = ai_brain

    async def analisar_tendencia(self, ultimas_decisoes: list):
        """
        Analisa o tom das últimas decisões para identificar rigor ou flexibilidade.
        """
        texto_consolidado = "\n".join(ultimas_decisoes[:10])
        prompt = f"""
        Analise o padrão destas últimas 10 decisões do magistrado:
        {texto_consolidado}
        
        Classifique:
        1. Tendência Atual (Rigorosa / Flexível / Neutra).
        2. Temas Sensíveis (O que ele mais tem negado?).
        3. Recomendação de Tom para a Petição (Agressivo / Conciliador / Estritamente Técnico).
        """
        return await self.ai.generate(prompt, "secundario")

sentimento_ia = SentimentoMagistrado()
