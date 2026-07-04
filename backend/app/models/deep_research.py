# ── app/models/deep_research.py ──────────────────────────────────────────────
# Deep Research jurídica — job PERSISTIDO de pesquisa multi-etapa (roda em
# background por minutos). O cliente cria o job e faz POLLING no status/progresso.
#
# Sem Celery/Redis: o worker roda via fastapi.BackgroundTasks e escreve o
# andamento aqui. Todo resultado é RASCUNHO (HITL/OAB) — exige revisão humana.
from __future__ import annotations
import enum
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, Enum as SAEnum, func
from app.core.database import Base


class DeepResearchStatus(str, enum.Enum):
    em_andamento = "em_andamento"   # worker executando as etapas
    concluido    = "concluido"      # relatório final disponível
    erro         = "erro"           # falhou — erro_mensagem preenchido (nunca "success" vazio)


class DeepResearchJob(Base):
    __tablename__ = "deep_research_jobs"

    id       = Column(String(36), primary_key=True)
    user_id  = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    # case_id é opcional e SEM FK (espelha AILog.case_id): triagem/consultas
    # avulsas podem não estar vinculadas a um caso.
    case_id  = Column(String(36), nullable=True, index=True)

    pergunta = Column(Text, nullable=False)
    tese     = Column(Text, nullable=True)
    nivel_inteligencia = Column(String(20), nullable=False, default="alto")

    status   = Column(
        SAEnum(DeepResearchStatus, name="deepresearchstatus"),
        nullable=False, default=DeepResearchStatus.em_andamento, index=True,
    )
    progresso    = Column(Integer, nullable=False, default=0)   # 0-100
    etapa_atual  = Column(String(120), nullable=True)

    # Trilha das etapas executadas e o relatório final estruturado (JSON serializado
    # em Text — mantém o padrão dos outros models do EJC, sem depender de JSONB).
    etapas_json    = Column(Text, nullable=True)   # [{etapa, detalhe, ts}, ...]
    resultado_json = Column(Text, nullable=True)   # relatório final com fontes rastreáveis
    erro_mensagem  = Column(Text, nullable=True)

    # Limites de segurança observados (auditoria/HITL).
    total_subquestoes = Column(Integer, nullable=False, default=0)
    total_chamadas_ia = Column(Integer, nullable=False, default=0)

    created_at   = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at   = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    concluido_em = Column(DateTime(timezone=True), nullable=True)
