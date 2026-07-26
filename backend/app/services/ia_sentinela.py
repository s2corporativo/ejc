"""
IA Sentinela — EJC v3.0
Monitora a inércia processual e o engajamento com o cliente.
Evita o "esquecimento" de honorários de êxito e processos parados.
"""
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import text, select, func

logger = logging.getLogger("ejc.ia_sentinela")

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
        limite = datetime.now(timezone.utc) - timedelta(days=dias_limite)
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
        limite = datetime.now(timezone.utc) - timedelta(days=dias_limite)
        result = await self.db.execute(query, {"limite": limite})
        return result.mappings().all()

    async def _risco_financeiro_exito(self, case_ids: list) -> float:
        """Exposição financeira concreta da inércia: soma dos honorários de ÊXITO
        (valor contratado) ainda NÃO pagos dos casos parados. É o que se perde se
        o processo for esquecido. 0.0 quando não há casos/honorários."""
        if not case_ids:
            return 0.0
        from app.models.fee import Fee, FeeTipo, FeeStatus
        total = (await self.db.execute(
            select(func.coalesce(func.sum(Fee.valor), 0)).where(
                Fee.case_id.in_(case_ids),
                Fee.tipo == FeeTipo.exito,
                Fee.deleted_at.is_(None),
                Fee.status != FeeStatus.pago,
            )
        )).scalar()
        return float(total or 0)

    async def gerar_alertas_estrategicos(self):
        inercia = await self.auditar_inercia()
        clientes = await self.auditar_atendimento_cliente()
        risco = await self._risco_financeiro_exito([p["id"] for p in inercia])

        return {
            "alertas_processuais": [dict(p) for p in inercia],
            "alertas_clientes": [dict(c) for c in clientes],
            # Valor real (R$) — honorários de êxito não pagos dos casos em inércia.
            "total_risco_financeiro": risco,
        }
