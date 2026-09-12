# ── app/models/ajuizamento.py ────────────────────────────────────────────────
# Núcleo de ajuizamento e integração judicial (migration 157).
#
# Entidades PRÓPRIAS do fluxo de protocolo — nenhuma duplica cliente, caso,
# parte, advogado, documento ou peça: todas referenciam as tabelas canônicas
# (`clients`, `cases`, `case_partes`, `users`, `documents`, `legal_docs`).
#
# Segredos NUNCA entram aqui: `JudicialIntegrationProfile.client_id_ref` e
# `certificate_ref` são referências ao Cofre de Credenciais (provider_key/
# field_key) ou ao catálogo MNI (`credenciais_processo_eletronico`), jamais o
# valor. Tokens de acesso vivem só em memória, dentro do PdpjAuthProvider.
#
# Snapshot canônico (`judicial_filings.canonico`): CPF/CNPJ das partes ficam
# MASCARADOS no JSON (mesma máscara de pii_crypto.mascarar_documento) com o
# hash cego ao lado; o documento em claro é resolvido das entidades de origem
# só no instante do envio e nunca persiste fora de `clients`/`case_partes`.
from __future__ import annotations

import enum

from sqlalchemy import (
    JSON, Boolean, Column, DateTime, ForeignKey, Index, Integer, Numeric,
    String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class EstadoAjuizamento(str, enum.Enum):
    """Máquina de estados do ajuizamento (persistida; toda transição em
    `judicial_filing_transicoes`)."""
    DRAFT = "DRAFT"
    PREPARING = "PREPARING"
    VALIDATING = "VALIDATING"
    INVALID = "INVALID"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    APPROVED = "APPROVED"
    SIGNING = "SIGNING"
    READY_TO_SUBMIT = "READY_TO_SUBMIT"
    SUBMITTING = "SUBMITTING"
    SUBMITTED = "SUBMITTED"
    CONFIRMED = "CONFIRMED"
    SYNCING = "SYNCING"
    FAILED = "FAILED"
    REQUIRES_AUTHORIZATION = "REQUIRES_AUTHORIZATION"
    CANCELLED = "CANCELLED"


class SistemaJudicial(str, enum.Enum):
    pdpj = "pdpj"
    pje_mni = "pje_mni"
    eproc = "eproc"
    datajud = "datajud"
    manual = "manual"


class JudicialIntegrationProfile(Base):
    """Perfil de integração por tribunal/sistema/ambiente — cadastrado por
    administrador. `base_url` só aceita https sem IP privado (SSRF) e é a
    ÚNICA origem de endpoint remoto: nenhum conector tem endpoint fixo
    universal. Homologação é individual por TRF/TJ (`homologated_at`)."""
    __tablename__ = "judicial_integration_profiles"
    __table_args__ = (
        UniqueConstraint(
            "tribunal_code", "system", "degree", "environment",
            name="uq_judicial_profile_tribunal_sistema_grau_ambiente",
        ),
    )

    id = Column(String(36), primary_key=True)
    tribunal_code = Column(String(10), nullable=False, index=True)   # "TJMG", "TRF6"
    tribunal_nome = Column(String(120), nullable=True)
    segment = Column(String(30), nullable=False)                     # estadual|federal|trabalhista|...
    degree = Column(String(10), nullable=False, default="1")         # "1" | "2"
    system = Column(String(20), nullable=False)                      # SistemaJudicial
    environment = Column(String(20), nullable=False, default="homologacao")  # homologacao|producao
    integration_type = Column(String(30), nullable=False)            # rest|soap|portal
    base_url = Column(String(500), nullable=True)
    api_version = Column(String(20), nullable=True)
    auth_type = Column(String(30), nullable=False, default="none")   # none|oidc_client_credentials|mni_consultante|certificado
    # Referências ao cofre (provider_key:field_key) ou à credencial MNI — nunca valor.
    client_id_ref = Column(String(120), nullable=True)
    certificate_ref = Column(String(120), nullable=True)
    certificate_required = Column(Boolean, nullable=False, default=False)

    filing_supported = Column(Boolean, nullable=False, default=False)
    append_petition_supported = Column(Boolean, nullable=False, default=False)
    process_query_supported = Column(Boolean, nullable=False, default=False)
    movement_query_supported = Column(Boolean, nullable=False, default=False)
    document_download_supported = Column(Boolean, nullable=False, default=False)
    notice_query_supported = Column(Boolean, nullable=False, default=False)
    callback_supported = Column(Boolean, nullable=False, default=False)

    # Checklist de homologação (booleanos explícitos + JSON livre de evidências).
    authorized = Column(Boolean, nullable=False, default=False)
    production_endpoint_verified = Column(Boolean, nullable=False, default=False)
    credentials_valid = Column(Boolean, nullable=False, default=False)
    homologation_checklist = Column(JSON, nullable=True)
    homologated_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(30), nullable=False, default="REQUIRES_AUTHORIZATION")
    documentation_url = Column(String(500), nullable=True)
    ativo = Column(Boolean, nullable=False, default=True)

    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class JudicialFiling(Base):
    """Um ajuizamento (petição inicial) preparado a partir de um caso."""
    __tablename__ = "judicial_filings"

    id = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False, index=True)
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False, index=True)
    profile_id = Column(
        String(36), ForeignKey("judicial_integration_profiles.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    peticao_legal_doc_id = Column(String(36), ForeignKey("legal_docs.id"), nullable=True, index=True)

    estado = Column(String(30), nullable=False, default=EstadoAjuizamento.DRAFT.value, index=True)
    tribunal_code = Column(String(10), nullable=True)
    system = Column(String(20), nullable=True)
    segment = Column(String(30), nullable=True)
    degree = Column(String(10), nullable=True)
    environment = Column(String(20), nullable=True)
    jurisdicao = Column(String(120), nullable=True)      # comarca/seção judiciária
    codigo_localidade = Column(String(20), nullable=True)  # código IBGE/localidade do destino
    competencia = Column(String(120), nullable=True)
    competencia_codigo = Column(String(20), nullable=True)
    classe_codigo = Column(String(20), nullable=True)
    classe_nome = Column(String(200), nullable=True)
    assuntos = Column(JSON, nullable=True)               # [{codigo, nome, principal}]
    valor_causa = Column(Numeric(14, 2), nullable=True)
    nivel_sigilo = Column(Integer, nullable=False, default=0)
    gratuidade = Column(Boolean, nullable=False, default=False)
    tutela = Column(Boolean, nullable=False, default=False)
    prioridade = Column(String(40), nullable=True)
    caracteristicas = Column(JSON, nullable=True)        # campos extras exigidos pelo destino
    documentos = Column(JSON, nullable=True)             # [{document_id|legal_doc_id, document_type, tpu_document_type, ordem}]
    advogados = Column(JSON, nullable=True)              # [{user_id, tipo, procuracao_id}]

    canonico = Column(JSON, nullable=True)               # snapshot CanonicalJudicialCase (PII mascarada)
    canonico_hash = Column(String(64), nullable=True)
    preflight = Column(JSON, nullable=True)              # último resultado do validador
    assinatura = Column(JSON, nullable=True)             # evidência da assinatura (sem chave)

    aprovado_por = Column(String(36), nullable=True)
    aprovado_em = Column(DateTime(timezone=True), nullable=True)
    assinado_por = Column(String(36), nullable=True)
    assinado_em = Column(DateTime(timezone=True), nullable=True)
    protocolado_em = Column(DateTime(timezone=True), nullable=True)
    numero_cnj = Column(String(30), nullable=True, index=True)
    process_id = Column(String(36), ForeignKey("processes.id", ondelete="SET NULL"), nullable=True)
    ultimo_erro = Column(Text, nullable=True)

    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    case = relationship("Case")
    profile = relationship("JudicialIntegrationProfile")
    tentativas = relationship("JudicialFilingAttempt", back_populates="filing")
    transicoes = relationship("JudicialFilingTransicao", back_populates="filing")


class JudicialFilingTransicao(Base):
    """Histórico de transições da máquina de estados (uma linha por transição)."""
    __tablename__ = "judicial_filing_transicoes"

    id = Column(String(36), primary_key=True)
    filing_id = Column(String(36), ForeignKey("judicial_filings.id"), nullable=False, index=True)
    de_estado = Column(String(30), nullable=True)
    para_estado = Column(String(30), nullable=False)
    ator_id = Column(String(36), nullable=True)
    motivo = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    filing = relationship("JudicialFiling", back_populates="transicoes")


class JudicialFilingAttempt(Base):
    """Tentativa de envio a um conector — idempotente por `idempotency_key`."""
    __tablename__ = "judicial_filing_attempts"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_judicial_attempt_idempotency"),
        Index("ix_judicial_attempts_filing_numero", "filing_id", "numero"),
    )

    id = Column(String(36), primary_key=True)
    filing_id = Column(String(36), ForeignKey("judicial_filings.id"), nullable=False, index=True)
    numero = Column(Integer, nullable=False, default=1)
    connector = Column(String(20), nullable=False)
    idempotency_key = Column(String(64), nullable=False)
    request_hash = Column(String(64), nullable=True)
    response_hash = Column(String(64), nullable=True)
    estado = Column(String(30), nullable=False)          # resultado: SUBMITTED|CONFIRMED|FAILED|REQUIRES_AUTHORIZATION|TIMEOUT
    detalhe = Column(Text, nullable=True)
    external_protocol = Column(String(120), nullable=True)
    external_process_id = Column(String(120), nullable=True)
    iniciada_em = Column(DateTime(timezone=True), server_default=func.now())
    concluida_em = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(String(36), nullable=True)

    filing = relationship("JudicialFiling", back_populates="tentativas")


class JudicialProtocol(Base):
    """ProtocolRegistry — registro persistido do protocolo (sem segredo/token)."""
    __tablename__ = "judicial_protocols"
    __table_args__ = (
        Index("ix_judicial_protocols_case_cnj", "case_id", "cnj_number"),
    )

    id = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False, index=True)
    filing_id = Column(String(36), ForeignKey("judicial_filings.id"), nullable=False, index=True)
    attempt_id = Column(String(36), ForeignKey("judicial_filing_attempts.id", ondelete="SET NULL"), nullable=True)
    tribunal = Column(String(10), nullable=True)
    system = Column(String(20), nullable=False)
    environment = Column(String(20), nullable=True)
    connector = Column(String(20), nullable=False)
    idempotency_key = Column(String(64), nullable=True)
    external_protocol = Column(String(120), nullable=True)
    external_process_id = Column(String(120), nullable=True)
    cnj_number = Column(String(30), nullable=True, index=True)
    distribution_unit = Column(String(200), nullable=True)
    status = Column(String(30), nullable=False)          # SUBMITTED|CONFIRMED
    receipt_document_id = Column(String(36), nullable=True)   # Document (comprovante) — sem FK, padrão legal_docs
    request_hash = Column(String(64), nullable=True)
    response_hash = Column(String(64), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class JudicialSyncEvent(Base):
    """Eventos de sincronização pós-protocolo (fonte, dedupe, resultado)."""
    __tablename__ = "judicial_sync_events"

    id = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False, index=True)
    filing_id = Column(String(36), ForeignKey("judicial_filings.id", ondelete="SET NULL"), nullable=True, index=True)
    cnj_number = Column(String(30), nullable=True, index=True)
    fonte = Column(String(20), nullable=False)           # datajud|pje_mni|pdpj|manual
    estado = Column(String(20), nullable=False)          # ok|vazio|falha|desabilitado
    movimentos_novos = Column(Integer, nullable=False, default=0)
    detalhe = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class JudicialTpuItem(Base):
    """Cache local persistido da TPU (classes, assuntos, movimentos, documentos).
    Origem oficial: SGT/CNJ público (`CnjSgtClient`) — sincronização
    CONDITIONAL à flag `CNJ_SGT_ENABLED`; sem sync o serviço opera sobre o
    cache e a validação avisa que o código não foi verificado."""
    __tablename__ = "judicial_tpu_itens"
    __table_args__ = (
        UniqueConstraint("tipo", "codigo", name="uq_judicial_tpu_tipo_codigo"),
    )

    id = Column(String(36), primary_key=True)
    tipo = Column(String(12), nullable=False, index=True)   # classe|assunto|movimento|documento
    codigo = Column(String(20), nullable=False)
    descricao = Column(String(400), nullable=False)
    situacao = Column(String(20), nullable=False, default="ativo")   # ativo|inativo
    pai_codigo = Column(String(20), nullable=True)
    versao = Column(String(40), nullable=True)
    origem = Column(String(40), nullable=False, default="cnj_sgt")
    sincronizado_em = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
