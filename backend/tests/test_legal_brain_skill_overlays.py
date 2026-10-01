from app.core.taxonomia import AREAS_CANONICAS
from app.services.ai.core.ejc_skill_catalog import (
    LEGAL_AREA_SPECS,
    MODULE_SKILL_SPECS,
    native_skill_coverage,
)
from app.services.legal_brain.issue_engine import _RULES
from app.services.legal_brain.skill_contracts import (
    get_native_legal_skill_contract,
    native_legal_skill_contracts,
)


def test_todo_ramo_ja_curado_tem_overlay_metodologico_versionado():
    for area, spec in LEGAL_AREA_SPECS.items():
        contract = get_native_legal_skill_contract(spec.name)
        assert contract is not None, area
        assert contract.version == "1.1.0"
        assert contract.area == area
        assert contract.issue_types
        assert contract.required_questions
        assert contract.required_evidence
        # Overlay metodológico não pode fabricar autoridade jurídica.
        assert contract.source_refs == ()
        assert contract.precedent_refs == ()
        assert contract.thesis_refs == ()


def test_overlay_so_referencia_issue_type_existente_no_motor():
    valid_issue_keys = {rule.key for rule in _RULES}
    for spec in LEGAL_AREA_SPECS.values():
        contract = get_native_legal_skill_contract(spec.name)
        assert contract is not None
        assert set(contract.issue_types) <= valid_issue_keys


def test_modulos_nao_recebem_overlay_juridico_por_engano():
    for spec in MODULE_SKILL_SPECS.values():
        contract = get_native_legal_skill_contract(spec.name)
        assert contract is not None
        assert contract.version == "1.0.0"
        assert contract.issue_types == ()
        assert contract.required_questions == ()
        assert contract.required_evidence == ()


def test_todas_as_areas_canonicas_tem_skill_e_overlay_metodologico():
    coverage = native_skill_coverage()
    assert coverage["legal_areas"]["missing"] == []
    assert coverage["complete"] is True

    contracts = native_legal_skill_contracts()
    contract_areas = {
        contract.area for contract in contracts if contract.key.startswith("ramo_")
    }
    assert contract_areas == set(AREAS_CANONICAS)
