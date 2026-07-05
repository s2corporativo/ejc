"""
Módulo Radar de Poder — EJC Intelligence v3.0
Monitoramento estratégico dos Três Poderes (Legislativo, Executivo e Judiciário).
"""
import httpx
import logging
from datetime import datetime

logger = logging.getLogger("radar_poder")

class RadarPoder:
    def __init__(self):
        self.camara_api = "https://dadosabertos.camara.leg.br/api/v2"
        self.senado_api = "https://legis.senado.leg.br/dadosabertos"

    async def monitorar_projetos_lei(self, keywords: list):
        """
        Busca Projetos de Lei recentes na Câmara que contenham as palavras-chave.
        """
        url = f"{self.camara_api}/proposicoes"
        params = {
            "dataInicio": datetime.now().strftime("%Y-01-01"),
            "ordem": "DESC",
            "ordenarPor": "id"
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                proposicoes = response.json().get("dados", [])
                
                alertas = []
                for p in proposicoes:
                    ementa = p.get("ementa", "").lower()
                    if any(kw.lower() in ementa for kw in keywords):
                        alertas.append(p)
                return alertas
        except Exception as e:
            logger.error(f"Erro ao monitorar Câmara: {e}")
            return []

    # P2 (2026-07-05): stub monitorar_dou removido — o monitoramento REAL do
    # DOU é o de app/services/diario_oficial_service.py (job do scheduler).

radar_poder = RadarPoder()
