from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ownership import is_gestao
from app.models.case import Case, CaseStatus
from app.models.client import Client, ClientTipo
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

    linked_company_ids = (
        select(Case.client_id)
        .where(
            Case.deleted_at.is_(None),
            or_(
                Case.advogado_responsavel_id == user.id,
                Case.advogado_auxiliar_id == user.id,
            ),
        )
    )
    return query.where(
        or_(
            Client.responsavel_id == user.id,
            Client.id.in_(linked_company_ids),
        )
    )


def _visible_business_cases_query(user: User, company_ids: list[str]):
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


def _is_critical_case(case: Case) -> bool:
    if _value(case.status) not in OPEN_CASE_STATUSES:
        return False
    risk = (case.risco or "").strip().lower()
    return _value(case.prioridade) == "critica" or risk in {"alto", "critico"}


async def build_dashboard(db: AsyncSession, user: User) -> DptDashboardResponse:
    """Composição read-only do cockpit empresarial.

    Segurança: cada conjunto é reduzido ao escopo canônico do usuário. Prazos
    só entram quando ligados a um caso empresarial que já passou pelo filtro de
    caso; prazos avulsos nunca ampliam o escopo do DPT.
    """
    companies = (
        await db.execute(_visible_company_query(user).order_by(Client.created_at.desc()))
    ).scalars().all()
    company_ids = [company.id for company in companies]

    if not company_ids:
        return DptDashboardResponse(
            generated_at=datetime.now(timezone.utc),
            metrics=DptDashboardMetrics(),
            notes=[
                "Nenhum cliente pessoa jurídica está visível para este usuário. Ausência de dados não equivale a regularidade jurídica."
            ],
        )

    cases = (
        await db.execute(
            _visible_business_cases_query(user, company_ids).order_by(Case.created_at.desc())
        )
    ).scalars().all()
    case_ids = [case.id for case in cases]

    deadlines: list[Deadline] = []
    if case_ids:
        deadlines = (
            await db.execute(
                select(Deadline)
                .where(
                    Deadline.deleted_at.is_(None),
                    Deadline.case_id.in_(case_ids),
                    Deadline.status.in_([
                        DeadlineStatus.pendente.value,
                        DeadlineStatus.vencido.value,
                    ]),
                )
                .order_by(Deadline.data_prazo.asc())
            )
        ).scalars().all()

    today = date.today()
    horizon = today + timedelta(days=7)
    upcoming = [deadline for deadline in deadlines if deadline.data_prazo <= horizon]
    critical_cases = [case for case in cases if _is_critical_case(case)]

    company_by_id = {company.id: company for company in companies}
    case_by_id = {case.id: case for case in cases}
    cases_by_company: dict[str, list[Case]] = defaultdict(list)
    deadlines_by_case: dict[str, list[Deadline]] = defaultdict(list)
    for case in cases:
        cases_by_company[case.client_id].append(case)
    for deadline in deadlines:
        if deadline.case_id:
            deadlines_by_case[deadline.case_id].append(deadline)

    company_payload: list[DptCompanySummary] = []
    for company in companies:
        company_cases = cases_by_company.get(company.id, [])
        company_case_ids = {case.id for case in company_cases}
        company_upcoming = [
            deadline
            for deadline in upcoming
            if deadline.case_id in company_case_ids
        ]
        company_payload.append(
            DptCompanySummary(
                id=company.id,
                nome=company.razao_social or company.nome_fantasia or "Empresa sem razão social",
                status=_value(company.status),
                cidade=company.cidade,
                estado=company.estado,
                casos=len(company_cases),
                casos_abertos=sum(
                    1 for case in company_cases if _value(case.status) in OPEN_CASE_STATUSES
                ),
                sinais_criticos=sum(1 for case in company_cases if _is_critical_case(case)),
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
        priority_items.append(
            DptPriorityItem(
                tipo="prazo",
                nivel=level,
                company_id=company.id,
                company_name=company.razao_social or company.nome_fantasia or "Empresa sem razão social",
                case_id=case.id,
                title=deadline.titulo,
                detail="Prazo vencido" if overdue else "Providência com vencimento próximo",
                canonical_path=f"/atividades?tipo=prazo&caso={case.id}",
                due_date=deadline.data_prazo,
            )
        )

    for case in critical_cases:
        company = company_by_id.get(case.client_id)
        if not company:
            continue
        priority_items.append(
            DptPriorityItem(
                tipo="caso",
                nivel="critico" if _value(case.prioridade) == "critica" else "alto",
                company_id=company.id,
                company_name=company.razao_social or company.nome_fantasia or "Empresa sem razão social",
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

    return DptDashboardResponse(
        generated_at=datetime.now(timezone.utc),
        metrics=DptDashboardMetrics(
            empresas_acompanhadas=len(companies),
            riscos_criticos=len(critical_cases),
            providencias_proximas=len(upcoming),
            # Mantidos explicitamente desconhecidos até as ondas especializadas.
            mudancas_juridicas_hoje=None,
            empresas_potencialmente_impactadas=None,
            diagnosticos_pendentes=None,
        ),
        companies=company_payload,
        cases=case_payload,
        deadlines=deadline_payload,
        priorities=priority_items[:20],
        notes=[
            "Saúde jurídica por área permanece Não avaliada enquanto não houver diagnóstico aprovado.",
            "Prazos empresariais incluem somente registros ligados a casos empresariais visíveis.",
        ],
    )
