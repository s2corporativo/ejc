from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case
from app.models.diario_oficial import DiarioOficialAlerta
from app.models.deadline import Deadline, DeadlineStatus
from app.models.user import User
from app.modules.dpt360.access_scope import visible_alerts_query
from app.modules.dpt360.company_service import get_company_profile
from app.modules.dpt360.dashboard_service import (
    _is_critical_case,
    _value,
    _visible_business_cases_query,
    build_dashboard,
)
from app.modules.dpt360.radar_service import classify_area, impact_level
from app.modules.dpt360.schemas import DptCaseSummary, DptDeadlineSummary


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

    # A1 (auditoria 2026-08-12): os casos e prazos do relatório executivo NÃO
    # podiam herdar o recorte agregado do cockpit (`dashboard.cases`/`deadlines`
    # trazem somente empresas do top-200 do dashboard, truncando em 1.000 casos
    # e omitindo empresas antigas com histórico). Agora os casos e prazos são
    # consultados diretamente pelo client_id, com teto e flag de truncamento
    # próprios por seção.
    case_rows = (
        await db.execute(
            _visible_business_cases_query(user, [client_id])
            .order_by(Case.created_at.desc())
            .limit(31)
        )
    ).scalars().all()
    cases_truncated = len(case_rows) > 30
    # Convertido para o schema aqui, uma vez só: _visible_business_cases_query
    # devolve instâncias ORM de Case, sem model_dump() — usado tanto para
    # calcular risco crítico quanto para o campo "casos" da resposta.
    cases = [
        DptCaseSummary(
            id=case.id,
            client_id=case.client_id,
            titulo=case.titulo,
            area=_value(case.area),
            status=_value(case.status),
            prioridade=_value(case.prioridade),
            risco=case.risco,
            proxima_acao=case.proxima_acao,
            proxima_acao_prazo=case.proxima_acao_prazo,
        )
        for case in case_rows[:30]
    ]
    case_ids = {item.id for item in cases}

    deadline_rows = (
        await db.execute(
            select(Deadline)
            .where(Deadline.case_id.in_(case_ids) if case_ids else False)
            .where(Deadline.deleted_at.is_(None))
            .where(Deadline.status.in_([DeadlineStatus.pendente.value, DeadlineStatus.vencido.value]))
            .where(Deadline.confirmado.is_(True))
            .order_by(Deadline.data_prazo.asc())
            .limit(21)
        )
    ).scalars().all()
    deadlines_truncated = len(deadline_rows) > 20
    deadlines = [
        DptDeadlineSummary(
            id=deadline.id,
            case_id=deadline.case_id,
            titulo=deadline.titulo,
            data_prazo=deadline.data_prazo,
            status=_value(deadline.status),
            prioridade=_value(deadline.prioridade),
            confirmado=bool(deadline.confirmado),
        )
        for deadline in deadline_rows[:20]
        if deadline.case_id
    ]
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
            .limit(501)
        )
    ).scalars().all()
    changes_truncated = len(rows) > 500
    rows = rows[:500]

    secoes_truncadas: list[str] = []
    if cases_truncated:
        secoes_truncadas.append("casos (mais de 30)")
    if deadlines_truncated:
        secoes_truncadas.append("providências futuras (mais de 20)")
    if changes_truncated:
        secoes_truncadas.append("alertas do período (mais de 500 no intervalo)")

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

    # "principais_riscos" também tem teto próprio (10) e precisa entrar na
    # mesma verificação de cobertura que casos/prazos/alertas — do contrário
    # uma empresa com mais de 10 riscos críticos teria a lista cortada sem aviso.
    if len(critical) > 10:
        secoes_truncadas.append("riscos atuais (mais de 10)")

    cobertura_notas = [f"Recorte agregado do cockpit: {note}" for note in dashboard.notes]
    cobertura_notas.extend(
        [f"Seção truncada no teto próprio: {label}." for label in secoes_truncadas]
    )

    return {
        "client_id": client_id,
        "empresa": profile.nome,
        "periodo_dias": days,
        "generated_at": datetime.now(timezone.utc),
        "status": "rascunho",
        "requer_revisao": True,
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
        "casos": [item.model_dump() for item in cases],
        "mudancas_juridicas_relevantes": changes[:30],
        "cobertura": "parcial" if (secoes_truncadas or dashboard.coverage == "partial") else "completa",
        "notas_cobertura": cobertura_notas,
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