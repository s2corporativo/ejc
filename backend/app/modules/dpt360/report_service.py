from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.diario_oficial import DiarioOficialAlerta
from app.models.user import User
from app.modules.dpt360.access_scope import visible_alerts_query
from app.modules.dpt360.company_service import get_company_profile
from app.modules.dpt360.dashboard_service import build_dashboard, _is_critical_case
from app.modules.dpt360.radar_service import classify_area, impact_level


async def build_executive_report(
    db: AsyncSession,
    user: User,
    client_id: str,
    *,
    days: int = 30,
) -> dict[str, Any] | None:
    days = max(1, min(days, 90))
    profile = await get_company_profile(db, user, client_id)
    if profile is None:
        return None

    dashboard = await build_dashboard(db, user)
    cases = [item for item in dashboard.cases if item.client_id == client_id]
    case_ids = {item.id for item in cases}
    deadlines = [item for item in dashboard.deadlines if item.case_id in case_ids]
    company_case_areas = set(profile.areas_com_casos)

    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        await db.execute(
            visible_alerts_query(user)
            .where(DiarioOficialAlerta.created_at >= since)
            .order_by(
                DiarioOficialAlerta.data_publicacao.desc().nullslast(),
                DiarioOficialAlerta.created_at.desc(),
            )
            .limit(500)
        )
    ).scalars().all()

    changes: list[dict[str, Any]] = []
    for row in rows:
        area = classify_area(row.keyword_match, row.titulo, row.resumo)
        adherence = impact_level(area, company_case_areas)
        if adherence is None:
            continue
        changes.append(
            {
                "id": str(row.id),
                "fonte": row.fonte,
                "titulo": row.titulo,
                "area": area,
                "aderencia": adherence,
                "status": "possivel_impacto_requer_revisao",
                "data_publicacao": row.data_publicacao,
                "link": row.link,
            }
        )

    # O dashboard já classifica risco crítico somente para casos ativos. Reusar
    # a mesma regra evita que caso encerrado continue aparecendo como risco atual
    # no relatório executivo por carregar prioridade/risco histórico.
    critical = [item for item in cases if _is_critical_case(item)]
    today = datetime.now(timezone.utc).date()
    future = [item for item in deadlines if item.data_prazo >= today]

    return {
        "client_id": client_id,
        "empresa": profile.nome,
        "periodo_dias": days,
        "generated_at": datetime.now(timezone.utc),
        "status": "rascunho",
        "requer_revisao": True,
        # O relatório deriva casos/prazos do payload agregado do dashboard, que
        # tem teto de itens. Quando o dashboard reporta cobertura parcial, este
        # relatório pode estar omitindo casos/prazos mais antigos da empresa —
        # o rascunho precisa dizer isso, não parecer completo por omissão.
        "cobertura_completa": dashboard.coverage == "complete",
        "cobertura_notas": list(dashboard.notes),
        "situacao_juridica": [item.model_dump() for item in profile.health],
        "principais_riscos": [item.model_dump() for item in critical[:10]],
        "providencias_futuras": [item.model_dump() for item in future[:20]],
        "pendencias": {
            "prazos_pendentes": profile.prazos_pendentes,
            "documentos_vinculados_visiveis": profile.documentos,
            "dimensoes_sem_dados": [
                item.label for item in profile.twin if item.status == "sem_dados"
            ],
        },
        "casos": [item.model_dump() for item in cases[:30]],
        "mudancas_juridicas_relevantes": changes[:30],
        "recomendacoes": [
            "Revisar manualmente os riscos e prazos listados.",
            "Validar vigência e aplicabilidade das mudanças jurídicas antes de orientar o cliente.",
            "Completar dimensões do Legal Twin marcadas como sem dados quando forem relevantes ao escopo contratado.",
        ],
        "proximos_passos": [
            "Executar pré-flight jurídico antes da aprovação do relatório.",
            "Aprovar expressamente o conteúdo antes de qualquer compartilhamento externo.",
        ],
        "nota": "Rascunho determinístico baseado em registros canônicos e no escopo visível do usuário. Não é comunicação ao cliente nem parecer final.",
    }