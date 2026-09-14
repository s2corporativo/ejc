from __future__ import annotations

from app.services.ai.core.ejc_skill_catalog import NativeSkillSpec, native_skill_specs

from .contracts import LegalSkillContract, SkillStatus


_DEFAULT_VERSION = "1.0.0"


def _contract_from_native(spec: NativeSkillSpec) -> LegalSkillContract:
    """Converte a skill canônica em contrato versionável sem copiar o Direito.

    Questões/evidências específicas são adicionadas por overlays curados; até lá
    o contrato permanece metodológico e não inventa fonte, precedente ou tese.
    """

    return LegalSkillContract(
        key=spec.name,
        version=_DEFAULT_VERSION,
        area=spec.area,
        display_name=spec.display_name,
        description=spec.description,
        issue_types=(),
        required_questions=(),
        required_evidence=(),
        source_refs=(),
        precedent_refs=(),
        thesis_refs=(),
        status=SkillStatus.ATIVA,
        requires_case=spec.requires_case,
        oab_restricted=spec.oab_restricted,
    )


def native_legal_skill_contracts() -> tuple[LegalSkillContract, ...]:
    """Snapshot versionado das skills existentes.

    Não cria outro registry: deriva a cada chamada da fonte canônica atual.
    """

    return tuple(_contract_from_native(spec) for spec in native_skill_specs())


def get_native_legal_skill_contract(name: str) -> LegalSkillContract | None:
    normalized = str(name or "").strip()
    for contract in native_legal_skill_contracts():
        if contract.key == normalized:
            return contract
    return None
