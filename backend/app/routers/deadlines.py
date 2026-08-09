# ── app/routers/deadlines.py ─────────────────────────────────────────────────
# Prazos: CRUD + cálculo assistido + confirmação de ciência.
from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func as sqlfunc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import is_gestao, verificar_acesso_caso
from app.core.security import get_current_user, requer_advogado
from app.models.audit_log import criar_audit_log
from app.models.case import Case
from app.models.deadline import Deadline
from app.models.user import User
from app.schemas.common import MsgResponse
from app.schemas.deadline import (
    CalcularPrazoRequest,
    DeadlineCreate,
    DeadlineResponse,
    DeadlineUpdate,
)
from app.services.deadline_calculator import (
    dias_uteis_restantes,
    prazo_dias_corridos,
    prazo_dias_uteis,
    regime_processual_por_area,
)

router = APIRouter(prefix="/deadlines", tags=["Prazos"])
logger = logging.getLogger("ejc.deadlines")
_MAX_EXPORT = 5000


def _ids_casos_do_usuario(user: User):
    return (
        select(Case.id)
        .where(
            Case.deleted_at.is_(None),
            or_(
                Case.advogado_responsavel_id == user.id,
                Case.advogado_auxiliar_id == user.id,
            ),
        )
        .scalar_subquery()
    )


def _filtro_escopo_prazos(q, cu: User):
    if is_gestao(cu):
        return q
    return q.where(
        or_(
            Deadline.case_id.in_(_ids_casos_do_usuario(cu)),
            Deadline.responsavel_id == cu.id,
            Deadline.case_id.is_(None),
        )
    )


@router.post("/calcular")
async def calcular(req: CalcularPrazoRequest, cu: User = Depends(get_current_user)):
    """Calculadora rápida, sem persistência.

    Para processo penal, a data fatal depende da regra de contagem contínua e
    do marco processual específico. O endpoint genérico não converte
    silenciosamente uma data arbitrária em termo inicial penal: exige o fluxo
    DJEN (que conhece disponibilização/publicação) ou data final manual.
    """
    if req.regime_processual == "penal":
        raise HTTPException(
            status_code=422,
            detail=(
                "Cálculo penal não usa a contagem civil em dias úteis. "
                "Para publicação DJEN, use a sugestão da própria intimação; "
                "fora do DJEN, confirme o marco inicial e informe a data fatal."
            ),
        )

    if req.dias_uteis:
        if req.regime_processual is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Informe regime_processual (civel ou trabalhista) para "
                    "cálculo processual automático."
                ),
            )
        vencimento = prazo_dias_uteis(
            req.data_inicio,
            req.dias,
            tribunal=req.tribunal,
            em_dobro=req.dobro,
            aplicar_recesso=req.aplicar_recesso,
        )
        norma = (
            "CLT arts. 775 e 775-A"
            if req.regime_processual == "trabalhista"
            else "CPC arts. 219 e 220"
        )
        modo = f"dias úteis processuais ({norma})"
        if req.dobro:
            modo += " · quantidade dobrada (hipótese deve ser conferida)"
    else:
        vencimento = prazo_dias_corridos(
            req.data_inicio, req.dias, tribunal=req.tribunal
        )
        modo = "dias corridos c/ prorrogação do termo final"

    return {
        "data_vencimento": vencimento,
        "modo": modo,
        "regime_processual": req.regime_processual,
        "dias_uteis_restantes": dias_uteis_restantes(
            vencimento,
            aplicar_recesso=bool(req.dias_uteis and req.aplicar_recesso),
            tribunal=req.tribunal,
        ),
        "aviso": "Cálculo assistivo; confirme marco inicial, rito, suspensões e ato judicial.",
    }


