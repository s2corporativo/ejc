# ── app/models/tese_extensoes.py ─────────────────────────────────────────────
# Tabelas satélite do Banco Nacional de Teses Jurídicas (migração 148):
# fundamentações estruturadas, grafo de relações entre teses (inclui
# contratese), vínculo tese↔jurisprudência interna, evidência jurídica
# auditável e alertas do Radar Jurisprudencial. Todas keyed em `teses.id`
# (app/models/tese.py).
from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, JSON, Date, Boolean
from app.core.database import Base


class TeseFundamentacao(Base):
    """Dispositivo legal (norma/artigo/interpretação) que fundamenta uma tese."""
    __tablename__ = "teses_fundamentacoes"

    id           = Column(String(36), primary_key=True)
    tese_id      = Column(String(36), ForeignKey("teses.id", ondelete="CASCADE"), nullable=False)
    norma        = Column(String(120), nullable=False)   # "CDC", "CLT", "CF", "Súmula 297/STJ"...
    artigo       = Column(String(20))
    paragrafo    = Column(String(20))
    inciso       = Column(String(20))
    alinea       = Column(String(20))
    texto        = Column(Text)
    interpretacao = Column(Text)
    tipo         = Column(String(30))   # constituicao|lei_federal|lei_estadual|sumula|decreto|regulamento|principio
    created_by   = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class TeseRelacao(Base):
    """Grafo de relações entre teses — apoia, contradiz (cobre contratese),
    distingue, complementa, depende_de, supera, superada_por, alternativa,
    subsidiaria, mesma_questao."""
    __tablename__ = "teses_relacoes"

    id             = Column(String(36), primary_key=True)
    tese_origem_id  = Column(String(36), ForeignKey("teses.id", ondelete="CASCADE"), nullable=False)
    tese_destino_id = Column(String(36), ForeignKey("teses.id", ondelete="CASCADE"), nullable=False)
    tipo_relacao   = Column(String(30), nullable=False)
    observacao     = Column(Text)
    created_by     = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at     = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# Vocabulário fechado de teses_relacoes.tipo_relacao (validado no router/service).
TIPOS_RELACAO = (
    "apoia", "contradiz", "distingue", "complementa", "depende_de",
    "supera", "superada_por", "alternativa", "subsidiaria", "mesma_questao",
)


class TeseJurisprudenciaLink(Base):
    """Vínculo entre uma tese e um registro de jurisprudência interna."""
    __tablename__ = "teses_jurisprudencias"

    id                = Column(String(36), primary_key=True)
    tese_id           = Column(String(36), ForeignKey("teses.id", ondelete="CASCADE"), nullable=False)
    jurisprudencia_id = Column(String(36), ForeignKey("jurisprudencias_internas.id", ondelete="CASCADE"), nullable=False)
    tipo_relacao      = Column(String(20), nullable=False)   # favoravel|contrario|distinguishing
    observacao        = Column(Text)
    created_by        = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at        = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


TIPOS_RELACAO_JURISPRUDENCIA = ("favoravel", "contrario", "distinguishing")


class TeseAlertaJurisprudencial(Base):
    """Um alerta por decisão detectada pelo Radar Jurisprudencial.
    `teses_afetadas`/`casos_afetados` ficam em JSON pois uma única decisão
    pode impactar N teses e, por elas, N casos ativos."""
    __tablename__ = "teses_alertas_jurisprudenciais"

    id              = Column(String(36), primary_key=True)
    fonte           = Column(String(30), nullable=False)     # lexml|tjmg|...
    chave_dedup     = Column(String(200), nullable=False, unique=True)
    titulo          = Column(String(500))
    ementa          = Column(Text)
    tribunal        = Column(String(120))
    numero_processo = Column(String(120))
    link            = Column(Text)
    data_julgamento = Column(Date)
    severidade      = Column(String(10), nullable=False)     # critica|alta|media|baixa
    teses_afetadas  = Column(JSON, nullable=True)             # [{tese_id, titulo, score, termos_casados}]
    casos_afetados  = Column(JSON, nullable=True)             # [{case_id, numero_interno}]
    status          = Column(String(20), nullable=False, default="novo")  # novo|em_analise|tratado|descartado
    tratado_por     = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    tratado_em      = Column(DateTime(timezone=True), nullable=True)
    observacao      = Column(Text)
    created_at      = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


SEVERIDADES_ALERTA = ("critica", "alta", "media", "baixa")
STATUS_ALERTA = ("novo", "em_analise", "tratado", "descartado")


class LegalEvidence(Base):
    """Trilha de auditoria de PROVENIÊNCIA jurídica: de onde saiu cada
    afirmação registrada no Banco de Teses — fonte, quem coletou, quando,
    hash do conteúdo coletado, quem revisou. Produzida pelo pipeline de
    coleta (PR 3) e por conferências manuais.

    Não substitui `TeseJurisprudenciaLink` (vínculo tese↔jurisprudência já
    curada) — é o registro anterior a isso: `tese_id` é opcional porque uma
    evidência pode ser coletada antes de estar vinculada a uma tese
    específica."""
    __tablename__ = "legal_evidence"

    id           = Column(String(36), primary_key=True)
    tese_id      = Column(String(36), ForeignKey("teses.id", ondelete="SET NULL"), nullable=True)
    tipo_fonte   = Column(String(30), nullable=False)   # sumula|acordao|lei|decreto|tema_repetitivo|repercussao_geral|...
    tribunal     = Column(String(120))
    numero       = Column(String(120))                  # nº do processo/acórdão/súmula
    url_oficial  = Column(Text)
    data_consulta = Column(DateTime(timezone=True))      # quando a fonte foi consultada
    inteiro_teor_disponivel = Column(Boolean)
    orgao_julgador = Column(String(150))
    relator      = Column(String(200))
    data_julgamento = Column(Date)
    data_publicacao = Column(Date)
    status       = Column(String(20), nullable=False, default="coletada")  # ver STATUS_LEGAL_EVIDENCE
    trecho_relevante = Column(Text)
    hash_fingerprint = Column(String(64))                # sha256 do conteúdo coletado — integridade/dedup
    coletado_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    revisado_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    ultima_validacao_em = Column(DateTime(timezone=True), nullable=True)
    created_at   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# Vocabulário fechado de legal_evidence.status.
STATUS_LEGAL_EVIDENCE = ("coletada", "verificada", "desatualizada", "invalida")
