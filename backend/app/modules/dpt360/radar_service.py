from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.diario_oficial import DiarioOficialAlerta
from app.models.user import User
from app.modules.dpt360.access_scope import visible_alerts_query
from app.modules.dpt360.dashboard_service import (
    _value,
    _visible_business_cases_query,
    _visible_company_query,
)

AREA_TERMS: dict[str, tuple[str, ...]] = {
    "tributario": ("tribut", "receita federal", "pgfn", "icms", "iss", "ibs", "cbs", "imposto",
                   "contribuicao", "imposto seletivo", "split payment", "lc 214"),
    "ambiental": ("ambient", "ibama", "conama", "semad", "feam", "ief", "igam", "copam", "licenciamento", "residuo"),
    "administrativo": ("licit", "contrato administrativo", "tcu", "pncp", "administracao publica", "sancao administrativa"),
    "trabalhista": ("trabalh", "emprego", "empregado", "sst", "seguranca do trabalho", "ministerio do trabalho", "fgts"),
    "lgpd_ia": ("lgpd", "anpd", "dados pessoais", "inteligencia artificial", "sistema de ia", "algoritm"),
}

AREA_CASE_ALIASES = {
    "tributario": {"tributario"},
    "ambiental": {"ambiental"},
    "administrativo": {"administrativo", "licitacoes"},
    "trabalhista": {"trabalhista"},
    "lgpd_ia": {"digital_lgpd"},
}


def _normalize(value: str | None) -> str:
    raw = (value or "").lower()
    raw = raw.replace("ç", "c").replace("ã", "a").replace("á", "a").replace("â", "a")
    raw = raw.replace("é", "e").replace("ê", "e").replace("í", "i").replace("ó", "o")
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


async def build_today_radar(
    db: AsyncSession,
    user: User,
    *,
    hours: int = 24,
) -> dict[str, Any]:
    hours = max(1, min(hours, 168))
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    rows = (
        await db.execute(
            visible_alerts_query(user)
            .where(DiarioOficialAlerta.created_at >= since)
            .order_by(
                DiarioOficialAlerta.data_publicacao.desc().nullslast(),
                DiarioOficialAlerta.created_at.desc(),
            )
            .limit(300)
        )
    ).scalars().all()

    companies = (await db.execute(_visible_company_query(user))).scalars().all()
    company_ids = [item.id for item in companies]
    cases = []
    if company_ids:
        cases = (
            await db.execute(_visible_business_cases_query(user, company_ids))
        ).scalars().all()

    areas_by_company: dict[str, set[str]] = defaultdict(set)
    for case in cases:
        areas_by_company[case.client_id].add(_value(case.area))
    company_by_id = {item.id: item for item in companies}

    area_counts: Counter[str] = Counter()
    items: list[dict[str, Any]] = []
    impacted_company_ids: set[str] = set()

    for row in rows:
        area = classify_area(row.keyword_match, row.titulo, row.resumo)
        area_counts[area] += 1
        impacts = []
        for company_id, case_areas in areas_by_company.items():
            level = impact_level(area, case_areas)
            if level is None:
                continue
            company = company_by_id.get(company_id)
            if company is None:
                continue
            impacted_company_ids.add(company_id)
            impacts.append({
                "client_id": company_id,
                "empresa": company.razao_social or company.nome_fantasia or "Empresa sem razão social",
                "aderencia": level,
                "fundamento": f"A empresa possui caso canônico na área {area}; requer análise jurídica humana.",
                "status": "possivel_impacto",
            })
        items.append({
            "id": str(row.id),
            "fonte": row.fonte,
            "titulo": row.titulo,
            "resumo": row.resumo,
            "link": row.link,
            "data_publicacao": row.data_publicacao,
            "area": area,
            "estado_conhecimento": "CLASSIFICADO",
            "vigencia": "a_confirmar",
            "rag": "nao_promovido_por_este_endpoint",
            "impactos": impacts,
        })

    return {
        "generated_at": datetime.now(timezone.utc),
        "periodo_horas": hours,
        "total_publicacoes": len(rows),
        "por_area": dict(area_counts),
        "empresas_potencialmente_impactadas": len(impacted_company_ids),
        "itens": items[:100],
        "fontes_ativas": ["diario_oficial_alertas: DOU/DOE-MG"],
        "dependencias_pendentes": ["PR #895: gate de vigência RAG"],
        "regra_impacto": "Aderência só é exibida quando existe sinal objetivo no perfil/casos da empresa. Possível impacto não significa irregularidade.",
    }