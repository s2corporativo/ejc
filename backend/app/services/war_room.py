"""
Simulador War Room — EJC v3.0
Simula o "Advogado da Parte Contrária" para blindagem de teses.
"""
import logging
from app.core.ai_brain import ai_brain

logger = logging.getLogger("war_room")

class WarRoom:
    def __init__(self):
        self.ai = ai_brain

    async def simular_contestacao(self, peticao_inicial: str):
        """
        Gera uma contra-argumentação agressiva para testar a robustez da inicial.
        """
        prompt = f"""
        Você é o Advogado da Parte Contrária, altamente agressivo e técnico. 
        Seu objetivo é DESTRUIR esta petição inicial. 
        Aponte:
        1. Nulidades processuais.
        2. Contradições fáticas.
        3. Jurisprudência defensiva (que derruba a tese).
        4. Falta de provas essenciais.
        
        Petição Inicial: {peticao_inicial}
        
        Retorne um relatório de vulnerabilidades.
        """
        resultado = await self.ai.generate(prompt, "principal")
        return resultado

    async def preparar_replica_blindada(self, contestacao_adversaria: str, tese_original: str):
        """
        Sugere argumentos para a réplica com base nos ataques identificados.
        """
        prompt = f"""
        Com base nesta contestação: {contestacao_adversaria}
        E na nossa tese original: {tese_original}
        
        Sugira 3 argumentos de blindagem para a réplica que anulem os ataques da contraparte.
        """
        return await self.ai.generate(prompt, "secundario")

war_room = WarRoom()
