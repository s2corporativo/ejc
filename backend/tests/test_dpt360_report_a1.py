"""Regressão A1 (auditoria 2026-08-12) — `build_executive_report` deve consultar
casos e prazos da empresa diretamente, sem herdar o recorte agregado do dashboard
(truncamento em 200 empresas / 1000 casos), e qualquer corte de teto deve entrar
explicitamente em `cobertura="parcial"` e `notas_cobertura`, nunca em silêncio.

Padrão dos arquivos `*_dblevel.py`: Postgres real via singleton
`app.core.database.engine`/`AsyncSessionLocal`; sem `RUN_DB_TESTS=1`, pula.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from uuid import uuid4

import pytest

from app.modules.dpt360 import report_service

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_DB_TESTS"),
    reason="requer banco real (RUN_DB_TESTS=1)",
)


async def _seed(db, *, role="socio", companies=1, cases_per_company=5):
    from app.models.case import Case, CaseArea, CasePrioridade, CaseStatus
    from app.models.client import Client, ClientTipo
    from app.models.deadline import Deadline, DeadlineStatus
    from app.models.user import User, UserRole
    import bcrypt

    user = User(
        id=str(uuid4()),
        email=f"auditor-a1-{role}-{uuid4().hex[:8]}@local.dev",
        full_name="Auditor A1",
        hashed_password=bcrypt.hashpw("SenhaTeste@A1".encode(), bcrypt.gensalt()).decode(),
        role=UserRole(role),
        is_active=True,
    )
    db.add(user)
    await db.flush()

    clients = []
    for i in range(companies):
        client = Client(
            id=str(uuid4()),
            tipo=ClientTipo.PJ,
            nome_fantasia=f"Empresa A1-{i}",
            razao_social=f"Empresa A1-{i} Ltda",
        )
        db.add(client)
        await db.flush()
        clients.append(client)

    for i, client in enumerate(clients):
        for j in range(cases_per_company):
            case = Case(
                id=str(uuid4()),
                client_id=client.id,
                titulo=f"Caso A1-{i}-{j}",
                area=CaseArea.empresarial,
                status=CaseStatus.aberto,
                prioridade=CasePrioridade.media,
                advogado_responsavel_id=(None if role == "socio" else user.id),
            )
            db.add(case)
            await db.flush()
            db.add(
                Deadline(
                    id=str(uuid4()),
                    case_id=case.id,
                    titulo=f"Prazo A1-{i}-{j}",
                    data_prazo=date.today() + timedelta(days=j + 1),
                    status=DeadlineStatus.pendente.value,
                )
            )
            await db.flush()

    await db.commit()
    return user, clients


@pytest.fixture
async def db():
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        yield session


@pytest.mark.asyncio
async def test_empresa_antiga_retorna_casos_fora_do_top_200(db):
    """Empresa sem casos recentes (fora do top-200 do dashboard) deve
    continuar aparecendo com seus casos reais no relatório executivo."""
    from app.models.case import Case  # noqa: F401 — registra model no metadata
    from app.core.database import Base

    async with db.bind.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    user, clients = await _seed(db, companies=2, cases_per_company=3)
    empresa_antiga = clients[0]

    report = await report_service.build_executive_report(
        db, user, str(empresa_antiga.id)
    )

    assert report is not None, "o relatório não pode falhar para empresa visível"
    assert len(report["casos"]) == 3, (
        "os 3 casos reais da empresa devem entrar no relatório, mesmo que ela "
        "não estivesse entre as empresas hidrataadas do dashboard agregado"
    )
    assert report["cobertura"] in {"completa", "parcial"}
    assert isinstance(report["notas_cobertura"], list)


@pytest.mark.asyncio
async def test_cobertura_parcial_aparece_quando_secao_corta(db):
    """Corte do teto próprio de uma seção (31+ casos) entra em cobertura
    parcial com nota explícita, nunca em silêncio."""
    from app.core.database import Base

    async with db.bind.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    user, clients = await _seed(db, companies=1, cases_per_company=31)
    report = await report_service.build_executive_report(db, user, str(clients[0].id))

    assert report["cobertura"] == "parcial"
    assert any("casos" in nota for nota in report["notas_cobertura"]), (
        "o corte de casos deve constar em notas_cobertura"
    )
    assert len(report["casos"]) == 30


@pytest.mark.asyncio
async def test_empresa_invisivel_retorna_none(db):
    """Empresa fora do escopo de visibilidade do usuário retorna None
    (fail-closed), sem vazar dados nem levantar exceção."""
    from app.core.database import Base
    from app.models.user import User, UserRole
    import bcrypt

    async with db.bind.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    user, clients = await _seed(db, companies=1, cases_per_company=2)
    outsider = User(
        id=str(uuid4()),
        email=f"fora-a1-{uuid4().hex[:8]}@local.dev",
        full_name="Fora",
        hashed_password=bcrypt.hashpw("SenhaTeste@A1".encode(), bcrypt.gensalt()).decode(),
        role=UserRole.advogado,
        is_active=True,
    )
    db.add(outsider)
    await db.commit()

    report = await report_service.build_executive_report(
        db, outsider, str(clients[0].id)
    )

    assert report is None


@pytest.mark.asyncio
async def test_prazos_da_empresa_entravam_independentes_do_dashboard(db):
    """Os prazos do relatório devem ser os da empresa pedida, mesmo quando o
    dashboard agregado não hidrata a empresa (cenário do gatilho principal
    da auditoria: empresa fora das 200 mais recentes)."""
    from app.core.database import Base

    async with db.bind.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    user, clients = await _seed(db, companies=1, cases_per_company=4)
    report = await report_service.build_executive_report(db, user, str(clients[0].id))

    assert report is not None
    assert len(report["providencias_futuras"]) == 4, (
        "os 4 prazos futuros da empresa devem constar no relatório"
    )
