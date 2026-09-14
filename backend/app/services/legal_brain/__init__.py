"""Núcleo determinístico do EJC Legal Brain.

Esta camada NÃO cria um segundo gateway de IA, RAG ou cadastro jurídico. Ela
organiza questões, evidências, pesquisa e validade de precedentes para consumo
pelo ``SingleAICoreOrchestrator`` e pelos módulos canônicos já existentes.

Princípios:
- fato, alegação, inferência e validação humana são estados distintos;
- referência jurídica é por ID/proveniência, nunca por cópia silenciosa;
- ausência de evidência gera lacuna, nunca conclusão;
- pesquisa tem critérios objetivos de parada;
- validade de precedente é proposicional e baseada em relações explícitas.
"""

from .area_specializations import (
    AreaSpecializationRef,
    resolve_area_specialization,
    supplemental_area_coverage,
)
from .brain import build_legal_brain_plan
from .case_state_bridge import CaseStateBridgeResult, bridge_legal_chat_state
from .contracts import (
    EvidenceState,
    LegalBrainPlan,
    LegalIssue,
    LegalReference,
    LegalSkillContract,
    PrecedentPropositionStatus,
    ResearchPlan,
    SkillStatus,
)
from .evidence import CaseAssertion, transition_assertion
from .issue_engine import identify_legal_issues
from .precedent_validity import evaluate_proposition_validity
from .rag_research import execute_research_plan_with_rag
from .research_loop import build_research_plan, evaluate_research_coverage
from .skill_contracts import (
    get_native_legal_skill_contract,
    native_legal_skill_contracts,
)
from .skill_factory import (
    SkillCandidate,
    SkillFactoryError,
    build_skill_for_homologation,
)

__all__ = [
    "AreaSpecializationRef",
    "CaseAssertion",
    "CaseStateBridgeResult",
    "EvidenceState",
    "LegalBrainPlan",
    "LegalIssue",
    "LegalReference",
    "LegalSkillContract",
    "PrecedentPropositionStatus",
    "ResearchPlan",
    "SkillCandidate",
    "SkillFactoryError",
    "SkillStatus",
    "bridge_legal_chat_state",
    "build_legal_brain_plan",
    "build_research_plan",
    "build_skill_for_homologation",
    "evaluate_proposition_validity",
    "evaluate_research_coverage",
    "execute_research_plan_with_rag",
    "get_native_legal_skill_contract",
    "identify_legal_issues",
    "native_legal_skill_contracts",
    "resolve_area_specialization",
    "supplemental_area_coverage",
    "transition_assertion",
]
