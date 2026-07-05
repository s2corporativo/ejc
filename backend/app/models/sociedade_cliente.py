# ── app/models/sociedade_cliente.py ──────────────────────────────────────────
# Gestão societária de CLIENTES empresariais (vertical Empresarial).
#
# NÃO confundir com app/routers/gestao_societaria.py (sócios DO ESCRITÓRIO,
# tabela office_partners): aqui o objeto é a SOCIEDADE DO CLIENTE — quadro
# societário, cap table e eventos societários das empresas atendidas.
#
# PII do sócio (LGPD): o documento (CPF/CNPJ) segue EXATAMENTE o padrão do
# models/client.py (Bloco 6a): NUNCA em texto puro no banco —
#   • documento_enc  — ciphertext Fernet (services/pii_crypto.encrypt);
#   • documento_hash — HMAC-SHA256 determinístico (índice cego p/ dedup);
#   • documento_mascarado — máscara de exibição (ex.: ***.456.789-**),
#     ÚNICO campo que sai nas respostas da API.
from __future__ import annotations
import enum

from sqlalchemy import (
    Column, String, Text, Numeric, Boolean, Date, DateTime, ForeignKey, func,
)
from app.core.database import Base


class TipoSocietario(str, enum.Enum):
    LTDA  = "LTDA"
    SA    = "SA"
    SLU   = "SLU"
    SS    = "SS"
    outro = "outro"


class TipoEventoSocietario(str, enum.Enum):
    alteracao_contratual = "alteracao_contratual"
    entrada_socio        = "entrada_socio"
    saida_socio          = "saida_socio"
    aumento_capital      = "aumento_capital"
    distribuicao_lucros  = "distribuicao_lucros"
    transformacao        = "transformacao"
    outro                = "outro"


class SociedadeCliente(Base):
    __tablename__ = "sociedades_cliente"

    id              = Column(String(36), primary_key=True)
    client_id       = Column(String(36), ForeignKey("clients.id"), nullable=False, index=True)
    razao_social    = Column(String(255), nullable=False)
    cnpj            = Column(String(18), nullable=True)   # dado público de PJ — sem criptografia
    # VARCHAR + enum Python (validação no schema Pydantic) em vez de pg ENUM:
    # evita gerenciar tipo nativo em migration idempotente; mesmo trade-off de
    # outras tabelas raw-SQL do projeto.
    tipo_societario = Column(String(20), nullable=False, default=TipoSocietario.LTDA.value)
    capital_social  = Column(Numeric(15, 2), nullable=True)

    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at      = Column(DateTime(timezone=True), nullable=True)  # soft delete


class SocioSociedade(Base):
    __tablename__ = "socios_sociedade"

    id            = Column(String(36), primary_key=True)
    sociedade_id  = Column(String(36), ForeignKey("sociedades_cliente.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    nome          = Column(String(255), nullable=False)
    quotas        = Column(Numeric(18, 2), nullable=False, default=0)
    pro_labore    = Column(Numeric(15, 2), nullable=True)
    administrador = Column(Boolean, nullable=False, default=False)

    # PII — padrão Bloco 6a (ver cabeçalho). Texto puro NUNCA é persistido.
    documento_enc       = Column(Text, nullable=True)          # Fernet — não indexável
    documento_hash      = Column(String(64), nullable=True, index=True)  # índice cego HMAC
    documento_mascarado = Column(String(32), nullable=True)    # exibição segura

    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EventoSocietario(Base):
    __tablename__ = "eventos_societarios"

    id           = Column(String(36), primary_key=True)
    sociedade_id = Column(String(36), ForeignKey("sociedades_cliente.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    tipo         = Column(String(30), nullable=False)  # TipoEventoSocietario (validação Pydantic)
    descricao    = Column(Text, nullable=True)
    data_evento  = Column(Date, nullable=False)
    created_by   = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
