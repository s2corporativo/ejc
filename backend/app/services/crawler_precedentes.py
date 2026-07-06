"""
Crawler de Precedentes — EJC v3.0
Captura sentenças e acórdãos de portais públicos (TJMG, TRTs, STF, STJ).
"""
import logging

logger = logging.getLogger("crawler_precedentes")

class CrawlerPrecedentes:
    def __init__(self):
        self.headers = {"User-Agent": "EJC-Jurimetria-Bot/3.0"}

    async def buscar_precedentes_magistrado(self, nome_magistrado: str, tema: str):
        """
        Busca as últimas decisões de um magistrado específico sobre um tema.

        STUB NÃO IMPLEMENTADO: a integração com o portal do STJ ainda não foi
        construída (não há request real). Retorna status honesto
        "nao_implementado" — NÃO simule sucesso. Sem chamadores vivos hoje;
        implementar o scraping/consulta antes de usar em produção.
        """
        logger.info(
            "[crawler_precedentes] stub — busca de %s sobre %s não implementada",
            nome_magistrado, tema,
        )
        return {"status": "nao_implementado", "total_encontrado": 0, "precedentes": []}

crawler = CrawlerPrecedentes()
