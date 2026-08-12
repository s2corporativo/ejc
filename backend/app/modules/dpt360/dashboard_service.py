from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ownership import is_gestao
from app.models.case import Case, CaseStatus
from app.models.client import Client, ClientTipo
from app.models.dpt_diagnostico import DptDiagnosticRun
from app.models.deadline import Deadline, DeadlineStatus
from app.models.user import User
from app.modules.dpt360.schemas import (
    DptCaseSummary,
    DptCompanySummary,
    DptDashboardMetrics,
    DptDashboardResponse,
    DptDeadlineSummary,
    DptPriorityItem,
)

BUSINESS_AREAS = {
    "empresarial",
    "tributario",
    "ambiental",
    "administrativo",
    "trabalhista",
    "contratual",
    "societario",
    "licitacoes",
    "digital_lgpd",
    "bancario",
    "agrario",
    "agronegocio",
}

OPEN_CASE_STATUSES = {
    CaseStatus.aberto.value,
    CaseStatus.em_instrucao.value,
    CaseStatus.em_producao.value,
    CaseStatus.protocolado.value,
}

# O cockpit não deve materializar uma carteira inteira sem limite. Métricas são
# calculadas por agregação SQL sobre todo o escopo; estes tetos limitam somente
# o payload detalhado. Se houver truncamento, `coverage=partial` deixa isso
# explícito em vez de apresentar um recorte como completo.
COMPANY_PAYLOAD_LIMIT = 200
CASE_PAYLOAD_LIMIT = 1000
DEADLINE_PAYLOAD_LIMIT = 2000


def _value(value) -> str:
    raw = getattr(value, "value", value)
    return str(raw) if raw is not None else ""


def _visible_company_query(user: User):
    query = select(Client).where(
        Client.deleted_at.is_(None),
        Client.tipo == ClientTipo.PJ,
    )
    if is_gestao(user):
        return query

    linked_company_ids = select(Case.client_id).where(
        Case.deleted_at.is_(None),
        or_(
            Case.advogado_responsavel_id == user.id,
            Case.advogado_auxiliar_id == user.id,
        ),
    )
    return query.where(
        or_(
            Client.responsavel_id == user.id,
            Client.id.in_(linked_company_ids),
        )
    )


def _visible_business_cases_query(user: User, company_ids: Any):
    query = select(Case).where(
        Case.deleted_at.is_(None),
        Case.client_id.in_(company_ids),
        Case.area.in_(BUSINESS_AREAS),
    )
    if is_gestao(user):
        return query
    return query.where(
        or_(
            Case.advogado_responsavel_id == user.id,
            Case.advogado_auxiliar_id == user.id,
        )
    )


def _is_critical_case(case: Case | DptCaseSummary) -> bool:
    if _value(case.status) not in OPEN_CASE_STATUSES:
        return False
    risk = (case.risco or "").strip().lower()
    return _value(case.prioridade) == "critica" or risk in {"alto", "critico"}


def _critical_case_sql(case_table):
    return (
        case_table.c.status.in_(OPEN_CASE_STATUSES)
        & (
            (case_table.c.prioridade == "critica")
            | func.lower(func.coalesce(case_table.c.risco, "")).in_(["alto", "critico"])
        )
    )


