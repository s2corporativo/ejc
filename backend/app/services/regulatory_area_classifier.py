"""Taxonomia compartilhada para classificação de impacto regulatório.

Extraída do radar DPT360 na refatoração EJC Core (#1843). O módulo é puro,
determinístico e não depende de banco, IA, DPT360 ou dados pessoais.
"""
from __future__ import annotations

import re

AREA_TERMS: dict[str, tuple[str, ...]] = {
    "tributario": (
        "tribut", "receita federal", "pgfn", "icms", "iss", "ibs", "cbs",
        "imposto", "contribuicao", "imposto seletivo", "split payment", "lc 214",
    ),
    "ambiental": (
        "ambient", "ibama", "conama", "semad", "feam", "ief", "igam", "copam",
        "licenciamento", "residuo",
    ),
    "administrativo": (
        "licit", "contrato administrativo", "tcu", "pncp",
        "administracao publica", "sancao administrativa",
    ),
    "trabalhista": (
        "trabalh", "emprego", "empregado", "sst", "seguranca do trabalho",
        "ministerio do trabalho", "fgts",
    ),
    "lgpd_ia": (
        "lgpd", "anpd", "dados pessoais", "inteligencia artificial",
        "sistema de ia", "algoritm",
    ),
}

AREA_CASE_ALIASES: dict[str, set[str]] = {
    "tributario": {"tributario"},
    "ambiental": {"ambiental"},
    "administrativo": {"administrativo", "licitacoes"},
    "trabalhista": {"trabalhista"},
    "lgpd_ia": {"digital_lgpd"},
}


def _normalize(value: str | None) -> str:
    raw = (value or "").lower()
    raw = (
        raw.replace("ç", "c")
        .replace("ã", "a")
        .replace("á", "a")
        .replace("â", "a")
    )
    raw = (
        raw.replace("é", "e")
        .replace("ê", "e")
        .replace("í", "i")
        .replace("ó", "o")
    )
    raw = raw.replace("ô", "o").replace("õ", "o").replace("ú", "u")
    return re.sub(r"\s+", " ", raw).strip()


def classify_area(*parts: str | None) -> str:
    haystack = _normalize(" ".join(part or "" for part in parts))
    scores: dict[str, int] = {}
    for area, terms in AREA_TERMS.items():
        score = sum(1 for term in terms if _normalize(term) in haystack)
        if score:
            scores[area] = score
    if not scores:
        return "geral"
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))[0][0]


def impact_level(area: str, company_case_areas: set[str]) -> str | None:
    aliases = AREA_CASE_ALIASES.get(area, set())
    if aliases & company_case_areas:
        return "alta"
    return None
