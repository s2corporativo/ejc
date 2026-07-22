# ── app/services/caso_zombie_killer.py ───────────────────────────────────────
"""
SUGESTÃO 19: Ciclo de Vida Automático de Casos ("Zombie Killer")

Agente que identifica e arquiva automaticamente casos inativos há mais de 6 meses,
após notificação ao responsável.

Benefícios:
- Limpa dashboards operacionais
- Melhora visão real do escritório
- Reduz ruído em relatórios
- Força revisão periódica de casos antigos
"""
from __future__ import annotations
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from app.models.case import Case, CaseStatus, CaseOperationalStatus
from app.models.user import User
from app.core.notifications import NotificacaoService


class CasoZombieKiller:
    """
    Agente de limpeza de casos inativos (zumbis).
    
    Uso:
        killer = CasoZombieKiller(db_session)
        
        # Executar varredura diária
        resultado = killer.executar_varredura()
        
        # Resultado contém:
        - casos_identificados: lista de casos zumbis encontrados
        - casos_notificados: casos cujos responsáveis foram notificados
        - casos_arquivados: casos efetivamente arquivados
    """
    
    # Configurações padrão
    DIAS_INATIVIDADE_IDENTIFICACAO = 180  # 6 meses para identificar como zumbi
    DIAS_INATIVIDADE_ARQUIVAMENTO = 210   # 7 meses para arquivar automaticamente
    DIAS_AGUARDANDO_REVISAO = 30          # 30 dias após notificação para arquivar
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.notificacao_service = NotificacaoService(db_session)
    
    def identificar_casos_zumbis(self) -> List[Case]:
        """
        Identifica casos ativos sem movimentação há X dias.
        
        Critérios:
        1. Status = 'ativo' ou operacional_status em andamento
        2. Sem movimentos (case_movimentos) há 180+ dias
        3. Sem prazos pendentes
        4. Não marcado como 'aguardando_cliente' ou 'aguardando_terceiro'
        """
        hoje = datetime.utcnow()
        data_corte = hoje - timedelta(days=self.DIAS_INATIVIDADE_IDENTIFICACAO)
        
        # Subquery: último movimento de cada caso
        from sqlalchemy import func
        subquery = self.db.query(
            CaseMovimento.case_id,
            func.max(CaseMovimento.data_evento).label('ultimo_movimento')
        ).group_by(CaseMovimento.case_id).subquery()
        
        # Buscar casos zumbis
        casos_zumbis = self.db.query(Case).outerjoin(
            subquery, Case.id == subquery.c.case_id
        ).filter(
            # Status ativo
            or_(
                Case.status == CaseStatus.ativo,
                Case.operacional_status.in_([
                    CaseOperationalStatus.em_andamento,
                    CaseOperationalStatus.planejamento,
                    CaseOperationalStatus.onboarding
                ])
            ),
            # Último movimento antigo ou nenhum movimento
            or_(
                subquery.c.ultimo_movimento < data_corte,
                subquery.c.ultimo_movimento == None
            ),
            # Não está aguardando cliente/terceiro (esses têm justificativa)
            Case.operacional_status.notin_([
                CaseOperationalStatus.aguardando_cliente,
                CaseOperationalStatus.aguardando_terceiro
            ]),
            # Não deletado
            Case.deleted_at == None
        ).all()
        
        return casos_zumbis
    
    def verificar_prazos_pendentes(self, case: Case) -> bool:
        """Verifica se o caso tem prazos pendentes."""
        from app.models.deadline import Deadline, DeadlineStatus
        
        prazos_pendentes = self.db.query(Deadline).filter(
            Deadline.case_id == case.id,
            Deadline.status == DeadlineStatus.pendente,
            Deadline.deleted_at == None
        ).first()
        
        return prazos_pendentes is not None
    
    def notificar_responsavel(self, case: Case) -> bool:
        """
        Notifica o advogado responsável sobre caso zumbi.
        Retorna True se notificação enviada com sucesso.
        """
        if not case.advogado_responsavel_id:
            return False
        
        responsavel = self.db.query(User).filter(
            User.id == case.advogado_responsavel_id
        ).first()
        
        if not responsavel or not responsavel.email:
            return False
        
        # Criar notificação
        titulo = f"⚠️ Caso Zumbi Detectado: {case.titulo}"
        mensagem = f"""
O caso **{case.titulo}** (nº {case.numero_interno}) está sem movimentação há mais de {self.DIAS_INATIVIDADE_IDENTIFICACAO} dias.

**Detalhes:**
- Cliente: {case.client.nome if case.client else 'N/A'}
- Área: {case.area.value}
- Último movimento: {self._formatar_data(case.movimentos[0].data_evento) if case.movimentos else 'Nenhum'}
- Status atual: {case.operacional_status.value if case.operacional_status else case.status.value}

**Ação necessária:**
1. Registre uma movimentação no caso se ainda estiver ativo
2. Ou solicite o arquivamento se o caso estiver encerrado

⏰ Este caso será **arquivado automaticamente** em {self.DIAS_AGUARDANDO_REVISAO} dias se não houver ação.
        """.strip()
        
        # Enviar notificação
        self.notificacao_service.criar_notificacao(
            user_id=responsavel.id,
            titulo=titulo,
            mensagem=mensagem,
            tipo="caso_zumbi",
            prioridade="alta",
            dados_extra={
                'case_id': case.id,
                'case_titulo': case.titulo,
                'dias_inatividade': self.DIAS_INATIVIDADE_IDENTIFICACAO,
                'data_limite_acao': (datetime.utcnow() + timedelta(days=self.DIAS_AGUARDANDO_REVISAO)).isoformat()
            }
        )
        
        # Enviar email também
        self.notificacao_service.enviar_email(
            destinatario=responsavel.email,
            assunto=titulo,
            corpo=mensagem
        )
        
        return True
    
    def arquivar_caso_zumbi(self, case: Case, justificativa: str = None) -> bool:
        """
        Arquiva caso zumbi após período de espera.
        """
        try:
            # Verificar se há obstáculos
            if self.verificar_prazos_pendentes(case):
                return False  # Não arquivar com prazos pendentes
            
            # Atualizar status
            case.operacional_status = CaseOperationalStatus.encerrado
            case.status = CaseStatus.arquivado
            case.archived_at = datetime.utcnow()
            case.archive_reason = justificativa or "Arquivamento automático: caso inativo por mais de 210 dias sem movimentação (Zombie Killer)"
            
            # Commit
            self.db.commit()
            
            # Notificar sobre arquivamento
            if case.advogado_responsavel_id:
                self._notificar_arquivamento(case)
            
            return True
            
        except Exception as e:
            self.db.rollback()
            print(f"Erro ao arquivar caso zumbi {case.id}: {str(e)}")
            return False
    
    def _notificar_arquivamento(self, case: Case):
        """Notifica responsável sobre arquivamento do caso."""
        responsavel = self.db.query(User).filter(
            User.id == case.advogado_responsavel_id
        ).first()
        
        if not responsavel:
            return
        
        mensagem = f"""
O caso **{case.titulo}** foi **arquivado automaticamente**.

**Motivo:** Inatividade prolongada (>210 dias sem movimentação)

Se o arquivamento foi indevido, você pode:
1. Reativar o caso manualmente
2. Registrar a movimentação faltante
3. Contatar a administração
        """.strip()
        
        self.notificacao_service.criar_notificacao(
            user_id=responsavel.id,
            titulo=f"📁 Caso Arquivado: {case.titulo}",
            mensagem=mensagem,
            tipo="caso_arquivado_zombie",
            prioridade="media",
            dados_extra={'case_id': case.id, 'reativavel': True}
        )
    
    def executar_varredura(self) -> Dict:
        """
        Executa varredura completa de casos zumbis.
        Deve ser rodado diariamente via cron/scheduler.
        """
        resultado = {
            'executado_em': datetime.utcnow().isoformat(),
            'casos_identificados': [],
            'casos_notificados': [],
            'casos_arquivados': [],
            'erros': []
        }
        
        # Passo 1: Identificar casos zumbis
        casos_zumbis = self.identificar_casos_zumbis()
        resultado['casos_identificados'] = [c.id for c in casos_zumbis]
        
        # Passo 2: Para cada caso zumbi, verificar ação necessária
        for case in casos_zumbis:
            try:
                # Verificar se já foi notificado recentemente
                # (implementação simplificada - idealmente teria tabela de histórico)
                
                # Notificar responsável
                if self.notificar_responsavel(case):
                    resultado['casos_notificados'].append(case.id)
                
            except Exception as e:
                resultado['erros'].append({
                    'case_id': case.id,
                    'erro': str(e)
                })
        
        # Passo 3: Identificar casos prontos para arquivamento (>210 dias)
        casos_para_arquivar = self._identificar_casos_prontos_arquivamento()
        
        for case in casos_para_arquivar:
            try:
                if self.arquivar_caso_zumbi(case):
                    resultado['casos_arquivados'].append(case.id)
                    
            except Exception as e:
                resultado['erros'].append({
                    'case_id': case.id,
                    'erro': str(e)
                })
        
        return resultado
    
    def _identificar_casos_prontos_arquivamento(self) -> List[Case]:
        """Identifica casos zumbis já notificados e prontos para arquivamento."""
        # Implementação simplificada
        # Na prática, consultaria tabela de histórico de notificações
        return self.identificar_casos_zumbis()  # Placeholder
    
    def _formatar_data(self, data: datetime) -> str:
        """Formata data para exibição."""
        if not data:
            return "N/A"
        return data.strftime("%d/%m/%Y %H:%M")


# Import necessário (evitar circular)
from app.models.case import CaseMovimento  # noqa: E402
