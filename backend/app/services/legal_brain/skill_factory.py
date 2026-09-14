from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .contracts import LegalSkillContract, SkillStatus

_SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class SkillFactoryError(ValueError):
    """Falha de contrato ao preparar uma skill jurídica para homologação."""


@dataclass(frozen=True)
class SkillCandidate:
    """Candidata imutável produzida por curadoria ou ferramenta assistida.

    A factory não cria conteúdo jurídico. Ela apenas valida estrutura,
    proveniência e completude mínima antes de produzir um contrato em
    ``HOMOLOGACAO``. A ativação permanece ato separado e humano.
    """

    key: str
    version: str
    area: str
    display_name: str
    description: str
    issue_types: tuple[str, ...]
    required_questions: tuple[str, ...]
    required_evidence: tuple[str, ...]
    source_refs: tuple[str, ...]
    precedent_refs: tuple[str, ...] = ()
    thesis_refs: tuple[str, ...] = ()
    contraindications: tuple[str, ...] = ()
    requires_case: bool = False
    oab_restricted: bool = True


def _clean_text(value: str, field: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise SkillFactoryError(f"{field} é obrigatório")
    return cleaned


def _clean_items(values: Iterable[str], field: str) -> tuple[str, ...]:
    cleaned = tuple(str(value or "").strip() for value in values)
    if any(not value for value in cleaned):
        raise SkillFactoryError(f"{field} contém item vazio")
    if len(set(cleaned)) != len(cleaned):
        raise SkillFactoryError(f"{field} contém duplicidade")
    return cleaned


def _require_items(values: Iterable[str], field: str) -> tuple[str, ...]:
    cleaned = _clean_items(values, field)
    if not cleaned:
        raise SkillFactoryError(f"{field} exige ao menos um item")
    return cleaned


def build_skill_for_homologation(candidate: SkillCandidate) -> LegalSkillContract:
    """Valida candidata e produz contrato fail-closed para homologação.

    Regras deliberadas:
    - nenhuma skill nasce ``ATIVA`` por esta factory;
    - fonte rastreável é obrigatória;
    - questões e evidências são obrigatórias;
    - precedente e tese são opcionais, mas, quando informados, precisam ter ID;
    - nenhum texto jurídico, precedente ou fonte é inferido pela factory.
    """

    key = _clean_text(candidate.key, "key")
    version = _clean_text(candidate.version, "version")
    if not _SEMVER_RE.fullmatch(version):
        raise SkillFactoryError("version deve seguir MAJOR.MINOR.PATCH")

    area = _clean_text(candidate.area, "area")
    display_name = _clean_text(candidate.display_name, "display_name")
    description = _clean_text(candidate.description, "description")

    issue_types = _require_items(candidate.issue_types, "issue_types")
    required_questions = _require_items(
        candidate.required_questions,
        "required_questions",
    )
    required_evidence = _require_items(
        candidate.required_evidence,
        "required_evidence",
    )
    source_refs = _require_items(candidate.source_refs, "source_refs")
    precedent_refs = _clean_items(candidate.precedent_refs, "precedent_refs")
    thesis_refs = _clean_items(candidate.thesis_refs, "thesis_refs")
    contraindications = _clean_items(
        candidate.contraindications,
        "contraindications",
    )

    return LegalSkillContract(
        key=key,
        version=version,
        area=area,
        display_name=display_name,
        description=description,
        issue_types=issue_types,
        required_questions=required_questions,
        required_evidence=required_evidence,
        contraindications=contraindications,
        source_refs=source_refs,
        precedent_refs=precedent_refs,
        thesis_refs=thesis_refs,
        status=SkillStatus.HOMOLOGACAO,
        requires_case=bool(candidate.requires_case),
        oab_restricted=bool(candidate.oab_restricted),
    )
