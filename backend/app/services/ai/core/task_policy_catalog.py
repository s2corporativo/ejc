"""Catálogo declarativo de governança das tarefas do Núcleo Único de IA.

Não executa modelo, não contém prompt e não substitui o classificador, registro
de agentes, provider policy ou orquestrador. Apenas consolida metadados e regras
transversais auditáveis sobre as fontes já existentes.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Literal, cast

from fastapi import HTTPException

from app.services.ai.core.agent_registry import AGENT_REGISTRY, AgenteInterno

IntelligenceLevel = Literal["padrao", "alto", "maximo"]
RAGPolicy = Literal["optional", "recommended", "required"]
Sensitivity = Literal["normal", "confidential", "restricted", "internal"]

_LEVEL_RANK: dict[str, int] = {"padrao": 1, "alto": 2, "maximo": 3}
_CANONICAL_BY_AGENT: dict[str, str] = {
    "EJCCoordinatorAgent": "ejc_coordination",
    "CaseAgent": "case_analysis",
    "ProcessAgent": "process_analysis",
    "DocumentAgent": "document_analysis",
    "LegalWritingAgent": "legal_draft",
    "RAGResearchAgent": "legal_research",
    "JurimetryAgent": "jurimetry",
    "FinanceAgent": "financial_analysis",
    "BankForensicsAgent": "bank_forensics",
    "ClientCommunicationAgent": "client_communication",
    "SystemHealthAgent": "system_health",
    "RepairAgent": "repair_plan",
    "UIUXAgent": "uiux_review",
    "SecurityLGPDOABAgent": "security_audit",
}
_CONFIDENTIAL_AGENTS = {
    "BankForensicsAgent",
    "CriminalLawAgent",
    "FamilyLawAgent",
    "MedicalLawAgent",
    "DigitalLGPDAgent",
}
_RESTRICTED_AGENTS = {
    "SecurityLGPDOABAgent",
    "SystemHealthAgent",
    "RepairAgent",
}
_TECHNICAL_AGENTS = {"SystemHealthAgent", "RepairAgent", "UIUXAgent"}


@dataclass(frozen=True)
class TaskPolicy:
    canonical_task: str
    purpose: str
    agent: str
    source_required: bool
    rag_policy: RAGPolicy
    minimum_intelligence: IntelligenceLevel
    sensitivity: Sensitivity
    hitl_required: bool
    canonical_endpoint: str = "/api/v1/ai/core/task"

    def public_dict(self) -> dict:
        """Somente metadados; nunca prompt, modelo, chave ou handler."""
        return asdict(self)


def _snake_agent_name(name: str) -> str:
    stem = name.removesuffix("Agent")
    return re.sub(r"(?<!^)(?=[A-Z])", "_", stem).lower()


def _canonical_task(agent: AgenteInterno) -> str:
    # Mapeia os domínios transversais para nomes públicos estáveis. Para cada
    # especialista jurídico não listado, usa o próprio nome do agente em snake
    # case, garantindo unicidade sem duplicar a taxonomia do intent classifier.
    return _CANONICAL_BY_AGENT.get(agent.nome, _snake_agent_name(agent.nome))


def _sensitivity(agent_name: str) -> Sensitivity:
    if agent_name in _RESTRICTED_AGENTS:
        return "restricted"
    if agent_name in _CONFIDENTIAL_AGENTS:
        return "confidential"
    if agent_name in _TECHNICAL_AGENTS:
        return "internal"
    return "normal"


def _rag_policy(agent: AgenteInterno) -> RAGPolicy:
    if agent.nome == "RAGResearchAgent":
        return "required"
    if agent.exige_fonte:
        return "recommended"
    return "optional"


def _minimum_intelligence(agent: AgenteInterno) -> IntelligenceLevel:
    if agent.nome in {"RepairAgent", "JurimetryAgent", "LegalWritingAgent"}:
        return "alto"
    if agent.exige_fonte:
        return "alto"
    return "padrao"


def resolve_task_policy(agent_name: str) -> TaskPolicy:
    agent = AGENT_REGISTRY.get(agent_name)
    if agent is None:
        raise KeyError(f"Agente não registrado: {agent_name}")
    return TaskPolicy(
        canonical_task=_canonical_task(agent),
        purpose=agent.descricao,
        agent=agent.nome,
        source_required=bool(agent.exige_fonte),
        rag_policy=_rag_policy(agent),
        minimum_intelligence=_minimum_intelligence(agent),
        sensitivity=_sensitivity(agent.nome),
        hitl_required=True,
    )


def effective_intelligence(
    requested: str,
    policy: TaskPolicy,
) -> IntelligenceLevel:
    value = (requested or "alto").strip().lower()
    if value not in _LEVEL_RANK:
        raise HTTPException(
            422,
            "Nível de inteligência inválido. Use: padrao, alto ou maximo.",
        )
    minimum = policy.minimum_intelligence
    effective = minimum if _LEVEL_RANK[value] < _LEVEL_RANK[minimum] else value
    return cast(IntelligenceLevel, effective)


def effective_rag(requested: bool, policy: TaskPolicy) -> bool:
    return True if policy.rag_policy == "required" else bool(requested)


def list_task_policies() -> list[dict]:
    return [
        resolve_task_policy(name).public_dict()
        for name in sorted(AGENT_REGISTRY)
    ]
