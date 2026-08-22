# ── app/models/legal_thesis_bank.py ───────────────────────────────────────────
# Banco Nacional de Teses Jurídicas — fundação canônica V1.
#
# Estas entidades não substituem `teses`, `jurisprudencias_internas` ou a
# matriz por caso. Elas formam a camada nacional, versionada e rastreável que
# será projetada no RAG somente depois dos gates de validação.
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


SOURCE_STATUSES = ("ativo", "pausado", "revisar", "descontinuado")
SNAPSHOT_STATUSES = ("capturado", "normalizado", "validado", "superado", "bloqueado")
PRECEDENT_STATUSES = (
    "nao_validado",
    "identificado",
    "validado",
    "revisar",
    "superado",
    "bloqueado",
)
THESIS_STATUSES = (
    "coletada",
    "em_analise",
    "parcialmente_validada",
    "validada",
    "revisada",
    "desatualizada",
    "superada",
    "arquivada",
)
THESIS_SIDES = ("ataque", "defesa", "ambos")
THESIS_KINDS = (
    "material",
    "processual",
    "probatoria",
    "subsidiaria",
    "reducao_de_pena",
)
THESIS_PRECEDENT_RELATIONS = (
    "favoravel",
    "contraria",
    "qualificada",
    "distinguishing",
)
THESIS_RELATIONS = (
    "depende_de",
    "contradiz",
    "complementa",
    "subsidiaria_de",
    "superada_por",
    "distingue_se_de",
    "precedente_comum",
)
VALIDATION_ACTIONS = (
    "coleta",
    "normalizacao",
    "validacao_fonte",
    "validacao_precedente",
    "revisao_humana",
    "aprovacao",
    "reprovacao",
    "marcacao_superada",
    "arquivamento",
)
INGESTION_STATUSES = ("em_processamento", "concluida", "parcial", "erro", "cancelada")