@router.get("/")
async def listar(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status_f: Optional[str] = Query("pendente", alias="status"),
    case_id: Optional[str] = None,
    tipo: Optional[str] = None,
    apenas_meus: bool = False,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = select(Deadline).where(Deadline.deleted_at.is_(None))
    if status_f:
        q = q.where(Deadline.status == status_f)
    if case_id:
        q = q.where(Deadline.case_id == case_id)
    if tipo:
        q = q.where(Deadline.tipo == tipo)
    q = _filtro_escopo_prazos(q, cu)
    if apenas_meus:
        q = q.where(Deadline.responsavel_id == cu.id)
    q = q.order_by(Deadline.data_prazo.asc())

    total = (
        await db.execute(select(sqlfunc.count()).select_from(q.subquery()))
    ).scalar()
    rows = (
        await db.execute(q.offset((page - 1) * page_size).limit(page_size))
    ).scalars().all()

    hoje = date.today()
    data = []
    for prazo in rows:
        item = DeadlineResponse.model_validate(prazo).model_dump()
        dias = (prazo.data_prazo - hoje).days
        item["dias_restantes"] = dias
        item["urgencia"] = (
            "vencido"
            if dias < 0
            else "critico"
            if dias <= 3
            else "atencao"
            if dias <= 7
            else "normal"
        )
        data.append(item)
    return {"data": data, "total": total, "page": page, "page_size": page_size}


@router.get("/export.csv")
async def exportar_csv(
    status_f: Optional[str] = Query("pendente", alias="status"),
    case_id: Optional[str] = None,
    tipo: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = select(Deadline).where(Deadline.deleted_at.is_(None))
    if status_f:
        q = q.where(Deadline.status == status_f)
    if case_id:
        q = q.where(Deadline.case_id == case_id)
    if tipo:
        q = q.where(Deadline.tipo == tipo)
    q = _filtro_escopo_prazos(q, cu)
    q = q.order_by(Deadline.data_prazo.asc()).limit(_MAX_EXPORT + 1)
    rows = (await db.execute(q)).scalars().all()
    if len(rows) > _MAX_EXPORT:
        rows = rows[:_MAX_EXPORT]
        logger.warning("[export.csv] resultado truncado em %d linhas", _MAX_EXPORT)

    return Response(
        content=_prazos_para_csv(rows, date.today()),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="prazos.csv"'},
    )


def _prazos_para_csv(rows, hoje: date) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(
        [
            "Titulo",
            "Tipo",
            "Prioridade",
            "Status",
            "Data do prazo",
            "Data da intimacao",
            "Publicacao",
            "Termo inicial",
            "Regime",
            "Dias restantes",
            "Base legal",
        ]
    )
    for prazo in rows:
        dias = (prazo.data_prazo - hoje).days if prazo.data_prazo else ""
        writer.writerow(
            [
                prazo.titulo or "",
                prazo.tipo or "",
                prazo.prioridade or "",
                prazo.status or "",
                prazo.data_prazo.isoformat() if prazo.data_prazo else "",
                prazo.data_intimacao.isoformat()
                if getattr(prazo, "data_intimacao", None)
                else "",
                prazo.data_publicacao.isoformat()
                if getattr(prazo, "data_publicacao", None)
                else "",
                prazo.termo_inicial.isoformat()
                if getattr(prazo, "termo_inicial", None)
                else "",
                getattr(prazo, "regime_calculo", "") or "",
                dias,
                getattr(prazo, "base_legal", "") or "",
            ]
        )
    return "﻿" + buf.getvalue()


@router.post("/", status_code=201)
async def criar(
    payload: DeadlineCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    caso: Case | None = None
    if payload.case_id:
        await verificar_acesso_caso(db, cu, payload.case_id)
        caso = (
            await db.execute(
                select(Case).where(
                    Case.id == payload.case_id, Case.deleted_at.is_(None)
                )
            )
        ).scalar_one_or_none()

    regime = payload.regime_processual
    if regime is None and caso is not None:
        regime = regime_processual_por_area(caso.area)

    data_prazo = payload.data_prazo
    base = payload.base_legal
    calculo_automatico = False

    if not data_prazo and payload.dias_prazo and payload.data_intimacao:
        if payload.tipo == "processual":
            if regime is None:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Não foi possível determinar o regime processual do caso. "
                        "Informe regime_processual ou a data_prazo manualmente."
                    ),
                )
            if regime == "penal":
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Prazo penal não pode ser convertido pela contagem civil. "
                        "Confirme o marco inicial e informe a data fatal, ou use "
                        "o fluxo assistido da intimação DJEN."
                    ),
                )
            data_prazo = prazo_dias_uteis(
                payload.data_intimacao,
                payload.dias_prazo,
                tribunal=payload.tribunal,
                em_dobro=payload.dobro,
                aplicar_recesso=True,
            )
            norma = (
                "CLT arts. 775 e 775-A"
                if regime == "trabalhista"
                else "CPC arts. 219 e 220"
            )
            base = base or f"{payload.dias_prazo} dias úteis ({norma})"
            calculo_automatico = True
        else:
            data_prazo = prazo_dias_corridos(
                payload.data_intimacao,
                payload.dias_prazo,
                tribunal=payload.tribunal,
            )
            base = base or f"{payload.dias_prazo} dias corridos"
            calculo_automatico = True

    if not data_prazo:
        raise HTTPException(
            status_code=422,
            detail="Informe data_prazo OU (data_intimacao + dias_prazo)",
        )

    prazo = Deadline(
        id=str(uuid4()),
        titulo=payload.titulo,
        tipo=payload.tipo,
        prioridade=payload.prioridade,
        descricao=payload.descricao,
        data_prazo=data_prazo,
        data_intimacao=payload.data_intimacao,
        regime_calculo=regime,
        calculo_automatico=calculo_automatico,
        base_legal=base,
        case_id=payload.case_id,
        responsavel_id=payload.responsavel_id or cu.id,
    )
    db.add(prazo)
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "CREATE",
        "deadlines",
        prazo.id,
        dados_depois={
            "data_prazo": str(data_prazo),
            "data_intimacao": str(payload.data_intimacao)
            if payload.data_intimacao
            else None,
            "regime_calculo": regime,
            "calculo_automatico": calculo_automatico,
        },
    )
    await db.commit()
    await db.refresh(prazo)
    return DeadlineResponse.model_validate(prazo)


