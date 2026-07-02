# ── app/models/client.py ─────────────────────────────────────────────────────
from __future__ import annotations
from sqlalchemy import Column, String, DateTime, Enum as SAEnum, func, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum


class ClientTipo(str, enum.Enum):
    PF = "PF"
    PJ = "PJ"


class ClientStatus(str, enum.Enum):
    lead      = "lead"        # primeiro contato / não convertido
    ativo     = "ativo"
    inativo   = "inativo"
    arquivado = "arquivado"


class ClientOrigem(str, enum.Enum):
    indicacao   = "indicacao"
    site        = "site"
    redes       = "redes_sociais"
    whatsapp    = "whatsapp"
    escritorio  = "escritorio"
    outro       = "outro"


class Client(Base):
    __tablename__ = "clients"

    id             = Column(String(36), primary_key=True)
    tipo           = Column(SAEnum(ClientTipo), nullable=False, default=ClientTipo.PF)

    # Campos PF
    nome           = Column(String(255), nullable=True, index=True)
    cpf            = Column(String(14),  nullable=True, unique=True, index=True)
    data_nascimento = Column(String(10), nullable=True)   # YYYY-MM-DD
    profissao      = Column(String(100), nullable=True)

    # Campos PJ
    razao_social   = Column(String(255), nullable=True)
    cnpj           = Column(String(18),  nullable=True, unique=True, index=True)
    nome_fantasia  = Column(String(255), nullable=True)

    # Contato (PF e PJ)
    email          = Column(String(255), nullable=True)
    telefone       = Column(String(30),  nullable=True)
    whatsapp       = Column(String(30),  nullable=True)

    # Endereço
    cep            = Column(String(9),   nullable=True)
    logradouro     = Column(String(255), nullable=True)
    numero         = Column(String(10),  nullable=True)
    complemento    = Column(String(100), nullable=True)
    bairro         = Column(String(100), nullable=True)
    cidade         = Column(String(100), nullable=True, default="Betim")
    estado         = Column(String(2),   nullable=True, default="MG")

    # CRM
    origem         = Column(SAEnum(ClientOrigem), nullable=True)
    status         = Column(SAEnum(ClientStatus), nullable=False, default=ClientStatus.ativo)
    observacoes    = Column(Text, nullable=True)
    # A FK para users.id EXISTE no banco desde a migration 001 (linha 85). O model
    # não a declarava — drift model↔banco (achado M9, Etapa 3). Declarar aqui apenas
    # informa o SQLAlchemy da constraint já existente; não gera DDL nem migração.
    responsavel_id = Column(String(36), ForeignKey("users.id"), nullable=True)

    created_at     = Column(DateTime(timezone=True), server_default=func.now())
    updated_at     = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at     = Column(DateTime(timezone=True), nullable=True)
    # Direito ao esquecimento (LGPD art. 17, migration 060). NULL = nunca
    # anonimizado. Preenchido = quando os campos de PII foram substituídos por
    # placeholders (ver services/client_anonimizacao.py). Registro não some —
    # relacionamentos (casos, financeiro) são preservados por obrigação legal.
    anonimizado_em = Column(DateTime(timezone=True), nullable=True)

    # Relacionamentos
    cases     = relationship("Case",      back_populates="client")
    documents = relationship("Document",  back_populates="client")
    fees      = relationship("Fee",       back_populates="client")

    @property
    def nome_exibicao(self) -> str:
        return self.nome or self.razao_social or "Cliente sem nome"

    def __repr__(self):
        return f"<Client {self.nome_exibicao} [{self.tipo}]>"
