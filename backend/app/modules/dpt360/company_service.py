from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func as sqlfunc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.environmental import EnvironmentalCase
from app.models.lgpd_tratamento import RegistroTratamento
from app.models.sociedade_cliente import SociedadeCliente
from app.models.user import User
from app.modules.dpt360.access_scope import visible_document_count_query
from app.modules.dpt360.dashboard_service import (
    OPEN_CASE_STATUSES,
    _value,
    _visible_business_cases_query,
    _visible_company_query,
)
from app.modules.dpt360.schemas import DptCompanyProfile, DptHealthArea, DptTwinDimension

HEALTH_LABELS = [
    "Tributário",
    "Ambiental",
    "Administrativo",
    "Trabalhista",
    "Contratual",
    "LGPD",
    "Governança de IA",
]


async def get_company_profile(
    db: AsyncSession,
    user: User,
    client_id: str,
) -> DptCompanyProfile | None:
    company = (
        await db.execute(_visible_company_query(user).where(Client.id == client_id))
    ).scalar_one_or_none()
    if company is None:
        return None

    cases = (
        await db.execute(_visible_business_cases_query(user, [client_id]))
    ).scalars().all()
    case_ids = [item.id for item in cases]

    documents = (
        await db.execute(
            visible_document_count_query(
                user,
                client_id=client_id,
                visible_case_ids=case_ids,
            )
        )
    ).scalar() or 0

    societies = (
        await db.execute(
            select(sqlfunc.count(SociedadeCliente.id)).where(
                SociedadeCliente.client_id == client_id,
                SociedadeCliente.deleted_at.is_(None),
            )
        )
    ).scalar() or 0

    lgpd_total, lgpd_high = (
        await db.execute(
            select(
                sqlfunc.count(RegistroTratamento.id),
                sqlfunc.count(RegistroTratamento.id).filter(
                    RegistroTratamento.risco == "alto"
                ),
            ).where(
                RegistroTratamento.client_id == client_id,
                RegistroTratamento.deleted_at.is_(None),
            )
        )
    ).one()

    environmental_total = 0
    if case_ids:
        environmental_total = (
            await db.execute(
                select(sqlfunc.count(EnvironmentalCase.id)).where(
                    EnvironmentalCase.case_id.in_(case_ids),
                    EnvironmentalCase.deleted_at.is_(None),
                )
            )
        ).scalar() or 0

    health = [DptHealthArea(area=label) for label in HEALTH_LABELS]
    areas = sorted({_value(item.area) for item in cases if _value(item.area)})
    open_cases = sum(
        1 for item in cases if _value(item.status) in OPEN_CASE_STATUSES
    )

    from app.models.deadline import Deadline, DeadlineStatus

    pending_deadlines = 0
    if case_ids:
        pending_deadlines = (
            await db.execute(
                select(sqlfunc.count(Deadline.id)).where(
                    Deadline.deleted_at.is_(None),
                    Deadline.case_id.in_(case_ids),
                    Deadline.confirmado.is_(True),
                    Deadline.status.in_(
                        [DeadlineStatus.pendente.value, DeadlineStatus.vencido.value]
                    ),
                )
            )
        ).scalar() or 0

    twin = [
        DptTwinDimension(
            key="cadastro",
            label="Cadastro empresarial",
            status="com_dados",
            registros=1,
            canonical_path=f"/clientes/{client_id}",
            note="Fonte: cadastro canônico de Clientes do EJC.",
        ),
        DptTwinDimension(
            key="casos",
            label="Casos empresariais",
            status="com_dados" if cases else "sem_dados",
            registros=len(cases),
            canonical_path="/dpt360/casos",
        ),
        DptTwinDimension(
            key="documentos",
            label="Documentos visíveis vinculados",
            status="com_dados" if documents else "sem_dados",
            registros=int(documents),
            canonical_path=f"/clientes/{client_id}",
            note="Contagem respeita cofre, confidencialidade e ownership do GED canônico; conteúdo não é replicado.",
        ),
        DptTwinDimension(
            key="societario",
            label="Estrutura societária",
            status="com_dados" if societies else "sem_dados",
            registros=int(societies),
            canonical_path="/areas-de-atuacao/empresarial",
        ),
        DptTwinDimension(
            key="lgpd",
            label="Operações de tratamento LGPD",
            status="com_dados" if lgpd_total else "sem_dados",
            registros=int(lgpd_total or 0),
            canonical_path="/areas-de-atuacao/digital_lgpd",
            note=(
                f"{int(lgpd_high or 0)} operação(ões) marcada(s) como alto risco no ROPA."
                if lgpd_total
                else "Nenhuma operação ROPA localizada; isso não prova ausência de tratamento de dados."
            ),
        ),
        DptTwinDimension(
            key="ambiental",
            label="Autos ambientais vinculados",
            status="com_dados" if environmental_total else "sem_dados",
            registros=int(environmental_total),
            canonical_path="/areas-de-atuacao/ambiental",
        ),
        DptTwinDimension(
            key="ia",
            label="Governança de IA empresarial",
            status="sem_dados",
            registros=0,
            note="Ainda não existe inventário empresarial de IA confirmado para esta projeção.",
            canonical_path="/ia-governanca",
        ),
    ]

    return DptCompanyProfile(
        id=company.id,
        nome=company.razao_social or company.nome_fantasia or "Empresa sem razão social",
        status=_value(company.status),
        cidade=company.cidade,
        estado=company.estado,
        generated_at=datetime.now(timezone.utc),
        health=health,
        twin=twin,
        areas_com_casos=areas,
        casos_abertos=open_cases,
        prazos_pendentes=int(pending_deadlines),
        documentos=int(documents),
        sociedades=int(societies),
        operacoes_lgpd=int(lgpd_total or 0),
        operacoes_lgpd_alto_risco=int(lgpd_high or 0),
        autos_ambientais=int(environmental_total),
        notes=[
            "Legal Twin é uma projeção factual dos registros existentes; não é um segundo cadastro.",
            "Sem diagnóstico aprovado, todas as áreas de saúde jurídica permanecem Não avaliadas.",
            "Sem dados em uma dimensão significa ausência de registro localizado, não ausência de obrigação ou risco.",
        ],
    )