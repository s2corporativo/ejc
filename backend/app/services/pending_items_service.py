# ── app/services/pending_items_service.py ────────────────────────────────────────
"""
RECOMENDAÇÃO 1: Dashboard como Central de Ação

Serviço consolidado que coleta TODAS as pendências do escritório em uma única chamada.
Cada pendência inclui link direto para ação, evitando navegação por múltiplos módulos.

Tipos de pendência suportados:
- prazos_vencidos, prazos_criticos_3d, prazos_proximos_7d
- intimacoes_nao_analisadas
- tarefas_vencidas
- casos_sem_proxima_acao
- documentos_pendentes_cliente
- pecas_aguardando_revisao
- propostas_aguardando_aceite
- contratos_aguardando_assinatura
- cobrancas_vencidas
- erros_integracao
- analises_ia_aguardando_validacao
- casos_ativos_sem_movimentacao
- atendimentos_sem_retorno
"""
from datetime import date, timedelta, datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.models.user import User
from app.core.ownership import is_gestao


class PendingItemService:
    """Serviço centralizado de pendências operacionais."""
    
    def __init__(self, db: AsyncSession, current_user: User):
        self.db = db
        self.current_user = current_user
        self.is_admin = is_gestao(current_user)
    
    async def get_all_pending_items(self) -> dict:
        """
        Retorna TODAS as pendências organizadas por categoria.
        Cada item inclui: id, tipo, título, descrição, urgência, data_limite, 
        responsável, link direto para ação, origem (documento/caso/evento).
        """
        hoje = date.today()
        d3 = hoje + timedelta(days=3)
        d7 = hoje + timedelta(days=7)
        
        results = {
            "prazos": await self._get_prazos_pendentes(hoje, d3, d7),
            "intimacoes": await self._get_intimacoes_nao_analisadas(),
            "tarefas_vencidas": await self._get_tarefas_vencidas(hoje),
            "casos_sem_proxima_acao": await self._get_casos_sem_proxima_acao(),
            "documentos_pendentes": await self._get_documentos_pendentes_cliente(),
            "pecas_revisao": await self._get_pecas_aguardando_revisao(),
            "propostas_con tratos": await self._get_propostas_contratos_aguardando(),
            "financeiro": await self._get_cobrancas_vencidas(),
            "erros_integracao": await self._get_erros_integracao(),
            "analises_ia": await self._get_analises_ia_aguardando_validacao(),
            "casos_inativos": await self._get_casos_ativos_sem_movimentacao(),
            "atendimentos": await self._get_atendimentos_sem_retorno(),
            "resumo": {}
        }
        
        # Calcula totais para resumo
        total_geral = sum(len(v) if isinstance(v, list) else 0 for v in results.values())
        results["resumo"] = {
            "total_pendencias": total_geral,
            "por_categoria": {k: len(v) if isinstance(v, list) else 0 for k, v in results.items() if k != "resumo"},
            "data_atualizacao": datetime.now().isoformat()
        }
        
        return results
    
    async def _get_prazos_pendentes(self, hoje: date, d3: date, d7: date) -> list:
        """Prazos vencidos, críticos (3 dias) e próximos (7 dias)."""
        query = text("""
            SELECT 
                d.id,
                'prazo' as tipo,
                CASE 
                    WHEN d.data_prazo < :hoje THEN 'vencido'
                    WHEN d.data_prazo <= :d3 THEN 'critico'
                    ELSE 'proximo'
                END as urgencia,
                d.descricao as titulo,
                c.titulo as caso_titulo,
                c.id as caso_id,
                u.full_name as responsavel,
                d.data_prazo as data_limite,
                d.status,
                '/cases/' || c.id || '/deadlines/' || d.id as link_acao,
                'deadline' as origem_tipo,
                NULL as origem_id
            FROM deadlines d
            JOIN cases c ON c.id = d.case_id AND c.deleted_at IS NULL
            LEFT JOIN users u ON u.id = d.responsavel_id
            WHERE d.status = 'pendente' 
              AND d.deleted_at IS NULL
              AND d.data_prazo <= :d7
              AND (:admin OR c.advogado_responsavel_id = :uid OR c.advogado_auxiliar_id = :uid)
            ORDER BY d.data_prazo ASC
            LIMIT 50
        """)
        
        params = {
            "hoje": hoje, "d3": d3, "d7": d7,
            "admin": self.is_admin,
            "uid": self.current_user.id if not self.is_admin else None
        }
        
        result = await self.db.execute(query, params)
        rows = result.mappings().all()
        
        return [dict(row) for row in rows]
    
    async def _get_intimacoes_nao_analisadas(self) -> list:
        """Intimações recebidas mas ainda não analisadas pela equipe."""
        query = text("""
            SELECT 
                m.id,
                'intimacao' as tipo,
                'intimacao_nao_analisada' as urgencia,
                'Intimação não analisada' as titulo,
                m.descricao,
                c.titulo as caso_titulo,
                c.id as caso_id,
                u.full_name as responsavel,
                m.data_evento as data_limite,
                'pendente' as status,
                '/cases/' || c.id || '/movimentos/' || m.id as link_acao,
                'movimento' as origem_tipo,
                m.id as origem_id
            FROM case_movimentos m
            JOIN cases c ON c.id = m.case_id AND c.deleted_at IS NULL
            LEFT JOIN users u ON u.id = c.advogado_responsavel_id
            WHERE m.tipo = 'intimacao'
              AND m.created_at >= CURRENT_DATE - INTERVAL '7 days'
              AND (:admin OR c.advogado_responsavel_id = :uid OR c.advogado_auxiliar_id = :uid)
              AND NOT EXISTS (
                  SELECT 1 FROM deadlines d 
                  WHERE d.case_id = c.id 
                    AND d.documento_origem_id = m.id
                    AND d.deleted_at IS NULL
              )
            ORDER BY m.data_evento DESC
            LIMIT 30
        """)
        
        params = {
            "admin": self.is_admin,
            "uid": self.current_user.id if not self.is_admin else None
        }
        
        result = await self.db.execute(query, params)
        return [dict(row) for row in result.mappings().all()]
    
    async def _get_tarefas_vencidas(self, hoje: date) -> list:
        """Tarefas vencidas sem conclusão."""
        query = text("""
            SELECT 
                t.id,
                'tarefa_vencida' as tipo,
                'vencido' as urgencia,
                t.titulo,
                t.descricao,
                c.titulo as caso_titulo,
                c.id as caso_id,
                u.full_name as responsavel,
                t.data_vencimento as data_limite,
                t.status,
                '/tasks/' || t.id as link_acao,
                'task' as origem_tipo,
                t.id as origem_id
            FROM tasks t
            LEFT JOIN cases c ON c.id = t.case_id AND c.deleted_at IS NULL
            LEFT JOIN users u ON u.id = t.responsavel_id
            WHERE t.status != 'concluido'
              AND t.data_vencimento < :hoje
              AND t.deleted_at IS NULL
              AND (:admin OR t.responsavel_id = :uid 
                   OR (c.id IS NOT NULL AND (c.advogado_responsavel_id = :uid OR c.advogado_auxiliar_id = :uid)))
            ORDER BY t.data_vencimento ASC
            LIMIT 30
        """)
        
        params = {
            "hoje": hoje,
            "admin": self.is_admin,
            "uid": self.current_user.id if not self.is_admin else None
        }
        
        result = await self.db.execute(query, params)
        return [dict(row) for row in result.mappings().all()]
    
    async def _get_casos_sem_proxima_acao(self) -> list:
        """
        RECOMENDAÇÃO 2: Casos ativos sem próxima ação definida.
        Combate processos cadastrados que ficam sem movimentação interna clara.
        """
        query = text("""
            SELECT 
                c.id,
                'caso_sem_proxima_acao' as tipo,
                'alto' as urgencia,
                'Caso ativo sem próxima ação' as titulo,
                c.titulo as descricao,
                c.titulo as caso_titulo,
                c.id as caso_id,
                u.full_name as responsavel,
                c.updated_at as data_limite,
                'ativo' as status,
                '/cases/' || c.id as link_acao,
                'case' as origem_tipo,
                c.id as origem_id,
                c.operacional_status,
                c.fase,
                c.area
            FROM cases c
            LEFT JOIN users u ON u.id = c.advogado_responsavel_id
            WHERE c.status IN ('ativo', 'triagem')
              AND c.deleted_at IS NULL
              AND (c.proxima_acao IS NULL OR c.proxima_acao = '')
              AND (:admin OR c.advogado_responsavel_id = :uid OR c.advogado_auxiliar_id = :uid)
            ORDER BY c.updated_at ASC
            LIMIT 40
        """)
        
        params = {
            "admin": self.is_admin,
            "uid": self.current_user.id if not self.is_admin else None
        }
        
        result = await self.db.execute(query, params)
        return [dict(row) for row in result.mappings().all()]
    
    async def _get_documentos_pendentes_cliente(self) -> list:
        """Documentos solicitados ao cliente mas ainda não enviados."""
        query = text("""
            SELECT 
                sd.id,
                'documento_pendente' as tipo,
                CASE WHEN sd.data_prazo < CURRENT_DATE THEN 'vencido' ELSE 'pendente' END as urgencia,
                sd.descricao as titulo,
                sd.justificativa as descricao,
                c.titulo as caso_titulo,
                c.id as caso_id,
                cl.nome as cliente_nome,
                sd.data_prazo as data_limite,
                sd.status,
                '/clients/' || cl.id || '/documents/requests' as link_acao,
                'solicitacao_documento' as origem_tipo,
                sd.id as origem_id
            FROM solicitacao_documentos sd
            JOIN clients cl ON cl.id = sd.client_id AND cl.deleted_at IS NULL
            LEFT JOIN cases c ON c.id = sd.case_id AND c.deleted_at IS NULL
            WHERE sd.status = 'pendente'
              AND sd.deleted_at IS NULL
              AND (:admin OR cl.responsavel_id = :uid OR c.advogado_responsavel_id = :uid)
            ORDER BY sd.data_prazo ASC
            LIMIT 30
        """)
        
        params = {
            "admin": self.is_admin,
            "uid": self.current_user.id if not self.is_admin else None
        }
        
        result = await self.db.execute(query, params)
        return [dict(row) for row in result.mappings().all()]
    
    async def _get_pecas_aguardando_revisao(self) -> list:
        """Peças jurídicas geradas por IA aguardando revisão humana."""
        query = text("""
            SELECT 
                ld.id,
                'peca_revisao' as tipo,
                'medio' as urgencia,
                'Peça aguardando revisão' as titulo,
                ld.titulo as descricao,
                c.titulo as caso_titulo,
                c.id as caso_id,
                u.full_name as responsavel,
                ld.created_at as data_limite,
                ld.status,
                '/legal-docs/' || ld.id || '/review' as link_acao,
                'legal_doc' as origem_tipo,
                ld.id as origem_id
            FROM legal_docs ld
            JOIN cases c ON c.id = ld.case_id AND c.deleted_at IS NULL
            LEFT JOIN users u ON u.id = c.advogado_responsavel_id
            WHERE ld.ai_generated = true
              AND ld.human_reviewed = false
              AND ld.status != 'rascunho'
              AND ld.deleted_at IS NULL
              AND (:admin OR c.advogado_responsavel_id = :uid OR c.advogado_auxiliar_id = :uid)
            ORDER BY ld.created_at DESC
            LIMIT 25
        """)
        
        params = {
            "admin": self.is_admin,
            "uid": self.current_user.id if not self.is_admin else None
        }
        
        result = await self.db.execute(query, params)
        return [dict(row) for row in result.mappings().all()]
    
    async def _get_propostas_contratos_aguardando(self) -> list:
        """Propostas de honorários e contratos aguardando aceite/assinatura."""
        query = text("""
            SELECT 
                fp.id,
                'proposta_aguardando' as tipo,
                'medio' as urgencia,
                'Proposta/Contrato aguardando aceite' as titulo,
                fp.descricao,
                c.titulo as caso_titulo,
                c.id as caso_id,
                cl.nome as cliente_nome,
                fp.created_at as data_limite,
                fp.status,
                '/fees/proposals/' || fp.id as link_acao,
                'fee_proposal' as origem_tipo,
                fp.id as origem_id
            FROM fee_proposals fp
            JOIN cases c ON c.id = fp.case_id AND c.deleted_at IS NULL
            JOIN clients cl ON cl.id = c.client_id AND cl.deleted_at IS NULL
            WHERE fp.status IN ('enviada', 'aguardando_aceite')
              AND fp.deleted_at IS NULL
              AND (:admin OR c.advogado_responsavel_id = :uid)
            ORDER BY fp.created_at DESC
            LIMIT 20
        """)
        
        params = {
            "admin": self.is_admin,
            "uid": self.current_user.id if not self.is_admin else None
        }
        
        result = await self.db.execute(query, params)
        return [dict(row) for row in result.mappings().all()]
    
    async def _get_cobrancas_vencidas(self) -> list:
        """Cobranças e parcelas vencidas."""
        query = text("""
            SELECT 
                f.id,
                'cobranca_vencida' as tipo,
                'critico' as urgencia,
                'Parcela vencida' as titulo,
                f.descricao,
                c.titulo as caso_titulo,
                c.id as caso_id,
                cl.nome as cliente_nome,
                f.data_vencimento as data_limite,
                f.valor,
                f.status,
                '/fees/' || f.id as link_acao,
                'fee' as origem_tipo,
                f.id as origem_id
            FROM fees f
            JOIN cases c ON c.id = f.case_id AND c.deleted_at IS NULL
            JOIN clients cl ON cl.id = c.client_id AND cl.deleted_at IS NULL
            WHERE f.status IN ('pendente', 'atrasado')
              AND f.data_vencimento < CURRENT_DATE
              AND f.deleted_at IS NULL
              AND (:admin OR c.advogado_responsavel_id = :uid)
            ORDER BY f.data_vencimento ASC
            LIMIT 30
        """)
        
        params = {
            "admin": self.is_admin,
            "uid": self.current_user.id if not self.is_admin else None
        }
        
        result = await self.db.execute(query, params)
        return [dict(row) for row in result.mappings().all()]
    
    async def _get_erros_integracao(self) -> list:
        """Erros de integração com tribunais/sistemas externos."""
        query = text("""
            SELECT 
                c.id,
                'erro_integracao' as tipo,
                'alto' as urgencia,
                'Erro de sincronização' as titulo,
                c.sync_error as descricao,
                c.titulo as caso_titulo,
                c.id as caso_id,
                u.full_name as responsavel,
                c.updated_at as data_limite,
                'erro' as status,
                '/cases/' || c.id || '/sync' as link_acao,
                'case_sync' as origem_tipo,
                c.id as origem_id
            FROM cases c
            LEFT JOIN users u ON u.id = c.advogado_responsavel_id
            WHERE c.sync_error IS NOT NULL
              AND c.deleted_at IS NULL
              AND (:admin OR c.advogado_responsavel_id = :uid OR c.advogado_auxiliar_id = :uid)
            ORDER BY c.updated_at DESC
            LIMIT 20
        """)
        
        params = {
            "admin": self.is_admin,
            "uid": self.current_user.id if not self.is_admin else None
        }
        
        result = await self.db.execute(query, params)
        return [dict(row) for row in result.mappings().all()]
    
    async def _get_analises_ia_aguardando_validacao(self) -> list:
        """Análises de IA aguardando validação humana."""
        query = text("""
            SELECT 
                ci.id,
                'analise_ia' as tipo,
                'medio' as urgencia,
                'Análise de IA aguardando validação' as titulo,
                ci.resumo_executivo as descricao,
                c.titulo as caso_titulo,
                c.id as caso_id,
                u.full_name as responsavel,
                ci.created_at as data_limite,
                ci.status_validacao as status,
                '/intelligence/' || ci.id || '/review' as link_acao,
                'case_intelligence' as origem_tipo,
                ci.id as origem_id
            FROM case_intelligence ci
            JOIN cases c ON c.id = ci.case_id AND c.deleted_at IS NULL
            LEFT JOIN users u ON u.id = c.advogado_responsavel_id
            WHERE ci.status_validacao = 'pendente'
              AND ci.deleted_at IS NULL
              AND (:admin OR c.advogado_responsavel_id = :uid)
            ORDER BY ci.created_at DESC
            LIMIT 20
        """)
        
        params = {
            "admin": self.is_admin,
            "uid": self.current_user.id if not self.is_admin else None
        }
        
        result = await self.db.execute(query, params)
        return [dict(row) for row in result.mappings().all()]
    
    async def _get_casos_ativos_sem_movimentacao(self) -> list:
        """Casos ativos sem movimentação há mais de 30 dias."""
        query = text("""
            SELECT 
                c.id,
                'caso_inativo' as tipo,
                'alto' as urgencia,
                'Caso sem movimentação há 30+ dias' as titulo,
                c.titulo as descricao,
                c.titulo as caso_titulo,
                c.id as caso_id,
                u.full_name as responsavel,
                c.updated_at as data_limite,
                c.status,
                '/cases/' || c.id as link_acao,
                'case' as origem_tipo,
                c.id as origem_id,
                c.operacional_status,
                MAX(m.created_at) as ultima_movimentacao
            FROM cases c
            LEFT JOIN case_movimentos m ON m.case_id = c.id
            LEFT JOIN users u ON u.id = c.advogado_responsavel_id
            WHERE c.status IN ('ativo', 'triagem')
              AND c.deleted_at IS NULL
              AND (c.updated_at < CURRENT_DATE - INTERVAL '30 days' 
                   OR MAX(m.created_at) FILTER (WHERE m.created_at IS NOT NULL) < CURRENT_DATE - INTERVAL '30 days')
              AND (:admin OR c.advogado_responsavel_id = :uid OR c.advogado_auxiliar_id = :uid)
            GROUP BY c.id, c.titulo, u.full_name, c.status, c.operacional_status
            ORDER BY COALESCE(MAX(m.created_at), c.updated_at) ASC
            LIMIT 30
        """)
        
        params = {
            "admin": self.is_admin,
            "uid": self.current_user.id if not self.is_admin else None
        }
        
        result = await self.db.execute(query, params)
        return [dict(row) for row in result.mappings().all()]
    
    async def _get_atendimentos_sem_retorno(self) -> list:
        """Atendimentos realizados sem retorno registrado ao cliente."""
        query = text("""
            SELECT 
                a.id,
                'atendimento_sem_retorno' as tipo,
                'medio' as urgencia,
                'Atendimento sem retorno ao cliente' as titulo,
                a.assunto as descricao,
                c.titulo as caso_titulo,
                c.id as caso_id,
                cl.nome as cliente_nome,
                a.created_at as data_limite,
                a.status,
                '/atendimentos/' || a.id as link_acao,
                'atendimento' as origem_tipo,
                a.id as origem_id
            FROM atendimentos a
            LEFT JOIN cases c ON c.id = a.case_id AND c.deleted_at IS NULL
            LEFT JOIN clients cl ON cl.id = COALESCE(a.client_id, c.client_id) AND cl.deleted_at IS NULL
            WHERE a.retorno_realizado = false
              AND a.deleted_at IS NULL
              AND a.created_at >= CURRENT_DATE - INTERVAL '15 days'
              AND (:admin OR a.atendido_por = :uid OR c.advogado_responsavel_id = :uid)
            ORDER BY a.created_at DESC
            LIMIT 25
        """)
        
        params = {
            "admin": self.is_admin,
            "uid": self.current_user.id if not self.is_admin else None
        }
        
        result = await self.db.execute(query, params)
        return [dict(row) for row in result.mappings().all()]
    
    async def get_pending_summary(self) -> dict:
        """
        Retorna apenas o resumo das pendências (contagens por categoria).
        Útil para cards do dashboard sem carregar todos os detalhes.
        """
        all_items = await self.get_all_pending_items()
        return all_items.get("resumo", {})


# Factory function para facilitar uso nos routers
def get_pending_service(db: AsyncSession, current_user: User) -> PendingItemService:
    return PendingItemService(db, current_user)
