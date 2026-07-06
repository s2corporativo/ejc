"""
Monitor Judiciário — EJC Intelligence v3.0
Acompanhamento de Pautas de Julgamento (STF/STJ).
"""
import logging

logger = logging.getLogger("monitor_judiciario")

class MonitorJudiciario:
    def __init__(self):
        self.stf_api = "https://api.stf.jus.br/pauta/v1"
        self.stj_api = "https://api.stj.jus.br/pauta/v1"

    async def buscar_pautas_julgamento(self, temas: list):
        """
        Busca processos pautados que coincidam com os temas de interesse do escritório.

        STUB NÃO IMPLEMENTADO: as APIs de pauta STF/STJ ainda não foram
        integradas (sem request real). Retorna lista vazia (resultado honesto);
        sem chamadores vivos hoje. Implementar a consulta antes de depender disto.
        """
        logger.info("[monitor_judiciario] stub — pautas para temas %s não implementado", temas)
        return []

    async def alerta_repercussao_geral(self):
        """
        Monitora novos temas de Repercussão Geral (STF) e Repetitivos (STJ).

        STUB NÃO IMPLEMENTADO: sem integração real com STF/STJ. Retorna [] honesto.
        """
        return []

monitor_judiciario = MonitorJudiciario()
