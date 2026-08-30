# ── app/models/saneamento.py ─────────────────────────────────────────────────
# Módulo de saneamento de base processual — tabelas próprias, prefixadas
# `saneamento_*` (migration 154_saneamento_schema; ver o docstring da
# migration para por que prefixo de tabela em vez de um schema Postgres
# dedicado — as ferramentas estáticas de paridade schema↔ORM do repositório
# não têm suporte a nomes qualificados por schema).
#
# Regra que os models por si só não impõem e cabe ao router respeitar: a
# coluna `decisao` de IndicativoEncerramento só é escrita por advogado
# autenticado (nunca por job); o banco reforça a metade que dá para reforçar
# via CHECK (decisao exige decidido_por + decidido_em — ver migration).
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from app.core.database import Base


class TpuMovimento(Base):
    """Catálogo TPU (Res. CNJ 46/2007) com classificação funcional revisada.

    Só sai de `nao_classificado` com revisão humana registrada (fonte +
    revisado_por). Ver docs/auditoria — código 246 é o único semeado pela
    migration; os demais entram via `scripts/carregar_tpu.py`.
    """

    __tablename__ = "saneamento_tpu_movimento"

    codigo = Column(Integer, primary_key=True)
    nome = Column(Text, nullable=False)
    classe = Column(String(20), nullable=False, server_default="nao_classificado")
    fonte = Column(Text, nullable=False, server_default="")
    revisado_por = Column(Text, nullable=True)
    revisado_em = Column(DateTime(timezone=True), nullable=True)
    atualizado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DatajudSnapshot(Base):
    """Cópia dos metadados retornados pelo DataJud para um número+grau."""

    __tablename__ = "saneamento_datajud_snapshot"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    numero_cnj = Column(String(20), nullable=False, index=True)
    # NOT NULL DEFAULT '' (sentinela "grau não informado"): permite uma
    # UniqueConstraint simples (numero_cnj, grau) na migration — Postgres
    # trataria NULL como sempre distinto em UNIQUE, abrindo brecha para
    # duplicata real com grau ausente.
    grau = Column(String(10), nullable=False, server_default="")
    tribunal = Column(Text, nullable=True)
    classe_codigo = Column(Integer, nullable=True)
    orgao_codigo = Column(Integer, nullable=True)
    data_ajuizamento = Column(DateTime(timezone=False), nullable=True)
    nivel_sigilo = Column(SmallInteger, nullable=False, server_default="0")
    payload = Column(JSONB, nullable=False)
    coletado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ExcecaoNumero(Base):
    """Fila de exceção: números que falharam na validação do DV — nunca duplicata."""

    __tablename__ = "saneamento_excecao_numero"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    id_interno = Column(Text, nullable=False)
    numero_bruto = Column(Text, nullable=False)
    motivo = Column(Text, nullable=False)
    resolvido = Column(Boolean, nullable=False, server_default="false")
    resolvido_por = Column(Text, nullable=True)
    resolvido_em = Column(DateTime(timezone=True), nullable=True)
    numero_corrigido = Column(String(20), nullable=True)
    criado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PlanoDedup(Base):
    """Proposta de deduplicação — nada é aplicado sem `aplicado_por` humano."""

    __tablename__ = "saneamento_plano_dedup"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    numero_cnj = Column(String(20), nullable=False, index=True)
    id_interno_principal = Column(Text, nullable=False)
    ids_absorvidos = Column(ARRAY(Text), nullable=False)
    tipo = Column(String(20), nullable=False)  # duplicata | multi_grau | conexo_sugerido
    aplicado = Column(Boolean, nullable=False, server_default="false")
    aplicado_por = Column(Text, nullable=True)
    aplicado_em = Column(DateTime(timezone=True), nullable=True)
    criado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class IndicativoEncerramento(Base):
    """Sinalização automática. `decisao` só é preenchida por advogado — nenhum
    job pode escrevê-la (regra de negócio inegociável do PROMPT 1, passo 5)."""

    __tablename__ = "saneamento_indicativo_encerramento"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    numero_cnj = Column(String(20), nullable=False, index=True)
    candidato = Column(Boolean, nullable=False)
    confianca = Column(String(10), nullable=False)  # alta | media | baixa | nenhuma
    motivos = Column(JSONB, nullable=False, server_default="[]")
    dias_de_silencio = Column(Integer, nullable=True)
    movimento_terminativo = Column(Integer, nullable=True)
    avaliado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Decisão humana. Enquanto NULL, o processo permanece ativo.
    decisao = Column(String(20), nullable=True)  # encerrar | manter_ativo
    decidido_por = Column(Text, nullable=True)
    decidido_em = Column(DateTime(timezone=True), nullable=True)
    justificativa = Column(Text, nullable=True)


class Divergencia(Base):
    """Divergência apontada pela reconciliação base interna × DataJud."""

    __tablename__ = "saneamento_divergencia"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    numero_cnj = Column(String(20), nullable=False, index=True)
    tipo = Column(Text, nullable=False)
    valor_interno = Column(JSONB, nullable=True)
    valor_datajud = Column(JSONB, nullable=True)
    observacao = Column(Text, nullable=False, server_default="")
    tratada = Column(Boolean, nullable=False, server_default="false")
    tratada_por = Column(Text, nullable=True)
    tratada_em = Column(DateTime(timezone=True), nullable=True)
    criado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Execucao(Base):
    """Log de execução das cargas/varreduras do módulo de saneamento."""

    __tablename__ = "saneamento_execucao"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tipo = Column(Text, nullable=False)
    iniciado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finalizado_em = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, server_default="em_andamento")
    processados = Column(Integer, nullable=False, server_default="0")
    falhas = Column(Integer, nullable=False, server_default="0")
    detalhe = Column(JSONB, nullable=False, server_default="{}")
