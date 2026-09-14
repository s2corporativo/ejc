"""Núcleo determinístico do EJC Legal Brain.

Esta camada NÃO cria um segundo gateway de IA, RAG ou cadastro jurídico. Ela
organiza questões, evidências, pesquisa e validade de precedentes para consumo
pelo ``SingleAICoreOrchestrator`` e pelos módulos canônicos já existentes.

Princípios:
- fato, alegação, inferência e validação humana são estados distintos;
- referência jurídica é por ID/proveniência, nunca por cópia silenciosa;
- ausência de evidência gera lacuna, não conclusão;
- pesquisa tem critérios objetivos de parada;
- validade de precedente é proposicional e baseada em relações explícitas.
"""

from .brain import build_legal_brain_plan
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
from .issue_engine import identify_legal_issues
from .precedent_validity import evaluate_proposition_validity
from .research_loop import build_research_plan, evaluate_research_coverage

__all__ = [
    "EvidenceState",
    "LegalBrainPlan",
    "LegalIssue",
    "LegalReference",
    "LegalSkillContract",
    "PrecedentPropositionStatus",
    "ResearchPlan",
    "SkillStatus",
    "build_legal_brain_plan",
    "build_research_plan",
    "evaluate_proposition_validity",
    "evaluate_research_coverage",
    "identify_legal_issues",
]