async def build_dashboard(db: AsyncSession, user: User) -> DptDashboardResponse:
    """Composição read-only e limitada do cockpit empresarial.

    Segurança: cada conjunto é reduzido ao escopo canônico do usuário. Prazos
    só entram quando ligados a caso empresarial visível; prazos avulsos nunca
    ampliam o escopo. Métricas globais são agregadas no banco e independem dos
    limites de hidratação do payload detalhado.
    """
    company_query = _visible_company_query(user).order_by(Client.created_at.desc())
    company_count = int(
        (
            await db.execute(
                select(func.count()).select_from(company_query.order_by(None).subquery())
            )
        ).scalar()
        or 0
    )

    company_rows = (
        await db.execute(company_query.limit(COMPANY_PAYLOAD_LIMIT + 1))
    ).scalars().all()
    companies_truncated = len(company_rows) > COMPANY_PAYLOAD_LIMIT
    companies = company_rows[:COMPANY_PAYLOAD_LIMIT]
    company_ids = [company.id for company in companies]

    if not company_count:
        return DptDashboardResponse(
            generated_at=datetime.now(timezone.utc),
            metrics=DptDashboardMetrics(),
            notes=[
                "Nenhum cliente pessoa jurídica está visível para este usuário. Ausência de dados não equivale a regularidade jurídica."
            ],
        )

    # Subconsulta de todas as empresas visíveis, usada apenas para agregação das
    # métricas globais sem materializar todos os IDs em memória.
    all_company_ids = _visible_company_query(user).with_only_columns(Client.id).order_by(None)
    all_cases_query = _visible_business_cases_query(user, all_company_ids)
    all_cases_sq = all_cases_query.order_by(None).subquery()

    global_critical_count = int(
        (
            await db.execute(
                select(func.count())
                .select_from(all_cases_sq)
                .where(_critical_case_sql(all_cases_sq))
            )
        ).scalar()
        or 0
    )

    # Diagnósticos 360 pendentes de revisão (HITL) em empresas visíveis.
    global_pending_diagnostics = int(
        (
            await db.execute(
                select(func.count(DptDiagnosticRun.id)).where(
                    DptDiagnosticRun.client_id.in_(all_company_ids),
                    DptDiagnosticRun.requer_revisao.is_(True),
                )
            )
        ).scalar()
        or 0
    )

    now_utc = datetime.now(timezone.utc)
    today = now_utc.date()
    horizon = today + timedelta(days=7)
    global_upcoming_count = int(
        (
            await db.execute(
                select(func.count(Deadline.id)).where(
                    Deadline.deleted_at.is_(None),
                    Deadline.case_id.in_(select(all_cases_sq.c.id)),
                    Deadline.status.in_(
                        [
                            DeadlineStatus.pendente.value,
                            DeadlineStatus.vencido.value,
                        ]
                    ),
                    Deadline.data_prazo <= horizon,
                )
            )
        ).scalar()
        or 0
    )

    cases: list[Case] = []
    cases_truncated = False
    if company_ids:
        case_rows = (
            await db.execute(
                _visible_business_cases_query(user, company_ids)
                .order_by(Case.created_at.desc())
                .limit(CASE_PAYLOAD_LIMIT + 1)
            )
        ).scalars().all()
        cases_truncated = len(case_rows) > CASE_PAYLOAD_LIMIT
        cases = case_rows[:CASE_PAYLOAD_LIMIT]
    case_ids = [case.id for case in cases]

    deadlines: list[Deadline] = []
    deadlines_truncated = False
    if case_ids:
        deadline_rows = (
            await db.execute(
                select(Deadline)
                .where(
                    Deadline.deleted_at.is_(None),
                    Deadline.case_id.in_(case_ids),
                    Deadline.status.in_(
                        [
                            DeadlineStatus.pendente.value,
                            DeadlineStatus.vencido.value,
                        ]
                    ),
                )
                .order_by(Deadline.data_prazo.asc())
                .limit(DEADLINE_PAYLOAD_LIMIT + 1)
            )
        ).scalars().all()
        deadlines_truncated = len(deadline_rows) > DEADLINE_PAYLOAD_LIMIT
        deadlines = deadline_rows[:DEADLINE_PAYLOAD_LIMIT]

    upcoming = [deadline for deadline in deadlines if deadline.data_prazo <= horizon]
    critical_cases = [case for case in cases if _is_critical_case(case)]

    company_by_id = {company.id: company for company in companies}
    case_by_id = {case.id: case for case in cases}
    cases_by_company: dict[str, list[Case]] = defaultdict(list)
    for case in cases:
        cases_by_company[case.client_id].append(case)

    company_payload: list[DptCompanySummary] = []
    for company in companies:
        company_cases = cases_by_company.get(company.id, [])
        company_case_ids = {case.id for case in company_cases}
        company_upcoming = [
            deadline for deadline in upcoming if deadline.case_id in company_case_ids
        ]
        company_payload.append(
            DptCompanySummary(
                id=company.id,
                nome=company.razao_social
                or company.nome_fantasia
                or "Empresa sem razão social",
                status=_value(company.status),
                cidade=company.cidade,
                estado=company.estado,
                casos=len(company_cases),
                casos_abertos=sum(
                    1
                    for case in company_cases
                    if _value(case.status) in OPEN_CASE_STATUSES
                ),
                sinais_criticos=sum(
                    1 for case in company_cases if _is_critical_case(case)
                ),
                providencias_proximas=len(company_upcoming),
            )
        )

    case_payload = [
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
        for case in cases
    ]

    deadline_payload = [
        DptDeadlineSummary(
            id=deadline.id,
            case_id=deadline.case_id,
            titulo=deadline.titulo,
            data_prazo=deadline.data_prazo,
            status=_value(deadline.status),
            prioridade=_value(deadline.prioridade),
            confirmado=bool(deadline.confirmado),
        )
        for deadline in deadlines
        if deadline.case_id
    ]

    priority_items: list[DptPriorityItem] = []
    for deadline in upcoming:
        if not deadline.case_id:
            continue
        case = case_by_id.get(deadline.case_id)
        if not case:
            continue
        company = company_by_id.get(case.client_id)
        if not company:
            continue
        overdue = deadline.data_prazo < today or _value(deadline.status) == "vencido"
        due_soon = deadline.data_prazo <= today + timedelta(days=3)
        level = "critico" if overdue else "alto" if due_soon else "atencao"
        confirmation_note = (
            ""
            if bool(deadline.confirmado)
            else " · Sugestão automática ainda não confirmada pelo advogado."
        )
        priority_items.append(
            DptPriorityItem(
                tipo="prazo",
                nivel=level,
                company_id=company.id,
                company_name=company.razao_social
                or company.nome_fantasia
                or "Empresa sem razão social",
                case_id=case.id,
                title=deadline.titulo,
                detail=(
                    "Prazo vencido" if overdue else "Providência com vencimento próximo"
                )
                + confirmation_note,
                canonical_path=f"/atividades?tipo=prazo&caso={case.id}",
                due_date=deadline.data_prazo,
                confirmado=bool(deadline.confirmado),
            )
        )

    for case in critical_cases:
        company = company_by_id.get(case.client_id)
        if not company:
            continue
        priority_items.append(
            DptPriorityItem(
                tipo="caso",
                nivel=(
                    "critico" if _value(case.prioridade) == "critica" else "alto"
                ),
                company_id=company.id,
                company_name=company.razao_social
                or company.nome_fantasia
                or "Empresa sem razão social",
                case_id=case.id,
                title=case.titulo,
                detail=f"Sinal objetivo registrado: prioridade {_value(case.prioridade)} / risco {case.risco or 'não informado'}",
                canonical_path=f"/casos/{case.id}",
            )
        )

    priority_items.sort(
        key=lambda item: (
            {"critico": 0, "alto": 1, "atencao": 2}[item.nivel],
            item.due_date or date.max,
            item.company_name.lower(),
        )
    )

    partial = companies_truncated or cases_truncated or deadlines_truncated
    notes = [
        "Saúde jurídica por área permanece Não avaliada enquanto não houver diagnóstico aprovado.",
        "Prazos empresariais incluem somente registros ligados a casos empresariais visíveis; sugestões automáticas permanecem identificadas como não confirmadas.",
    ]
    if partial:
        notes.append(
            "A lista detalhada foi limitada para preservar desempenho; métricas superiores foram agregadas sobre todo o escopo visível. Use os módulos canônicos para a listagem integral."
        )

    return DptDashboardResponse(
        generated_at=now_utc,
        metrics=DptDashboardMetrics(
            empresas_acompanhadas=company_count,
            riscos_criticos=global_critical_count,
            providencias_proximas=global_upcoming_count,
            mudancas_juridicas_hoje=None,
            empresas_potencialmente_impactadas=None,
            diagnosticos_pendentes=global_pending_diagnostics,
        ),
        companies=company_payload,
        cases=case_payload,
        deadlines=deadline_payload,
        priorities=priority_items[:20],
        coverage="partial" if partial else "complete",
        notes=notes,
    )
