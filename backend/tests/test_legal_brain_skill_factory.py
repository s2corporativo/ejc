from __future__ import annotations

import pytest

from app.services.legal_brain.contracts import SkillStatus
from app.services.legal_brain.skill_factory import (
    SkillCandidate,
    SkillFactoryError,
    build_skill_for_homologation,
)


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
        "source_refs": ("knowledge:source:synthetic-001",),
        "precedent_refs": (),
        "thesis_refs": (),
        "contraindications": ("não usar sem fonte rastreável",),
        "requires_case": True,
        "oab_restricted": True,
    }
    data.update(overrides)
    return SkillCandidate(**data)


def test_factory_nunca_ativa_skill_automaticamente() -> None:
    contract = build_skill_for_homologation(_candidate())

    assert contract.status is SkillStatus.HOMOLOGACAO
    assert contract.source_refs == ("knowledge:source:synthetic-001",)
    assert contract.requires_case is True
    assert contract.oab_restricted is True


def test_factory_exige_fonte_rastreavel() -> None:
    with pytest.raises(SkillFactoryError, match="source_refs"):
        build_skill_for_homologation(_candidate(source_refs=()))


def test_factory_exige_questoes_e_evidencias() -> None:
    with pytest.raises(SkillFactoryError, match="required_questions"):
        build_skill_for_homologation(_candidate(required_questions=()))

    with pytest.raises(SkillFactoryError, match="required_evidence"):
        build_skill_for_homologation(_candidate(required_evidence=()))


def test_factory_rejeita_referencias_duplicadas() -> None:
    with pytest.raises(SkillFactoryError, match="source_refs contém duplicidade"):
        build_skill_for_homologation(
            _candidate(
                source_refs=(
                    "knowledge:source:synthetic-001",
                    "knowledge:source:synthetic-001",
                )
            )
        )


def test_factory_rejeita_semver_invalido() -> None:
    with pytest.raises(SkillFactoryError, match="MAJOR.MINOR.PATCH"):
        build_skill_for_homologation(_candidate(version="v1"))


def test_factory_normaliza_bordas_sem_inventar_conteudo() -> None:
    candidate = _candidate(
        key="  skill.civil.exemplo  ",
        source_refs=("  knowledge:source:synthetic-001  ",),
        precedent_refs=("  precedent:synthetic-001  ",),
        thesis_refs=("  thesis:synthetic-001  ",),
    )

    contract = build_skill_for_homologation(candidate)

    assert contract.key == "skill.civil.exemplo"
    assert contract.source_refs == ("knowledge:source:synthetic-001",)
    assert contract.precedent_refs == ("precedent:synthetic-001",)
    assert contract.thesis_refs == ("thesis:synthetic-001",)
    assert candidate.key == "  skill.civil.exemplo  "
