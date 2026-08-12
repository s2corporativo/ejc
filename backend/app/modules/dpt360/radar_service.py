from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import re
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ownership import is_gestao
from app.models.case import Case
from app.models.client import Client, ClientTipo
from app.models.diario_oficial import DiarioOficialAlerta
from app.models.user import User
from app.modules.dpt360.access_scope import visible_alerts_query
from app.modules.dpt360.dashboard_service import BUSINESS_AREAS, _value

RADAR_CLASSIFICATION_LIMIT = 300
RADAR_ITEM_LIMIT = 100

AREA_TERMS: dict[str, tuple[str, ...]] = {
    "tributario": (
        "tribut",
        "receita federal",
        "pgfn",
        "icms",
        "iss",
        "ibs",
        "cbs",
        "imposto",
        "contribuicao",
    ),
    "ambiental": (
        "ambient",
        "ibama",
        "conama",
        "semad",
        "feam",
        "ief",
        "igam",
        "copam",
        "licenciamento",
        "residuo",
    ),
    "administrativo": (
        "licit",
        "contrato administrativo",
        "tcu",
        "pncp",
        "administracao publica",
        "sancao administrativa",
    ),
    "trabalhista": (
        "trabalh",
        "emprego",
        "empregado",
        "sst",
        "seguranca do trabalho",
        "ministerio do trabalho",
        "fgts",
    ),
    "lgpd_ia": (
        "lgpd",
        "anpd",
        "dados pessoais",
        "inteligencia artificial",
        "sistema de ia",
        "algoritm",
    ),
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


def _visible_company_area_query(user: User):
    """Retorna apenas os campos necessários ao impacto do Radar.

    Evita reidratar Client e Case completos depois do dashboard. Para advogado,
    somente casos em que é responsável/auxiliar entram no índice; para gestão,
    todos os casos empresariais de clientes PJ visíveis pelo contrato DPT.
    """
    query = (
        select(
            Client.id.label("client_id"),
            Client.razao_social.label("razao_social"),
            Client.nome_fantasia.label("nome_fantasia"),
            Case.area.label("area"),
        )
        .join(Case, Case.client_id == Client.id)
        .where(
            Client.deleted_at.is_(None),
            Client.tipo == ClientTipo.PJ,
            Case.deleted_at.is_(None),
            Case.area.in_(BUSINESS_AREAS),
        )
    )
    if is_gestao(user):
        return query
    return query.where(
        or_(
            Case.advogado_responsavel_id == user.id,
            Case.advogado_auxiliar_id == user.id,
        )
    )


async def build_today_radar(
    db: AsyncSession,
    user: User,
    *,
    hours: int = 24,
) -> dict[str, Any]:
    hours = max(1, min(hours, 168))
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    alert_query = visible_alerts_query(user).where(
        DiarioOficialAlerta.created_at >= since
    )
    alert_count_sq = (
        alert_query.with_only_columns(DiarioOficialAlerta.id)
        .order_by(None)
        .subquery()
    )
    total_publicacoes = int(
        (await db.execute(select(func.count()).select_from(alert_count_sq))).scalar()
        or 0
    )

    rows = (
        await db.execute(
            alert_query.order_by(
                DiarioOficialAlerta.data_publicacao.desc().nullslast(),
                DiarioOficialAlerta.created_at.desc(),
            ).limit(RADAR_CLASSIFICATION_LIMIT)
        )
    ).scalars().all()

    coverage_partial = total_publicacoes > len(rows)

    company_area_rows = (await db.execute(_visible_company_area_query(user))).all()
    areas_by_company: dict[str, set[str]] = defaultdict(set)
    company_names: dict[str, str] = {}
    for company_id, razao_social, nome_fantasia, area in company_area_rows:
        company_id_str = str(company_id)
        areas_by_company[company_id_str].add(_value(area))
        company_names[company_id_str] = (
            razao_social or nome_fantasia or "Empresa sem razão social"
        )

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
            impacted_company_ids.add(company_id)
            impacts.append(
                {
                    "client_id": company_id,
                    "empresa": company_names[company_id],
                    "aderencia": level,
                    "fundamento": (
                        f"A empresa possui caso canônico na área {area}; "
                        "requer análise jurídica humana."
                    ),
                    "status": "possivel_impacto",
                }
            )
        items.append(
            {
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
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc),
        "periodo_horas": hours,
        "total_publicacoes": total_publicacoes,
        "publicacoes_classificadas": len(rows),
        "por_area": dict(area_counts),
        "empresas_potencialmente_impactadas": len(impacted_company_ids),
        "itens": items[:RADAR_ITEM_LIMIT],
        "cobertura": "parcial" if coverage_partial else "completa",
        "fontes_ativas": ["diario_oficial_alertas: DOU/DOE-MG"],
        "dependencias_pendentes": ["PR #895: gate de vigência RAG"],
        "regra_impacto": (
            "Aderência só é exibida quando existe sinal objetivo no perfil/casos "
            "da empresa. Possível impacto não significa irregularidade."
        ),
    }
