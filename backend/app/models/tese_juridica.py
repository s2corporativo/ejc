# ── app/models/tese_juridica.py ─────────────────────────────────────
# Banco de Teses Jurídicas — modelo central para teses validadas.
from __future__ import annotations
import enum

from sqlalchemy import (
    Column, String, Text, Integer, Boolean, Float,
    Date, DateTime, ForeignKey, Enum as SAEnum, func, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSON
from app.core.database import Base
import uuid


class TipoTese(str, enum.Enum):
    """Classificação de tese: ataque, defesa, ou ambos."""
    ataque = "ataque"
    defesa = "defesa"
    ambos = "ambos"


class StatusTese(str, enum.Enum):
    """Status de validação da tese."""
    rascunho = "rascunho"
    em_revisao = "em_revisao"
    validada = "validada"
    nao_validada = "nao_validada"
    descontinuada = "descontinuada"


class Taxonomia(Base):
    """Classificação hierárquica de teses jurídicas: Área → Subárea → Tema."""
    __tablename__ = "taxonomias"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    area = Column(String(100), nullable=False)  # "Consumidor", "Bancário", etc.
    subarea = Column(String(100), nullable=False)  # "Crédito", "Fraude", etc.
    tema = Column(String(150), nullable=False)  # "Negativação Indevida", etc.
    subtema = Column(String(150))
    nivel = Column(Integer, default=1)  # Profundidade na hierarquia
    descricao = Column(Text)
    ativo = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("area", "subarea", "tema", "subtema", name="uq_taxonomia_path"),
    )


class TeseJuridica(Base):
    """Tese jurídica vencedora — registro principal com fundamentação, jurisprudência e score."""
    __tablename__ = "teses_juridicas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identificação
    titulo = Column(String(300), nullable=False)
    sumario = Column(String(500))  # Resumo executivo (~500 chars)

    # Classificação
    taxonomia_id = Column(UUID(as_uuid=True), ForeignKey("taxonomias.id"), nullable=False)
    tipo = Column(SAEnum(TipoTese, name="tipotese"), nullable=False)  # ataque/defesa/ambos
    parte_favorecida = Column(String(100))  # "Consumidor", "Devedor", "Réu", etc.
    procedimento = Column(String(100))  # "Ação ordinária", "JEC", "REsp", etc.
    instancia = Column(String(100))  # "1ª Instância", "STJ", "STF", etc.

    # Conteúdo jurídico
    tese_texto = Column(Text, nullable=False)  # Enunciado da tese (conciso)
    argumento = Column(Text)  # Fundamentação e argumentação detalhada
    pressupostos = Column(Text)  # Fatos e condições necessários para aplicação
    excecoes = Column(Text)  # Situações onde a tese NÃO se aplica
    estrategia = Column(Text)  # Quando aplicar, riscos, provas necessárias

    # Jurimetria e scoring
    score = Column(Integer, nullable=False, default=50)  # 0-100: força jurídica
    score_calculos = Column(JSON)  # {"norma": 30, "vinculante": 20, ...}
    decisoes_favoraveis = Column(Integer, default=0)
    decisoes_desfavoraveis = Column(Integer, default=0)
    decisoes_parciais = Column(Integer, default=0)
    taxa_sucesso = Column(Float)  # Proporção: favoráveis / total

    # Status e versioning
    status = Column(SAEnum(StatusTese, name="statustese"), nullable=False, default=StatusTese.rascunho)
    versao = Column(Integer, default=1)
    data_revisao = Column(DateTime(timezone=True))

    # Controle
    criada_por = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    revisada_por = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    auditada_por = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)


class FundamentacaoLegal(Base):
    """Dispositivos legais que fundamentam uma tese."""
    __tablename__ = "fundamentacoes_legais"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tese_id = Column(UUID(as_uuid=True), ForeignKey("teses_juridicas.id", ondelete="CASCADE"), nullable=False)

    norma = Column(String(50), nullable=False)  # "CF", "CDC", "CC", "CLT", etc.
    artigo = Column(String(20))
    paragrafo = Column(String(20))
    inciso = Column(String(20))
    alinea = Column(String(20))

    texto_relevante = Column(Text)  # Trecho exato da norma
    interpretacao = Column(Text)  # Como essa norma é interpretada na tese
    tipo = Column(String(50))  # "constitucional", "federal", "estadual", "súmula", etc.

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Precedente(Base):
    """Jurisprudência (acórdão, decisão, súmula) associada a uma tese."""
    __tablename__ = "precedentes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tese_id = Column(UUID(as_uuid=True), ForeignKey("teses_juridicas.id", ondelete="CASCADE"), nullable=False)

    # Identificação do julgado
    tribunal = Column(String(120), nullable=False)  # "STJ", "TJMG", "TRF1", etc.
    orgao_julgador = Column(String(150))  # "3ª Turma", "1ª Câmara Cível", etc.
    classe = Column(String(50))  # "REsp", "Apelação", "Agravo", etc.
    numero = Column(String(100))  # Número do processo/acórdão
    relator = Column(String(200))  # Nome do relator
    data_julgamento = Column(Date)
    data_publicacao = Column(Date)

    # Conteúdo
    ementa = Column(Text)  # Ementa oficial (resumo do julgado)
    ementa_resumida = Column(String(300))  # Versão curta (para painel de UI)

    # Tipo de relação com a tese
    tipo_relacao = Column(String(50))  # "favoravel", "desfavoravel", "parcial", "contradiz"
    vinculante = Column(Boolean, default=False)  # Súmula, decisão vinculante?

    # Fonte
    fonte_url = Column(Text)  # URL oficial (STJ, STF, tribunal)
    fonte = Column(String(50))  # "stj", "stf", "tjmg", "datajud", etc.

    # Jurimetria
    vezes_citada = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)


class ProcessoVitorioso(Base):
    """Caso real em que a tese foi vencedora (prova de aplicação prática)."""
    __tablename__ = "processos_vitoriosos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tese_id = Column(UUID(as_uuid=True), ForeignKey("teses_juridicas.id", ondelete="CASCADE"), nullable=False)

    tribunal = Column(String(120))
    classe = Column(String(50))
    numero = Column(String(100))
    resultado = Column(String(100))  # "Procedente", "Parcialmente procedente", etc.
    contexto = Column(Text)  # Resumo do caso (anônimizado)
    data_decisao = Column(Date)

    url = Column(Text)  # Link para a decisão (se pública)
    fonte = Column(String(50))  # "datajud", "tribunal", "manual", etc.

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ContratesesTese(Base):
    """Teses contrárias ou de defesa associadas a uma tese de ataque (e vice-versa)."""
    __tablename__ = "contrateses_tese"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tese_principal_id = Column(UUID(as_uuid=True), ForeignKey("teses_juridicas.id", ondelete="CASCADE"), nullable=False)
    tese_contraria_id = Column(UUID(as_uuid=True), ForeignKey("teses_juridicas.id", ondelete="CASCADE"), nullable=False)

    tipo_relacao = Column(String(50))  # "contraditoria", "complementar", "defesa_possivel"
    descricao = Column(Text)  # Descrição da relação

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("tese_principal_id", "tese_contraria_id", name="uq_contrateses_direcao"),
    )
