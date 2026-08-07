# ── app/models/processo_eletronico.py ────────────────────────────────────────
# Integração de processo eletrônico via MNI 2.2.2 (Fase A — somente leitura).
#
# Issue #762 / migration 132_processo_eletronico_mni. Escopo desta fase:
# consultar processo/andamentos/documentos de tribunais que falam MNI
# (TJMG 1º/2º grau, catálogo em Tribunal) e refletir no EJC. NÃO cobre
# `entregarManifestacaoProcessual` (peticionamento) — fora de escopo, não
# implementar nem stub aqui.
#
# Segredos (id_consultante/senha) NUNCA em claro: cifrados com o mesmo
# padrão Fernet de app/services/pii_crypto.py (ver credential_vault.py para
# o cifrador dedicado desta tabela).
from __future__ import annotations

import enum

from sqlalchemy import (
    Boolean, Column, DateTime, Enum as SAEnum, ForeignKey, Integer,
    String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class TipoCredencialProcessoEletronico(str, enum.Enum):
    mni_sistema = "mni_sistema"  # idConsultante/senha emitido pelo tribunal
    certificado = "certificado"  # certificado digital A1/A3 (ref. ao arquivo, nunca a chave em claro)


class EscopoCredencialProcessoEletronico(str, enum.Enum):
    leitura = "leitura"
    leitura_peticionamento = "leitura_peticionamento"  # reservado — Fase A não usa


class StatusSincronizacaoProcesso(str, enum.Enum):
    sincronizando = "sincronizando"
    sincronizado = "sincronizado"
    erro = "erro"


class Tribunal(Base):
    """Catálogo de tribunais habilitados ao MNI (TribunalRegistry).

    `grau` distingue 1º/2º grau porque o MNI trata cada instância como
    endpoint/competência distintos (numeração CNJ, dígito J.TR muda o
    roteamento — ver services/tribunal_registry.py)."""
    __tablename__ = "tribunais"
    __table_args__ = (
        UniqueConstraint("codigo_tribunal", "grau", name="uq_tribunais_codigo_grau"),
    )

    id = Column(String(36), primary_key=True)
    nome = Column(String(120), nullable=False)
    # Código CNJ do tribunal (dígitos "TR" do número de processo, ex.: "13" p/ TJMG)
    codigo_tribunal = Column(String(4), nullable=False, index=True)
    grau = Column(String(10), nullable=False)  # "1" | "2"
    endpoint_wsdl = Column(String(500), nullable=False)
    versao_mni = Column(String(10), nullable=False, default="2.2.2")
    ativo = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    credenciais = relationship("CredencialProcessoEletronico", back_populates="tribunal")


class CredencialProcessoEletronico(Base):
    """Credencial de acesso ao MNI de um advogado num tribunal.

    id_consultante e senha_consultante_ref são cifrados em repouso (Fernet,
    mesmo padrão de pii_crypto.py) — ver services/credential_vault.py para
    cifra/decifra; nunca retornados em claro pela API (routers/schemas só
    expõem metadados)."""
    __tablename__ = "credenciais_processo_eletronico"
    __table_args__ = (
        UniqueConstraint(
            "tribunal_id", "advogado_id", "tipo",
            name="uq_credencial_tribunal_advogado_tipo",
        ),
    )

    id = Column(String(36), primary_key=True)
    tribunal_id = Column(String(36), ForeignKey("tribunais.id"), nullable=False, index=True)
    advogado_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    tipo = Column(SAEnum(TipoCredencialProcessoEletronico), nullable=False)
    # Cifrados (Fernet) — nunca em claro no banco nem na resposta da API.
    id_consultante_cifrado = Column(Text, nullable=True)
    senha_consultante_ref = Column(Text, nullable=True)
    certificado_ref = Column(Text, nullable=True)  # referência ao certificado (cofre/arquivo), nunca a chave privada

    escopo = Column(
        SAEnum(EscopoCredencialProcessoEletronico), nullable=False,
        default=EscopoCredencialProcessoEletronico.leitura,
    )
    ativo = Column(Boolean, nullable=False, default=True)
    ultima_verificacao = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tribunal = relationship("Tribunal", back_populates="credenciais")
    advogado = relationship("User")


class SincronizacaoProcessoEletronico(Base):
    """Estado de sincronização MNI por caso — tabela própria (não mistura com
    os campos DataJud/PJe já existentes em Case: fonte, protocolo e
    semântica de erro são diferentes; ver decisão no relatório da tarefa)."""
    __tablename__ = "sincronizacao_processo_eletronico"
    __table_args__ = (
        UniqueConstraint("case_id", name="uq_sincronizacao_processo_case"),
    )

    id = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False, index=True)
    tribunal_id = Column(String(36), ForeignKey("tribunais.id"), nullable=True, index=True)
    numero_cnj = Column(String(25), nullable=True, index=True)

    status = Column(
        SAEnum(StatusSincronizacaoProcesso), nullable=False,
        default=StatusSincronizacaoProcesso.sincronizando,
    )
    mensagem_erro = Column(Text, nullable=True)
    docs_novos = Column(Integer, nullable=False, default=0)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    case = relationship("Case")
    tribunal = relationship("Tribunal")


class DocumentoProcessoEletronicoDedup(Base):
    """Chave de dedup idDocumento(tribunal) → Document(EJC) para idempotência
    da sincronização (não recriar o mesmo documento em reprocessamentos)."""
    __tablename__ = "documentos_processo_eletronico_dedup"
    __table_args__ = (
        UniqueConstraint(
            "tribunal_id", "id_documento_tribunal",
            name="uq_dedup_tribunal_iddocumento",
        ),
    )

    id = Column(String(36), primary_key=True)
    tribunal_id = Column(String(36), ForeignKey("tribunais.id"), nullable=False, index=True)
    id_documento_tribunal = Column(String(60), nullable=False, index=True)
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False, index=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
