from __future__ import annotations

from dataclasses import dataclass

from app.core.taxonomia import AREAS_CANONICAS, MAPA_CANONICO_PARA_TRIAGEM
from app.services.system_prompts import SYSTEM_PROMPTS


@dataclass(frozen=True)
class AreaSpecializationRef:
    """Referência a um método jurídico já existente no núcleo único."""

    area: str
    prompt_key: str
    inherited_from: str | None = None
    source: str = "system_prompts"
    requires_human_review: bool = True


# Áreas canônicas que hoje não têm NativeSkillSpec próprio, mas cujo método já
# está versionado no repositório em SYSTEM_PROMPTS. Não há cópia do conteúdo.
_DIRECT_SPECIALIZATIONS: dict[str, str] = {
    "sucessoes": "sucessoes",
    "constitucional": "constitucional",
    "saude": "saude",
    "medico": "medico",
    "agrario": "agrario",
    "agronegocio": "agronegocio",
    "eleitoral": "eleitoral",
    "internacional": "internacional",
    "contratual": "contratual",
}

# Somente heranças já declaradas como juridicamente seguras pela taxonomia
# canônica. Não generalizar para áreas ambíguas.
_INHERITED_SPECIALIZATIONS: dict[str, tuple[str, str]] = {
    "societario": ("empresarial", "empresarial"),
    "licitacoes": ("administrativo", "administrativo"),
}


def resolve_area_specialization(area: str | None) -> AreaSpecializationRef | None:
    """Resolve especialização sem criar prompt, agente ou skill paralela.

    A função falha fechado se a área não for canônica ou se a chave do prompt
    tiver desaparecido da fonte canônica.
    """

    normalized = str(area or "").strip().lower()
    if normalized not in AREAS_CANONICAS:
        return None

    prompt_key = _DIRECT_SPECIALIZATIONS.get(normalized)
    inherited_from: str | None = None
    if prompt_key is None and normalized in _INHERITED_SPECIALIZATIONS:
        inherited_from, prompt_key = _INHERITED_SPECIALIZATIONS[normalized]
        # Defesa contra drift: a herança só continua válida enquanto a própria
        # taxonomia declarar a mesma convergência segura.
        if MAPA_CANONICO_PARA_TRIAGEM.get(normalized) != inherited_from:
            return None

    if not prompt_key or prompt_key not in SYSTEM_PROMPTS:
        return None
    return AreaSpecializationRef(
        area=normalized,
        prompt_key=prompt_key,
        inherited_from=inherited_from,
    )


def supplemental_area_coverage() -> dict[str, object]:
    """Cobertura das lacunas do catálogo sem maquiar a métrica nativa."""

    refs = [
        ref
        for area in AREAS_CANONICAS
        if (ref := resolve_area_specialization(area)) is not None
    ]
    covered = {ref.area for ref in refs}
    return {
        "covered": sorted(covered),
        "total": len(covered),
        "source": "system_prompts",
        "canonical_total": len(AREAS_CANONICAS),
    }
