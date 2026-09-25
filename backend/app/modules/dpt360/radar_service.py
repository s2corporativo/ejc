from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
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

from app.services.regulatory_area_classifier import (
    AREA_CASE_ALIASES as AREA_CASE_ALIASES,
    AREA_TERMS as AREA_TERMS,
    classify_area as classify_area,
    impact_level as impact_level,
)

def _areas_by_company_from_rows(rows: list) -> tuple[dict[str, set[str]], dict[str, str]]:
    """DER-01: compõe o índice empresa-areas e nomes a partir do resultado bruto
    da query de área visível, evitando que o dashboard (que já possui esse
    índice pela mesma RBAC) reexecute a consulta. O índice só pode ser
    originado por _visible_company_area_query ou pelo próprio radar.
    """
    areas_by_company: dict[str, set[str]] = defaultdict(set)
    company_names: dict[str, str] = {}
    for client_id, razao_social, nome_fantasia, area in rows:
        client_id_str = str(client_id)
        areas_by_company[client_id_str].add(_value(area))
        company_names[client_id_str] = (
            razao_social or nome_fantasia or "Empresa sem razão social"
        )
    return areas_by_company, company_names


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
    company_areas: dict[str, set[str]] | None = None,
    company_names: dict[str, str] | None = None,
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

    if company_areas is not None and company_names is not None:
        # DER-01: índice empresa-areas já computado pelo chamador (mesmo filtro
        # RBAC visível); evita reexecutar a query de área visível na mesma
        # requisição do dashboard. O índice deve ter sido derivado de
        # _visible_company_area_query para manter a paridade de escopo.
        areas_by_company = {key: set(value) for key, value in company_areas.items()}
        company_names = dict(company_names)
    else:
        company_area_rows = (await db.execute(_visible_company_area_query(user))).all()
        areas_by_company, company_names = _areas_by_company_from_rows(company_area_rows)

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
