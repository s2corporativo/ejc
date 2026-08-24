# ── app/models/tese.py ────────────────────────────────────────────────────────
# Banco de Teses Jurídicas — repositório institucional de argumentos vencedores.
# Integrado ao RAG e à IA para reaproveitamento inteligente.
from __future__ import annotations
import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, Float, Integer, DateTime, ForeignKey, Enum as SAEnum, JSON,
)
from app.core.database import Base


class TeseTipo(str, enum.Enum):
    escritorio   = "escritorio"    # elaborada internamente
    sugerida_ia  = "sugerida_ia"  # gerada pela IA e validada
    doutrina     = "doutrina"     # fundamento doutrinário
    jurisprudencia = "jurisprudencia"  # baseada em julgado
    externa      = "externa"      # copiada de outro escritório / publicação


class TeseStatus(str, enum.Enum):
    rascunho  = "rascunho"
    ativa     = "ativa"
    arquivada = "arquivada"


# ── Banco Nacional de Teses Jurídicas (extensão aditiva — migração 148) ──────
# Vocabulário fechado em String (não enum PG), validado no schema/router —
# mesmo padrão já registrado para a migração 147 em MIGRATION_RESERVATIONS.md.
# NÃO confundir com TeseTipo/TeseStatus acima, que são os enums PG originais
# usados por services/sumulas_ingestion.py via SQL cru — nunca alterar aqueles.

ORIENTACOES = ("ataque", "defesa", "ambos")

# Ciclo de vida de validação de uma tese quanto à conferência contra fonte
# oficial. NULL = tese legada, criada antes desta extensão, não classificada.
STATUS_VALIDACAO = (
    "descoberta",
    "coletada",
    "normalizada",
    "parcialmente_validada",
    "validada",
    "revisada",
    "controvertida",
    "desatualizada",
    "parcialmente_superada",
    "superada",
    "arquivada",
)

# Transições permitidas por status_validacao atual. `None` representa uma
# tese legada (coluna ainda não classificada) — só pode entrar no ciclo por
# `coletada` ou `descoberta`.
TRANSICOES_VALIDACAO: dict[str | None, set[str]] = {
    None: {"descoberta", "coletada", "arquivada"},
    "descoberta": {"coletada", "controvertida", "arquivada"},
    "coletada": {"normalizada", "controvertida", "arquivada"},
    "normalizada": {"parcialmente_validada", "controvertida", "arquivada"},
    "parcialmente_validada": {"validada", "controvertida", "arquivada"},
    "validada": {"revisada", "desatualizada", "parcialmente_superada", "superada", "arquivada"},
    "revisada": {"desatualizada", "parcialmente_superada", "superada", "arquivada"},
    "controvertida": {"parcialmente_validada", "superada", "arquivada"},
    "desatualizada": {"normalizada", "arquivada"},
    "parcialmente_superada": {"superada", "arquivada"},
    "superada": {"arquivada"},
    "arquivada": set(),
}

# Transições que promovem a tese a um status de confiabilidade — exigem
# gate de verificação (verificador_jurisprudencia) e RBAC socio+ no router.
TRANSICOES_QUE_EXIGEM_VALIDACAO = {"validada", "revisada", "superada", "parcialmente_superada"}


class Tese(Base):
    __tablename__ = "teses"

    id           = Column(String(36), primary_key=True)
    titulo       = Column(String(300), nullable=False)
    descricao    = Column(Text, nullable=False)
    fundamentacao = Column(Text)           # artigos, súmulas, princípios
    jurisprudencia = Column(Text)          # julgados de suporte
    contra_argumento = Column(Text)        # o que o adversário pode responder
    area_juridica = Column(String(60))     # trabalhista, civel, ambiental...
    tribunal     = Column(String(120))     # ex: TRT-3, TJMG, STJ
    magistrado   = Column(String(200))     # magistrado associado (analytics)
    tags         = Column(Text)            # CSV: "responsabilidade,consumidor"
    observacoes  = Column(Text)

    tipo         = Column(SAEnum(TeseTipo),   nullable=False, default=TeseTipo.escritorio)
    status       = Column(SAEnum(TeseStatus), nullable=False, default=TeseStatus.ativa)

    # Métricas de desempenho
    vezes_usada  = Column(Integer, default=0, nullable=False)
    vezes_venceu = Column(Integer, default=0, nullable=False)
    vezes_perdeu = Column(Integer, default=0, nullable=False)
    taxa_sucesso = Column(Float)           # calculada: vezes_venceu/vezes_usada

    # Metadados
    created_by   = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                          onupdate=lambda: datetime.now(timezone.utc))
    deleted_at   = Column(DateTime(timezone=True), nullable=True)  # soft-delete

    # ── Extensão do Banco Nacional de Teses Jurídicas (migração 148) ──
    codigo       = Column(String(20), unique=True, nullable=True)   # ex.: BAN-000001
    orientacao   = Column(String(10), nullable=True)                # ataque|defesa|ambos — ver ORIENTACOES
    status_validacao = Column(String(25), nullable=True)            # ver STATUS_VALIDACAO/TRANSICOES_VALIDACAO
    score        = Column(Integer, nullable=True)
    score_calculos = Column(JSON, nullable=True)
    pressupostos = Column(Text)
    excecoes     = Column(Text)
    estrategia   = Column(Text)
    instancia    = Column(String(100))
    procedimento = Column(String(100))
    parte_favorecida = Column(String(100))
    requisitos   = Column(JSON, nullable=True)          # list[str]
    provas_necessarias = Column(JSON, nullable=True)    # list[str]
    riscos       = Column(JSON, nullable=True)          # list[str]
    fontes       = Column(JSON, nullable=True)          # [{referencia, situacao, url_oficial}]
    versao       = Column(Integer, default=1, nullable=False)
    ultima_validacao_em = Column(DateTime(timezone=True), nullable=True)
    validada_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    def __repr__(self):
        return f"<Tese {self.titulo[:40]}>"


class TeseCasoLink(Base):
    """Vínculo entre tese e caso (N:N) + resultado da aplicação."""
    __tablename__ = "tese_caso_links"

    id       = Column(String(36), primary_key=True)
    tese_id  = Column(String(36), ForeignKey("teses.id",  ondelete="CASCADE"), nullable=False)
    case_id  = Column(String(36), ForeignKey("cases.id",  ondelete="CASCADE"), nullable=False)
    resultado = Column(String(20))   # procedente | improcedente | acordo | pendente
    observacao = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
