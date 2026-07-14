# ── app/routers/deadlines.py ─────────────────────────────────────────────────
# Prazos: CRUD + cálculo automático (úteis/corridos) + confirmação de ciência
from __future__ import annotations
import csv
import io
import logging
from datetime import datetime, timezone, date
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL
from app.core.ownership import verificar_acesso_caso
from app.models.user import User
from app.models.deadline import Deadline
from app.models.audit_log import criar_audit_log
from app.services.deadline_calculator import (
    prazo_dias_uteis, prazo_dias_corridos, dias_uteis_restantes,
)
from app.schemas.deadline import (
    DeadlineCreate, DeadlineUpdate, DeadlineResponse, CalcularPrazoRequest,
)
from app.schemas.common import MsgResponse

router = APIRouter(prefix="/deadlines", tags=["Prazos"])
logger = logging.getLogger("ejc.deadlines")

_MAX_EXPORT = 5000  # teto de linhas do CSV (painel de prazos é sempre pequeno)


@router.post("/calcular")
async def calcular(req: CalcularPrazoRequest, cu: User = Depends(get_current_user)):
    """Calculadora rápida de prazo (sem persistir)."""
    if req.dias_uteis:
        vencimento = prazo_dias_uteis(req.data_inicio, req.dias,
                                      tribunal=req.tribunal, em_dobro=req.dobro)
        modo = ("dias úteis EM DOBRO (CPC art. 183/229)" if req.dobro
                else "dias úteis (CPC art. 219)")
    else:
        # Prazo em dobro é dos prazos processuais em dias úteis; não incide sobre
        # prazo administrativo corrido (Lei 9.784) — ignorado aqui de propósito.
        vencimento = prazo_dias_corridos(req.data_inicio, req.dias, tribunal=req.tribunal)
        modo = "dias corridos c/ prorrogação (Lei 9.784 art. 66 §1º)"
    return {
        "data_vencimento": vencimento,
        "modo": modo,
        "dias_uteis_restantes": dias_uteis_restantes(vencimento),
    }


