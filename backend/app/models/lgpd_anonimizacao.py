# ── app/models/lgpd_anonimizacao.py ──────────────────────────────────────────
"""
SUGESTÃO 17: Modo Quarentena para Dados Sensíveis (LGPD)

Modelos para gerenciar anonimização de dados pessoais antes de indexação no RAG.
Documentos com dados sensíveis são colocados em "quarentena" até que:
1. Dados pessoais sejam substituídos por tokens ([CPF_REDACTED], [NOME_REDACTED])
2. Original criptografado seja armazenado separadamente
3. Apenas usuários com permissão explícita possam acessar o original
"""
from __future__ import annotations
from sqlalchemy import Column, String, DateTime, Enum as SAEnum, func, Text, Boolean, ForeignKey, Integer
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum


class AnonimizacaoStatus(str, enum.Enum):
    """Status do processo de anonimização."""
    pendente = "pendente"           # Aguardando processamento
    em_processamento = "em_processamento"
    concluido = "concluido"         # Anonimizado e pronto para indexação
    revisao_necessaria = "revisao_necessaria"  # IA não teve certeza, precisa revisão humana
    falhou = "falhou"               # Erro no processo
    quarentena = "quarentena"       # Em quarentena aguardando decisão


class TipoDadoPessoal(str, enum.Enum):
    """Tipos de dados pessoais identificáveis."""
    cpf = "cpf"
    cnpj = "cnpj"
    rg = "rg"
    nome = "nome"
    endereco = "endereco"
    telefone = "telefone"
    email = "email"
    data_nascimento = "data_nascimento"
    nome_mae = "nome_mae"
    numero_processo = "numero_processo"
    banco = "banco"
    conta_corrente = "conta_corrente"
    pix = "pix"
    outro = "outro"


class DadoSensivelTipo(str, enum.Enum):
    """Categorias especiais de dados sensíveis (LGPD Art. 5º II)."""
    origem_racial = "origem_racial"
    etnica = "etnica"
    religiosa = "religiosa"
    politica = "politica"
    saude = "saude"
    vida_sexual = "vida_sexual"
    genetica = "genetica"
    biometrica = "biometrica"
    sindical = "sindical"


class DocumentoAnonimizado(Base):
    """
    Registro de anonimização de documentos para conformidade LGPD.
    
    Cada documento enviado ao EJC gera um registro aqui.
    O original fica imutável e criptografado.
    A versão anonimizade é usada para RAG e buscas.
    """
    __tablename__ = "documentos_anonimizados"

    id = Column(String(36), primary_key=True)
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False, index=True)
    
    # Status do processo
    status = Column(SAEnum(AnonimizacaoStatus), nullable=False, default=AnonimizacaoStatus.pendente)
    
    # Hash do original para integridade
    hash_original = Column(String(64), nullable=False)  # SHA-256 do arquivo original
    hash_anonimizado = Column(String(64), nullable=True)  # SHA-256 da versão anonimizade
    
    # Metadados do processamento
    processado_em = Column(DateTime(timezone=True), nullable=True)
    processado_por = Column(String(36), nullable=True)  # ID do usuário ou 'ia_gateway'
    
    # Contagem de dados encontrados
    total_dados_encontrados = Column(Integer, default=0)
    total_dados_anonimizados = Column(Integer, default=0)
    
    # Dados sensíveis específicos encontrados (JSON array)
    dados_sensiveis_encontrados = Column(Text, nullable=True)  # [{"tipo": "saude", "pagina": 3, ...}]
    
    # Nível de confiança da anonimização (0-100)
    confianca_anonimizacao = Column(Integer, nullable=True)  # 0-100
    
    # Se precisou de revisão humana
    revisao_human_necessaria = Column(Boolean, default=False)
    revisao_human_feita_por = Column(String(36), nullable=True)
    revisao_human_feita_em = Column(DateTime(timezone=True), nullable=True)
    observacoes_revisao = Column(Text, nullable=True)
    
    # Tokens de substituição usados (mapeamento reverso seguro)
    # Armazenado criptografado, apenas acessível com chave mestra
    mapeamento_tokens_criptografado = Column(Text, nullable=True)
    
    # Política de retenção
    retencao_dias = Column(Integer, default=365)  # Dias para manter na quarentena
    data_exclusao_programada = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relacionamentos
    document = relationship("Document", foreign_keys=[document_id])
    revisor = relationship("User", foreign_keys=[revisao_human_feita_por])


class RegistroAnonimizacao(Base):
    """
    Log detalhado de cada dado pessoal anonimizado.
    Auditoria completa para conformidade LGPD.
    """
    __tablename__ = "registros_anonimizacao"

    id = Column(String(36), primary_key=True)
    documento_anonimizado_id = Column(String(36), ForeignKey("documentos_anonimizados.id"), nullable=False, index=True)
    
    # Tipo de dado
    tipo_dado = Column(SAEnum(TipoDadoPessoal), nullable=False)
    dado_sensivel = Column(SAEnum(DadoSensivelTipo), nullable=True)
    
    # Localização no documento
    pagina = Column(Integer, nullable=True)
    posicao_inicio = Column(Integer, nullable=True)  # Caractere inicial
    posicao_fim = Column(Integer, nullable=True)    # Caractere final
    
    # Token gerado
    token_gerado = Column(String(50), nullable=False)  # Ex: [CPF_001_REDACTED]
    
    # Contexto (trecho redor, max 200 chars)
    contexto_antes = Column(String(200), nullable=True)
    contexto_depois = Column(String(200), nullable=True)
    
    # Método de detecção
    metodo_deteccao = Column(String(50), nullable=False)  # regex, ner_model, rule_based
    
    # Confiança da detecção (0-100)
    confianca = Column(Integer, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relacionamentos
    documento_anonimizado = relationship("DocumentoAnonimizado", back_populates="registros")


# Adicionar back_populates no modelo DocumentoAnonimizado
DocumentoAnonimizado.registros = relationship("RegistroAnonimizacao", back_populates="documento_anonimizado", cascade="all, delete-orphan")