class LegalSource(Base):
    """Fonte primária/complementar autorizada e sua regra de conferência."""

    __tablename__ = "legal_sources"

    id = Column(String(36), primary_key=True)
    slug = Column(String(80), nullable=False, unique=True, index=True)
    nome = Column(String(255), nullable=False)
    categoria = Column(String(40), nullable=False)  # tribunal|legislacao|dados_publicos|doutrina
    autoridade = Column(String(255), nullable=True)
    tipo_acesso = Column(String(40), nullable=False)  # api|portal|arquivo|manual
    url_base = Column(Text, nullable=False)
    url_validacao = Column(Text, nullable=True)
    url_termos = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="ativo", index=True)
    exige_autenticacao = Column(Boolean, nullable=False, default=False)
    permite_uso_derivado = Column(Boolean, nullable=True)
    ultima_verificacao = Column(DateTime(timezone=True), nullable=True)
    observacoes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class LegalSourceSnapshot(Base):
    """Captura imutável de conteúdo/metadados em uma fonte."""

    __tablename__ = "legal_source_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "chave_origem",
            "hash_conteudo",
            name="uq_legal_source_snapshot_origin_hash",
        ),
    )

    id = Column(String(36), primary_key=True)
    source_id = Column(
        String(36),
        ForeignKey("legal_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chave_origem = Column(String(500), nullable=False, index=True)
    versao = Column(Integer, nullable=False, default=1)
    titulo = Column(String(500), nullable=True)
    conteudo_normalizado = Column(Text, nullable=False)
    hash_conteudo = Column(String(64), nullable=False, index=True)
    url_origem = Column(Text, nullable=True)
    data_publicacao = Column(Date, nullable=True)
    capturado_em = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(20), nullable=False, default="capturado", index=True)
    vigente = Column(Boolean, nullable=False, default=True, index=True)
    metadados = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class LegalPrecedent(Base):
    """Precedente normalizado, sempre apontando para uma captura de origem."""

    __tablename__ = "legal_precedents"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "chave_origem",
            name="uq_legal_precedent_source_origin",
        ),
    )

    id = Column(String(36), primary_key=True)
    source_id = Column(
        String(36),
        ForeignKey("legal_sources.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    snapshot_id = Column(
        String(36),
        ForeignKey("legal_source_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    chave_origem = Column(String(500), nullable=False)
    tribunal = Column(String(60), nullable=True, index=True)
    instancia = Column(String(40), nullable=True, index=True)
    orgao_julgador = Column(String(160), nullable=True)
    classe_processual = Column(String(120), nullable=True)
    numero_processo = Column(String(80), nullable=True, index=True)
    relator = Column(String(200), nullable=True)
    data_julgamento = Column(Date, nullable=True, index=True)
    data_publicacao = Column(Date, nullable=True)
    ementa = Column(Text, nullable=True)
    fundamento_relevante = Column(Text, nullable=True)
    resultado = Column(String(30), nullable=True)
    tema = Column(String(300), nullable=True, index=True)
    url_oficial = Column(Text, nullable=True)
    hash_conteudo = Column(String(64), nullable=True, index=True)
    status = Column(String(20), nullable=False, default="nao_validado", index=True)
    publicidade = Column(String(20), nullable=False, default="publico")
    dados_minimizados = Column(Boolean, nullable=False, default=True)
    observacoes_validacao = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class LegalThesis(Base):
    """Tese nacional estruturada; publicação automática exige status validado/revisado."""

    __tablename__ = "legal_theses"
    __table_args__ = (
        UniqueConstraint("chave_canonica", name="uq_legal_thesis_canonical_key"),
    )

    id = Column(String(36), primary_key=True)
    chave_canonica = Column(String(180), nullable=False, index=True)
    titulo = Column(String(500), nullable=False)
    area = Column(String(80), nullable=False, index=True)
    subarea = Column(String(120), nullable=True, index=True)
    instituto = Column(String(120), nullable=True)
    tema = Column(String(200), nullable=True, index=True)
    subtema = Column(String(200), nullable=True)
    situacao_fatica = Column(Text, nullable=True)
    tipo = Column(String(30), nullable=False, default="material")
    lado = Column(String(10), nullable=False, default="ambos", index=True)
    parte_favorecida = Column(String(80), nullable=True)
    procedimento = Column(String(100), nullable=True)
    instancia = Column(String(40), nullable=True)

    tese_principal = Column(Text, nullable=False)
    fundamento_resumido = Column(Text, nullable=True)
    argumento_juridico = Column(Text, nullable=True)
    raciocinio_juridico = Column(Text, nullable=True)
    pressupostos = Column(JSONB, nullable=False, default=list)
    fatos_necessarios = Column(JSONB, nullable=False, default=list)
    elementos_demonstrar = Column(JSONB, nullable=False, default=list)
    fatos_impeditivos = Column(JSONB, nullable=False, default=list)
    excecoes = Column(JSONB, nullable=False, default=list)
    fundamentacao_legal = Column(JSONB, nullable=False, default=list)
    estrategia = Column(JSONB, nullable=False, default=dict)
    provas_necessarias = Column(JSONB, nullable=False, default=list)
    documentos_necessarios = Column(JSONB, nullable=False, default=list)
    argumento_adversario = Column(Text, nullable=True)
    resposta_adversaria = Column(Text, nullable=True)
    riscos = Column(JSONB, nullable=False, default=list)

    score_forca = Column(Integer, nullable=False, default=0, index=True)
    status = Column(String(30), nullable=False, default="coletada", index=True)
    versao = Column(Integer, nullable=False, default=1)
    vigente = Column(Boolean, nullable=False, default=True, index=True)
    origem = Column(String(30), nullable=False, default="coleta")
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    revisado_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    criada_em = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revisada_em = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class LegalThesisVersion(Base):
    """Snapshot imutável de cada versão material da tese."""

    __tablename__ = "legal_thesis_versions"
    __table_args__ = (
        UniqueConstraint("thesis_id", "versao", name="uq_legal_thesis_version"),
    )

    id = Column(String(36), primary_key=True)
    thesis_id = Column(
        String(36),
        ForeignKey("legal_theses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    versao = Column(Integer, nullable=False)
    snapshot = Column(JSONB, nullable=False)
    motivo_alteracao = Column(Text, nullable=False)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class LegalThesisPrecedent(Base):
    """Ligação tese–precedente com papel favorável/contrário e trecho rastreável."""

    __tablename__ = "legal_thesis_precedents"
    __table_args__ = (
        UniqueConstraint("thesis_id", "precedent_id", name="uq_legal_thesis_precedent"),
    )

    id = Column(String(36), primary_key=True)
    thesis_id = Column(
        String(36),
        ForeignKey("legal_theses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    precedent_id = Column(
        String(36),
        ForeignKey("legal_precedents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    relacao = Column(String(30), nullable=False)
    trecho_relevante = Column(Text, nullable=True)
    observacao = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class LegalThesisRelation(Base):
    """Aresta do grafo de teses; o sentido é explícito e versionável."""

    __tablename__ = "legal_thesis_relations"
    __table_args__ = (
        UniqueConstraint(
            "source_thesis_id",
            "target_thesis_id",
            "relacao",
            name="uq_legal_thesis_relation",
        ),
    )

    id = Column(String(36), primary_key=True)
    source_thesis_id = Column(
        String(36),
        ForeignKey("legal_theses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_thesis_id = Column(
        String(36),
        ForeignKey("legal_theses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relacao = Column(String(30), nullable=False)
    justificativa = Column(Text, nullable=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class LegalThesisValidationEvent(Base):
    """Trilha de auditoria da vida da tese, do precedente ou da fonte."""

    __tablename__ = "legal_thesis_validation_events"

    id = Column(String(36), primary_key=True)
    thesis_id = Column(
        String(36),
        ForeignKey("legal_theses.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    precedent_id = Column(
        String(36),
        ForeignKey("legal_precedents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    snapshot_id = Column(
        String(36),
        ForeignKey("legal_source_snapshots.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    acao = Column(String(30), nullable=False)
    status_anterior = Column(String(30), nullable=True)
    status_novo = Column(String(30), nullable=True)
    justificativa = Column(Text, nullable=False)
    reviewer_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class LegalIngestionRun(Base):
    """Checkpoint de cada lote de coleta para retomada idempotente e auditável."""

    __tablename__ = "legal_ingestion_runs"

    id = Column(String(36), primary_key=True)
    source_id = Column(
        String(36),
        ForeignKey("legal_sources.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    lote_codigo = Column(String(100), nullable=False, index=True)
    status = Column(String(25), nullable=False, default="em_processamento", index=True)
    iniciado_em = Column(DateTime(timezone=True), nullable=False)
    finalizado_em = Column(DateTime(timezone=True), nullable=True)
    itens_consultados = Column(Integer, nullable=False, default=0)
    itens_importados = Column(Integer, nullable=False, default=0)
    duplicidades = Column(Integer, nullable=False, default=0)
    descartados = Column(Integer, nullable=False, default=0)
    erro = Column(Text, nullable=True)
    checkpoint = Column(JSONB, nullable=True)
    executado_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
