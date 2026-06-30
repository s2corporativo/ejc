"""
Integração com APIs Públicas Gratuitas (CNJ, STF, STJ, TCU, BC, etc.)
Foco em Soberania Tecnológica e Custo Zero.
"""
import httpx
import logging
from datetime import datetime, timedelta

# Configuração de Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("public_apis")

class PublicAPIClient:
    def __init__(self):
        self.cache = {}
        self.timeout = 10.0

    async def _fetch_with_cache(self, key: str, url: str, params: dict = None):
        if key in self.cache:
            data, expiry = self.cache[key]
            if datetime.now() < expiry:
                logger.info(f"Cache hit for {key}")
                return data

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                self.cache[key] = (data, datetime.now() + timedelta(hours=1))
                return data
        except Exception as e:
            logger.error(f"Error fetching from {url}: {e}")
            return None

    async def get_selic(self):
        url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.11/dados/ultimos/1?formato=json"
        return await self._fetch_with_cache("selic", url)

    async def get_stf_jurisprudencia(self, query: str):
        # Exemplo de endpoint (requer ajuste conforme documentação oficial do STF)
        url = f"https://api.stf.jus.br/jurisprudencia/v1/pesquisa"
        return await self._fetch_with_cache(f"stf_{query}", url, {"q": query})

    async def get_cnpj_info(self, cnpj: str):
        url = f"https://receitaws.com.br/v1/cnpj/{cnpj}"
        return await self._fetch_with_cache(f"cnpj_{cnpj}", url)

api_client = PublicAPIClient()