@router.get("/")
async def listar(
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
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
    if apenas_meus or ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        # Painel de prazos é compartilhado por padrão (requisito do escritório),
        # mas advogado pode filtrar só os seus
        if apenas_meus:
            q = q.where(Deadline.responsavel_id == cu.id)
    q = q.order_by(Deadline.data_prazo.asc())

    total = (await db.execute(
        select(sqlfunc.count()).select_from(q.subquery())
    )).scalar()
    rows = (await db.execute(
        q.offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()

    hoje = date.today()
    data = []
    for d in rows:
        item = DeadlineResponse.model_validate(d).model_dump()
        dias = (d.data_prazo - hoje).days
        item["dias_restantes"] = dias
        item["urgencia"] = (
            "vencido" if dias < 0 else
            "critico" if dias <= 3 else
            "atencao" if dias <= 7 else "normal"
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
    """Exporta os prazos (com os mesmos filtros do painel) em CSV — uso recorrente
    do escritório (imprimir/compartilhar/importar em planilha). Mesmo modelo de
    acesso do GET /deadlines (painel compartilhado). UTF-8 com BOM p/ o Excel
    abrir acentos corretamente."""
    q = select(Deadline).where(Deadline.deleted_at.is_(None))
    if status_f:
        q = q.where(Deadline.status == status_f)
    if case_id:
        q = q.where(Deadline.case_id == case_id)
    if tipo:
        q = q.where(Deadline.tipo == tipo)
    q = q.order_by(Deadline.data_prazo.asc()).limit(_MAX_EXPORT + 1)
    rows = (await db.execute(q)).scalars().all()
    truncado = len(rows) > _MAX_EXPORT
    if truncado:
        rows = rows[:_MAX_EXPORT]
        logger.warning("[export.csv] resultado truncado em %d linhas", _MAX_EXPORT)

    return Response(
        content=_prazos_para_csv(rows, date.today()),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="prazos.csv"'},
    )


def _prazos_para_csv(rows, hoje: date) -> str:
    """Serializa prazos em CSV (';' pt-BR, BOM UTF-8 p/ Excel). Pura e testável."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Titulo", "Tipo", "Prioridade", "Status", "Data do prazo",
                "Data da intimacao", "Dias restantes", "Base legal"])
    for d in rows:
        dias = (d.data_prazo - hoje).days if d.data_prazo else ""
        w.writerow([
            d.titulo or "", d.tipo or "", d.prioridade or "", d.status or "",
            d.data_prazo.isoformat() if d.data_prazo else "",
            d.data_intimacao.isoformat() if getattr(d, "data_intimacao", None) else "",
            dias, getattr(d, "base_legal", "") or "",
        ])
    return "﻿" + buf.getvalue()   # BOM UTF-8


@router.post("/", status_code=201)
async def criar(
    payload: DeadlineCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    # Cálculo automático se dias_prazo informado
    data_prazo = payload.data_prazo
    base = payload.base_legal
    if not data_prazo and payload.dias_prazo and payload.data_intimacao:
        if payload.dias_uteis:
            data_prazo = prazo_dias_uteis(payload.data_intimacao, payload.dias_prazo,
                                          tribunal=payload.tribunal, em_dobro=payload.dobro)
            base = base or (
                f"{payload.dias_prazo} dias úteis em dobro (CPC art. 183/229)"
                if payload.dobro else f"{payload.dias_prazo} dias úteis (CPC art. 219)"
            )
        else:
            data_prazo = prazo_dias_corridos(payload.data_intimacao, payload.dias_prazo, tribunal=payload.tribunal)
            base = base or f"{payload.dias_prazo} dias corridos (Lei 9.784)"
    if not data_prazo:
        raise HTTPException(
            status_code=422,
            detail="Informe data_prazo OU (data_intimacao + dias_prazo)",
        )

    if payload.case_id:
        await verificar_acesso_caso(db, cu, payload.case_id)
    d = Deadline(
        id=str(uuid4()),
        titulo=payload.titulo, tipo=payload.tipo,
        prioridade=payload.prioridade, descricao=payload.descricao,
        data_prazo=data_prazo, data_intimacao=payload.data_intimacao,
        base_legal=base, case_id=payload.case_id,
        responsavel_id=payload.responsavel_id or cu.id,
    )
    db.add(d)
    await criar_audit_log(db, cu.id, cu.role.value, "CREATE", "deadlines", d.id)
    await db.commit()
    await db.refresh(d)
    return DeadlineResponse.model_validate(d)


@router.patch("/{deadline_id}")
async def atualizar(
    deadline_id: str, payload: DeadlineUpdate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    d = (await db.execute(
        select(Deadline).where(
            Deadline.id == deadline_id, Deadline.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Prazo não encontrado")
    if d.case_id:
        await verificar_acesso_caso(db, cu, d.case_id)

    mudancas = payload.model_dump(exclude_unset=True)
    # Alteração de data_prazo é sensível: audit detalhado
    if "data_prazo" in mudancas and mudancas["data_prazo"] != d.data_prazo:
        await criar_audit_log(
            db, cu.id, cu.role.value, "PRAZO_ALTERADO", "deadlines", deadline_id,
            dados_antes={"data_prazo": str(d.data_prazo)},
            dados_depois={"data_prazo": str(mudancas["data_prazo"])},
        )
    for k, v in mudancas.items():
        setattr(d, k, v)
    if mudancas.get("status") == "concluido":
        d.data_conclusao = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(d)
    return DeadlineResponse.model_validate(d)


@router.patch("/{deadline_id}/confirmar", response_model=DeadlineResponse)
async def confirmar(
    deadline_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Confirma um prazo RASCUNHO extraído por IA (confirmado=false → true, #83
    Gap C). O prazo já dispara alertas mesmo como rascunho — isto apenas remove
    a marca "a confirmar" e deixa trilha de auditoria (PRAZO_CONFIRMADO).

    Ownership idêntico aos demais endpoints de prazo (verificar_acesso_caso):
    sem vínculo com o caso → 403/404. Idempotente: reconfirmar não regrava audit."""
    d = (await db.execute(
        select(Deadline).where(
            Deadline.id == deadline_id, Deadline.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Prazo não encontrado")
    if d.case_id:
        await verificar_acesso_caso(db, cu, d.case_id)

    if not d.confirmado:
        d.confirmado = True
        await criar_audit_log(
            db, cu.id, cu.role.value, "PRAZO_CONFIRMADO", "deadlines", deadline_id,
        )
        await db.commit()
        await db.refresh(d)
    return DeadlineResponse.model_validate(d)


@router.post("/{deadline_id}/ciencia", response_model=MsgResponse)
async def confirmar_ciencia(
    deadline_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Confirmação de ciência do prazo (rastro LGPD/responsabilidade)."""
    d = (await db.execute(
        select(Deadline).where(
            Deadline.id == deadline_id, Deadline.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Prazo não encontrado")
    if d.case_id:
        await verificar_acesso_caso(db, cu, d.case_id)

    d.ciencia_confirmada = True
    d.ciencia_confirmada_em = datetime.now(timezone.utc)
    d.ciencia_confirmada_por = cu.id
    await criar_audit_log(
        db, cu.id, cu.role.value, "CIENCIA_PRAZO", "deadlines", deadline_id,
    )
    await db.commit()
    return MsgResponse(detail="Ciência confirmada")


@router.delete("/{deadline_id}", response_model=MsgResponse)
async def cancelar(
    deadline_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if cu.role.value not in ("admin", "socio", "advogado"):
        raise HTTPException(status_code=403, detail="Sem permissão para cancelar prazos")
    d = (await db.execute(
        select(Deadline).where(
            Deadline.id == deadline_id, Deadline.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Prazo não encontrado")
    if d.case_id:
        await verificar_acesso_caso(db, cu, d.case_id)
    d.deleted_at = datetime.now(timezone.utc)
    d.status = "cancelado"
    await criar_audit_log(db, cu.id, cu.role.value, "DELETE", "deadlines", deadline_id)
    await db.commit()
    return MsgResponse(detail="Prazo cancelado")
