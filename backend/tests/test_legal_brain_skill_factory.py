from __future__ import annotations

import pytest

from app.services.legal_brain.contracts import LegalReference, SkillStatus
from app.services.legal_brain.skill_factory import (
    SkillCandidate,
    SkillFactoryError,
    build_skill_for_homologation,
)

_SOURCE_ID = "knowledge:source:synthetic-001"


def _candidate(**overrides: object) -> SkillCandidate:
    data: dict[str, object] = {
        "key": "skill.civil.exemplo",
        "version": "1.0.0",
        "area": "civil",
        "display_name": "Skill sintética",
        "description": "Candidata usada apenas em teste determinístico.",
        "issue_types": ("prova_onus_lacunas",),
        "required_questions": ("Qual fato precisa ser confirmado?",),
        "required_evidence": ("documento sintético identificado",),
        "source_refs": (_SOURCE_ID,),
        "precedent_refs": (),
        "thesis_refs": (),
        "contraindications": ("não usar sem fonte rastreável",),
        "requires_case": True,
        "oab_restricted": True,
    }
    data.update(overrides)
    return SkillCandidate(**data)


def _references(**overrides: object) -> dict[str, LegalReference]:
    data: dict[str, object] = {
        "source_id": _SOURCE_ID,
        "kind": "legislacao",
        "citation": "Fonte sintética de teste",
        "official": True,
        "verified_at": "2026-09-14T00:00:00+00:00",
        "legal_status": "vigente",
        "url": "https://example.invalid/synthetic",
    }
    data.update(overrides)
    reference = LegalReference(**data)
    return {_SOURCE_ID: reference}


def test_factory_nunca_ativa_skill_automaticamente() -> None:
    contract = build_skill_for_homologation(_candidate(), _references())

    assert contract.status is SkillStatus.HOMOLOGACAO
    assert contract.source_refs == (_SOURCE_ID,)
    assert contract.requires_case is True
    assert contract.oab_restricted is True


def test_factory_exige_fonte_rastreavel() -> None:
    with pytest.raises(SkillFactoryError, match="source_refs"):
        build_skill_for_homologation(
            _candidate(source_refs=()),
            _references(),
        )


def test_factory_exige_questoes_e_evidencias() -> None:
    with pytest.raises(SkillFactoryError, match="required_questions"):
        build_skill_for_homologation(
            _candidate(required_questions=()),
            _references(),
        )

    with pytest.raises(SkillFactoryError, match="required_evidence"):
        build_skill_for_homologation(
            _candidate(required_evidence=()),
            _references(),
        )


def test_factory_rejeita_referencias_duplicadas() -> None:
    with pytest.raises(SkillFactoryError, match="source_refs contém duplicidade"):
        build_skill_for_homologation(
            _candidate(source_refs=(_SOURCE_ID, _SOURCE_ID)),
            _references(),
        )


def test_factory_rejeita_semver_invalido() -> None:
    with pytest.raises(SkillFactoryError, match="MAJOR.MINOR.PATCH"):
        build_skill_for_homologation(
            _candidate(version="v1"),
            _references(),
        )


def test_factory_rejeita_source_ref_sem_catalogo() -> None:
    with pytest.raises(SkillFactoryError, match="sem referência resolvida"):
        build_skill_for_homologation(_candidate(), {})


def test_factory_rejeita_fonte_principal_nao_oficial() -> None:
    with pytest.raises(SkillFactoryError, match="não é oficial"):
        build_skill_for_homologation(
            _candidate(),
            _references(official=False),
        )


def test_factory_rejeita_fonte_sem_data_de_verificacao() -> None:
    with pytest.raises(SkillFactoryError, match="sem data de verificação"):
        build_skill_for_homologation(
            _candidate(),
            _references(verified_at=None),
        )


def test_factory_rejeita_norma_sem_vigencia_confirmada() -> None:
    with pytest.raises(SkillFactoryError, match="não confirmada como vigente"):
        build_skill_for_homologation(
            _candidate(),
            _references(legal_status="vigencia_nao_verificada"),
        )


def test_factory_normaliza_bordas_sem_inventar_conteudo() -> None:
    candidate = _candidate(
        key="  skill.civil.exemplo  ",
        source_refs=(f"  {_SOURCE_ID}  ",),
        precedent_refs=("  precedent:synthetic-001  ",),
        thesis_refs=("  thesis:synthetic-001  ",),
    )

    contract = build_skill_for_homologation(candidate, _references())

    assert contract.key == "skill.civil.exemplo"
    assert contract.source_refs == (_SOURCE_ID,)
    assert contract.precedent_refs == ("precedent:synthetic-001",)
    assert contract.thesis_refs == ("thesis:synthetic-001",)
    assert candidate.key == "  skill.civil.exemplo  "
