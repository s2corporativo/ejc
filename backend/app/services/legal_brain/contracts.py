from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class EvidenceState(StrEnum):
    """Estado epistemológico de uma afirmação no caso.

    A enumeração é deliberadamente estrita para impedir que inferência de IA
    seja promovida implicitamente a fato confirmado.
    """

    CONFIRMADO = "confirmado"
    ALEGADO_CLIENTE = "alegado_cliente"
    ALEGADO_PARTE_CONTRARIA = "alegado_parte_contraria"
    CONTROVERTIDO = "controvertido"
    INFERENCIA_IA = "inferencia_ia"
    VALIDADO_ADVOGADO = "validado_advogado"
    DESCARTADO = "descartado"


class SkillStatus(StrEnum):
    RASCUNHO = "rascunho"
    HOMOLOGACAO = "homologacao"
    ATIVA = "ativa"
    REVISAO_NECESSARIA = "revisao_necessaria"
    APOSENTADA = "aposentada"


class PrecedentPropositionStatus(StrEnum):
    CONFIRMADA = "confirmada"
    DISTINGUIDA = "distinguida"
    LIMITADA = "limitada"
    SUPERADA = "superada"
    AFETADA_POR_TEMA = "afetada_por_tema"
    AFETADA_POR_SUMULA = "afetada_por_sumula"
    AFETADA_POR_ALTERACAO_LEGISLATIVA = "afetada_por_alteracao_legislativa"
    NAO_VERIFICADA = "nao_verificada"


@dataclass(frozen=True)
class LegalReference:
    """Referência por proveniência, sem duplicação do conteúdo jurídico."""

    source_id: str
    kind: str
    citation: str | None = None
    official: bool = False
    verified_at: str | None = None
    legal_status: str | None = None
    url: str | None = None


@dataclass(frozen=True)
class LegalIssue:
    """Questão jurídica candidata identificada de modo determinístico."""

    key: str
    title: str
    area: str
    question: str
    matched_terms: tuple[str, ...] = ()
    required_questions: tuple[str, ...] = ()
    required_evidence: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()


@dataclass(frozen=True)
class LegalSkillContract:
    """Contrato versionado de skill jurídica.

    A skill descreve método e referências. Ela não incorpora texto normativo ou
    jurisprudencial como verdade autônoma.
    """

    key: str
    version: str
    area: str
    display_name: str
    description: str
    issue_types: tuple[str, ...]
    required_questions: tuple[str, ...]
    required_evidence: tuple[str, ...]
    contraindications: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()
    precedent_refs: tuple[str, ...] = ()
    thesis_refs: tuple[str, ...] = ()
    status: SkillStatus = SkillStatus.HOMOLOGACAO
    requires_case: bool = False
    oab_restricted: bool = True


@dataclass(frozen=True)
class ResearchStep:
    order: int
    purpose: str
    query: str
    source_classes: tuple[str, ...]
    mandatory: bool = True


@dataclass(frozen=True)
class ResearchCoverage:
    primary_source: bool = False
    current_validity: bool = False
    supporting_precedent: bool = False
    adverse_precedent: bool = False
    factual_fit: bool = False

    @property
    def complete(self) -> bool:
        return all(
            (
                self.primary_source,
                self.current_validity,
                self.supporting_precedent,
                self.adverse_precedent,
                self.factual_fit,
            )
        )


@dataclass(frozen=True)
class ResearchPlan:
    issue_key: str
    area: str
    max_cycles: int
    steps: tuple[ResearchStep, ...]
    stop_when: tuple[str, ...]
    insufficient_evidence_message: str = (
        "EVIDÊNCIA JURÍDICA INSUFICIENTE PARA CONCLUSÃO SEGURA."
    )


@dataclass(frozen=True)
class PrecedentValidityResult:
    proposition_id: str
    status: PrecedentPropositionStatus
    decisive_relation: str | None = None
    related_source_ids: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class LegalBrainPlan:
    """Plano determinístico entregue ao núcleo único de IA."""

    area: str | None
    issues: tuple[LegalIssue, ...]
    native_skill_names: tuple[str, ...]
    research_plans: tuple[ResearchPlan, ...]
    warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
