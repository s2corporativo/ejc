"""
IA Sentinela — EJC v3.0
Monitora a inércia processual e o engajamento com o cliente.
Evita o "esquecimento" de honorários de êxito e processos parados.
"""
import logging
from datetime import datetime, timedelta
from sqlalchemy import text

logger = logging.getLogger("ia_sentinela")

class IASentinela:
    def __init__(self, db_session):
        self.db = db_session

    async def auditar_inercia(self, dias_limite: int = 60):
        """
        Identifica processos sem movimentação há mais de X dias.
        """
        query = text("""
            SELECT id, titulo, numero_interno, ultima_movimentacao 
            FROM cases 
            WHERE ultima_movimentacao < :limite 
            AND status = 'ativo' AND deleted_at IS NULL
        """)
        limite = datetime.now() - timedelta(days=dias_limite)
        result = await self.db.execute(query, {"limite": limite})
        return result.mappings().all()

    async def auditar_atendimento_cliente(self, dias_limite: int = 30):
        """
        Identifica clientes que não recebem reporte/contato há mais de X dias.
        """
        query = text("""
            SELECT c.id, c.full_name, MAX(a.created_at) as ultimo_contato
            FROM clients c
            LEFT JOIN atendimentos a ON a.client_id = c.id
            GROUP BY c.id
            HAVING ultimo_contato < :limite OR ultimo_contato IS NULL
        """)
        limite = datetime.now() - timedelta(days=dias_limite)
        result = await self.db.execute(query, {"limite": limite})
        return result.mappings().all()

    async def gerar_alertas_estrategicos(self):
        inercia = await self.auditar_inercia()
        clientes = await self.auditar_atendimento_cliente()
        
        return {
            "alertas_processuais": [dict(p) for p in inercia],
            "alertas_clientes": [dict(c) for c in clientes],
            "total_risco_financeiro": "Calculando com base em honorários de êxito..."
        }