@router.patch("/{deadline_id}")
async def atualizar(
    deadline_id: str,
    payload: DeadlineUpdate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    prazo = (
        await db.execute(
            select(Deadline).where(
                Deadline.id == deadline_id, Deadline.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if not prazo:
        raise HTTPException(status_code=404, detail="Prazo não encontrado")
    if prazo.case_id:
        await verificar_acesso_caso(db, cu, prazo.case_id)

    mudancas = payload.model_dump(exclude_unset=True)
    status_antes = getattr(prazo.status, "value", prazo.status)
    if "data_prazo" in mudancas and mudancas["data_prazo"] != prazo.data_prazo:
        await criar_audit_log(
            db,
            cu.id,
            cu.role.value,
            "PRAZO_ALTERADO",
            "deadlines",
            deadline_id,
            dados_antes={"data_prazo": str(prazo.data_prazo)},
            dados_depois={"data_prazo": str(mudancas["data_prazo"])},
        )
        # Alteração humana de data invalida a afirmação de que a data fatal foi
        # produzida integralmente pelo motor automático.
        prazo.calculo_automatico = False

    for key, value in mudancas.items():
        setattr(prazo, key, value)

    if mudancas.get("status") == "concluido" and status_antes != "concluido":
        prazo.data_conclusao = datetime.now(timezone.utc)
        prazo.concluido_por = cu.id
        await criar_audit_log(
            db,
            cu.id,
            cu.role.value,
            "PRAZO_CONCLUIDO",
            "deadlines",
            deadline_id,
            dados_antes={"status": status_antes},
            dados_depois={
                "status": "concluido",
                "concluido_por": cu.id,
                "data_conclusao": prazo.data_conclusao.isoformat(),
            },
        )
    await db.commit()
    await db.refresh(prazo)
    return DeadlineResponse.model_validate(prazo)


@router.patch("/{deadline_id}/confirmar", response_model=DeadlineResponse)
async def confirmar(
    deadline_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    prazo = (
        await db.execute(
            select(Deadline).where(
                Deadline.id == deadline_id, Deadline.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if not prazo:
        raise HTTPException(status_code=404, detail="Prazo não encontrado")
    if prazo.case_id:
        await verificar_acesso_caso(db, cu, prazo.case_id)

    if not prazo.confirmado:
        prazo.confirmado = True
        await criar_audit_log(
            db,
            cu.id,
            cu.role.value,
            "PRAZO_CONFIRMADO",
            "deadlines",
            deadline_id,
        )
        await db.commit()
        await db.refresh(prazo)
    return DeadlineResponse.model_validate(prazo)


@router.post("/{deadline_id}/ciencia", response_model=MsgResponse)
async def confirmar_ciencia(
    deadline_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    prazo = (
        await db.execute(
            select(Deadline).where(
                Deadline.id == deadline_id, Deadline.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if not prazo:
        raise HTTPException(status_code=404, detail="Prazo não encontrado")
    if prazo.case_id:
        await verificar_acesso_caso(db, cu, prazo.case_id)

    prazo.ciencia_confirmada = True
    prazo.ciencia_confirmada_em = datetime.now(timezone.utc)
    prazo.ciencia_confirmada_por = cu.id
    await criar_audit_log(
        db, cu.id, cu.role.value, "CIENCIA_PRAZO", "deadlines", deadline_id
    )
    await db.commit()
    return MsgResponse(detail="Ciência confirmada")


@router.delete("/{deadline_id}", response_model=MsgResponse)
async def cancelar(
    deadline_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    requer_advogado(cu, detail="Sem permissão para cancelar prazos")
    prazo = (
        await db.execute(
            select(Deadline).where(
                Deadline.id == deadline_id, Deadline.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if not prazo:
        raise HTTPException(status_code=404, detail="Prazo não encontrado")
    if prazo.case_id:
        await verificar_acesso_caso(db, cu, prazo.case_id)
    prazo.deleted_at = datetime.now(timezone.utc)
    prazo.status = "cancelado"
    await criar_audit_log(
        db, cu.id, cu.role.value, "DELETE", "deadlines", deadline_id
    )
    await db.commit()
    return MsgResponse(detail="Prazo cancelado")
