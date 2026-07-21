# ── app/models/client.py ─────────────────────────────────────────────────────
from __future__ import annotations
from sqlalchemy import Column, String, DateTime, Enum as SAEnum, func, Text, ForeignKey, Date, Index, text
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

    # Unicidade/dedup de cpf/cnpj é imposta EXCLUSIVAMENTE pelos índices cegos
    # de hash abaixo (ux_clients_*_hash). As colunas cpf/cnpj em TEXTO PURO e os
    # índices parciais sobre elas (uq_clients_cpf_active/uq_clients_cnpj_active,
    # migration 075) foram REMOVIDOS no cutover C6/LGPD (migration 112): CPF/CNPJ
    # não existem mais em claro no banco — só cifrados (cpf_enc/cnpj_enc) e
    # hasheados (cpf_hash/cnpj_hash). A leitura em claro é sob demanda via as
    # propriedades cpf_plain/cnpj_plain (decrypt).
    __table_args__ = (
        # #11/#12: dedup por HMAC (migration 061), com o predicado corrigido na
        # 079 para EXCLUIR soft-deleted (antes só `cpf_hash IS NOT NULL`, o que
        # impedia recadastrar o mesmo CPF após soft-delete que a 075 habilitou).
        # Declarados no ORM para o autogenerate NÃO emitir DROP INDEX destes
        # únicos parciais (perderia a unicidade de dedup). Pós-migration 112,
        # são a ÚNICA garantia de unicidade de documento entre clientes ativos.
        Index("ux_clients_cpf_hash", "cpf_hash", unique=True,
              postgresql_where=text("cpf_hash IS NOT NULL AND deleted_at IS NULL")),
        Index("ux_clients_cnpj_hash", "cnpj_hash", unique=True,
              postgresql_where=text("cnpj_hash IS NOT NULL AND deleted_at IS NULL")),
    )

    id             = Column(String(36), primary_key=True)
    tipo           = Column(SAEnum(ClientTipo), nullable=False, default=ClientTipo.PF)

    # Campos PF
    nome           = Column(String(255), nullable=True, index=True)
    data_nascimento = Column(Date, nullable=True)
    profissao      = Column(String(100), nullable=True)

    # Campos PJ
    razao_social   = Column(String(255), nullable=True)
    nome_fantasia  = Column(String(255), nullable=True)

    # Criptografia de PII em repouso (LGPD, achado C6 / migration 061). CUTOVER
    # concluído na migration 112: as colunas cpf/cnpj em TEXTO PURO foram
    # DROPADAS — a criptografia deixou de ser cosmética. cpf/cnpj passam a
    # existir SOMENTE cifrados (cpf_enc/cnpj_enc, Fernet) e hasheados
    # (cpf_hash/cnpj_hash, HMAC). Toda leitura em claro é sob demanda via as
    # propriedades cpf_plain/cnpj_plain (decrypt); busca/dedup/conflito usam o
    # hash. NÃO reintroduzir coluna de documento em texto puro.
    cpf_enc        = Column(Text, nullable=True)   # ciphertext Fernet, não indexável
    cnpj_enc       = Column(Text, nullable=True)
    # Índice declarado em __table_args__ (único parcial ux_clients_*_hash) — sem
    # index=True aqui para não gerar um ix_ redundante não-único (#11).
    cpf_hash       = Column(String(64), nullable=True)   # HMAC-SHA256 — busca exata/dedup
    cnpj_hash      = Column(String(64), nullable=True)

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
    # Funil de leads (CRMLeads/CentralRelacionamento — migration 087). Strings
    # livres validadas no schema Pydantic (etapa restrita a ETAPAS_FUNIL) para
    # não criar novo ENUM Postgres por valor de coluna de board.
    etapa_funil    = Column(String(20),  nullable=True, index=True)   # lead|contato|reuniao|proposta|convertido|perdido
    origem_lead    = Column(String(50),  nullable=True)               # ex.: "Indicação", "Instagram"
    area_interesse = Column(String(100), nullable=True)               # ex.: "Trabalhista"
    observacoes    = Column(Text, nullable=True)
    # A FK para users.id EXISTE no banco desde a migration 001 (linha 85). O model
    # não a declarava — drift model↔banco (achado M9, Etapa 3). Declarar aqui apenas
    # informa o SQLAlchemy da constraint já existente; não gera DDL nem migração.
    # index=True declara o ix_clients_responsavel_id criado na migration 076
    # (caminho quente); sem isto o autogenerate emitiria DROP INDEX (#11).
    responsavel_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)

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

    # ── Leitura em claro de CPF/CNPJ sob demanda (cutover C6/LGPD) ───────────
    # Fonte da verdade = cpf_enc/cnpj_enc (Fernet). Decifra só quando o valor em
    # claro é realmente necessário (resposta de API a quem tem acesso, geração
    # de peça/nota, export). Busca/dedup/conflito NÃO usam isto — usam o hash.
    # Import local: mantém o model livre de dependência de serviço no topo e
    # evita qualquer ciclo de import (mesmo padrão dos routers).
    @property
    def cpf_plain(self) -> str | None:
        from app.services.pii_crypto import decrypt
        return decrypt(self.cpf_enc)

    @property
    def cnpj_plain(self) -> str | None:
        from app.services.pii_crypto import decrypt
        return decrypt(self.cnpj_enc)

    @property
    def documento_plain(self) -> str | None:
        """CPF (PF) ou CNPJ (PJ) em claro — conveniência para os sites que antes
        faziam `c.cpf or c.cnpj`. PF-first, espelhando o comportamento legado."""
        return self.cpf_plain or self.cnpj_plain

    def __repr__(self):
        return f"<Client {self.nome_exibicao} [{self.tipo}]>"
