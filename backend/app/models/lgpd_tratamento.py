# ── app/models/lgpd_tratamento.py ─────────────────────────────────────────────
# LGPD como VERTICAL DE PRODUTO — Registro de Operações de Tratamento (ROPA,
# art. 37 da LGPD) por CLIENTE. É o entregável real de uma adequação: o mapa das
# operações de tratamento de dados pessoais que o cliente realiza, base do
# Relatório de Impacto (RIPD, art. 38).
#
# ⚠ PRIVACIDADE — NENHUM dado pessoal de titular real é armazenado aqui.
# Cada linha é METADADO DA OPERAÇÃO: descreve CATEGORIAS de dados ("nome, CPF,
# e-mail") e CATEGORIAS de titulares ("clientes, funcionários"), NUNCA valores
# concretos (nenhum CPF/e-mail de pessoa real). O ROPA cataloga tratamentos —
# não é um banco de dados pessoais. Por isso não há criptografia de PII aqui
# (diferente de socios_sociedade): não existe PII para proteger.
#
# Espelha a arquitetura de models/sociedade_cliente.py: FK clients, soft delete,
# VARCHAR + enum Python (validação no schema Pydantic) em vez de ENUM nativo.
from __future__ import annotations
import enum

from sqlalchemy import (
    Column, String, Text, Boolean, DateTime, ForeignKey, func,
)
from app.core.database import Base


class BaseLegal(str, enum.Enum):
    """Hipóteses legais de tratamento (art. 7º LGPD; dados sensíveis: art. 11)."""
    consentimento       = "consentimento"
    contrato            = "contrato"
    obrigacao_legal     = "obrigacao_legal"
    legitimo_interesse  = "legitimo_interesse"
    exercicio_direitos  = "exercicio_direitos"
    protecao_vida       = "protecao_vida"
    tutela_saude        = "tutela_saude"
    politica_publica    = "politica_publica"
    pesquisa            = "pesquisa"
    credito             = "credito"


class NivelRisco(str, enum.Enum):
    baixo = "baixo"
    medio = "medio"
    alto  = "alto"


class RegistroTratamento(Base):
    __tablename__ = "lgpd_registros_tratamento"

    id                        = Column(String(36), primary_key=True)
    client_id                 = Column(String(36), ForeignKey("clients.id"),
                                       nullable=False, index=True)
    nome_operacao             = Column(String(255), nullable=False)
    finalidade                = Column(Text, nullable=False)
    # VARCHAR + enum Python (validação no schema Pydantic) — mesmo trade-off das
    # demais tabelas raw-SQL do projeto (evita ENUM nativo em migration idempotente).
    base_legal                = Column(String(30), nullable=False)   # BaseLegal
    categorias_dados          = Column(Text, nullable=False)   # ex.: "nome, CPF, e-mail" (categorias, não valores)
    categorias_titulares      = Column(Text, nullable=False)   # ex.: "clientes, funcionários"
    dados_sensiveis           = Column(Boolean, nullable=False, default=False)
    compartilhamento          = Column(Text, nullable=True)    # com quem os dados são compartilhados
    transferencia_internacional = Column(Boolean, nullable=False, default=False)
    paises_transferencia      = Column(Text, nullable=True)
    prazo_retencao            = Column(Text, nullable=False)
    medidas_seguranca         = Column(Text, nullable=False)
    risco                     = Column(String(10), nullable=False,
                                       default=NivelRisco.baixo.value)  # calculado no service

    created_at                = Column(DateTime(timezone=True), server_default=func.now())
    updated_at                = Column(DateTime(timezone=True), server_default=func.now(),
                                       onupdate=func.now())
    deleted_at                = Column(DateTime(timezone=True), nullable=True)  # soft delete
