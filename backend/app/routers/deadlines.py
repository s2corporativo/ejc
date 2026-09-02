# ── app/routers/deadlines.py ─────────────────────────────────────────────────
# Prazos: CRUD + cálculo automático por regime + confirmação de ciência
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
from app.services.case_mutation_guard import verificar_caso_editavel
from app.services.deadline_calculator import (
    calcular_prazo_processual,
    dias_uteis_restantes,
    prazo_dias_corridos,
    prazo_dias_uteis,
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


def _resolver_regime_processual(regime: str | None, dias_uteis: bool) -> tuple[str, bool]:
    """Resolve o regime sem permitir que contagem corrida ambígua vire CPC.

    Compatibilidade: clientes antigos que enviavam `tipo=processual` e
    `dias_uteis=true` continuam como cível. O frontend atual sempre manda o
    regime explicitamente. `dias_uteis=false` sem regime é bloqueado, pois pode
    ser penal e não deve receber um algoritmo administrativo por acidente.
    """
    if regime:
        return regime, False
    if dias_uteis:
        return "civel", True
    raise HTTPException(
        status_code=422,
        detail=(
            "Prazo processual com contagem não útil exige regime_calculo explícito. "
            "Use civel, trabalhista ou penal; o sistema não presume regime penal."
        ),
    )


def _base_processual(regime: str, dias: int, dobro: bool, *, legado: bool,
                     excecao_recesso_penal: bool) -> str:
    if regime == "penal":
        base = f"{dias} dias — CPP art. 798 c/c art. 798-A"
        if excecao_recesso_penal:
            base += " (exceção ao recesso declarada pelo operador)"
    elif regime == "trabalhista":
        base = f"{dias} dias úteis — CLT arts. 775 e 775-A"
    else:
        base = (
            f"{dias} dias úteis em dobro (CPC arts. 180/183/186/229)"
            if dobro
            else f"{dias} dias úteis (CPC art. 219)"
        )
        base += " + recesso forense integral (CPC art. 220)"
    if legado:
        base += " · regime cível assumido por compatibilidade; conferir"
    return base


@router.post("/calcular")
async def calcular(req: CalcularPrazoRequest, cu: User = Depends(get_current_user)):
    """Calculadora rápida, sem persistir, com regime processual explícito."""
    del cu
    if req.dias < 1:
        raise HTTPException(status_code=422, detail="dias deve ser maior que zero")

    if req.tipo == "processual":
        regime, legado = _resolver_regime_processual(req.regime_calculo, req.dias_uteis)
        if req.excecao_recesso_penal and regime != "penal":
            raise HTTPException(
                status_code=422,
                detail="excecao_recesso_penal só é válida para regime penal",
            )
        try:
            resultado = calcular_prazo_processual(
                req.data_inicio,
                req.dias,
                regime,  # type: ignore[arg-type]
                tribunal=req.tribunal,
                em_dobro=req.dobro,
                excecao_recesso_penal=req.excecao_recesso_penal,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        resultado["regime_assumido_por_compatibilidade"] = legado
        resultado["dias_uteis_restantes"] = dias_uteis_restantes(
            resultado["data_vencimento"]
        )
        return resultado

    if req.excecao_recesso_penal or req.regime_calculo == "penal":
        raise HTTPException(
            status_code=422,
            detail="Regime penal só pode ser usado em prazo tipo=processual",
        )

    if req.dias_uteis:
        vencimento = prazo_dias_uteis(
            req.data_inicio,
            req.dias,
            tribunal=req.tribunal,
            em_dobro=req.dobro,
            aplicar_recesso=False,
            forense=False,
        )
        modo = "dias úteis sem recesso processual"
    else:
        vencimento = prazo_dias_corridos(
            req.data_inicio, req.dias, tribunal=req.tribunal
        )
        modo = "dias corridos c/ prorrogação do termo final (Lei 9.784 art. 66 §1º)"
    return {
        "data_vencimento": vencimento,
        "modo": modo,
        "regime_calculo": "administrativo" if req.tipo == "administrativo" else None,
        "resultado_preliminar": False,
        "revisao_obrigatoria": False,
        "aviso": None,
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
    q = _filtro_escopo_prazos(q, cu)
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
    return "﻿" + buf.getvalue()


@router.post("/", status_code=201)
async def criar(
    payload: DeadlineCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    data_prazo = payload.data_prazo
    base = payload.base_legal
    confirmado = True
    calculo_audit: dict | None = None

    if not data_prazo and payload.dias_prazo and payload.data_intimacao:
        if payload.tipo == "processual":
            regime, legado = _resolver_regime_processual(
                payload.regime_calculo, payload.dias_uteis
            )
            if payload.excecao_recesso_penal and regime != "penal":
                raise HTTPException(
                    status_code=422,
                    detail="excecao_recesso_penal só é válida para regime penal",
                )
            try:
                calculo_audit = calcular_prazo_processual(
                    payload.data_intimacao,
                    payload.dias_prazo,
                    regime,  # type: ignore[arg-type]
                    tribunal=payload.tribunal,
                    em_dobro=payload.dobro,
                    excecao_recesso_penal=payload.excecao_recesso_penal,
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            data_prazo = calculo_audit["data_vencimento"]
            base = base or _base_processual(
                regime,
                payload.dias_prazo,
                payload.dobro,
                legado=legado,
                excecao_recesso_penal=payload.excecao_recesso_penal,
            )
            if calculo_audit["resultado_preliminar"]:
                confirmado = False
                base += " · CALENDÁRIO DEGRADADO: conferência humana obrigatória"
        elif payload.dias_uteis:
            data_prazo = prazo_dias_uteis(
                payload.data_intimacao,
                payload.dias_prazo,
                tribunal=payload.tribunal,
                em_dobro=payload.dobro,
                aplicar_recesso=False,
                forense=False,
            )
            base = base or f"{payload.dias_prazo} dias úteis (sem recesso processual)"
        else:
            data_prazo = prazo_dias_corridos(
                payload.data_intimacao,
                payload.dias_prazo,
                tribunal=payload.tribunal,
            )
            base = base or f"{payload.dias_prazo} dias corridos (Lei 9.784)"

    if not data_prazo:
        raise HTTPException(
            status_code=422,
            detail="Informe data_prazo OU (data_intimacao + dias_prazo)",
        )

    if payload.case_id:
        await verificar_caso_editavel(db, cu, payload.case_id)

    d = Deadline(
        id=str(uuid4()),
        titulo=payload.titulo,
        tipo=payload.tipo,
        prioridade=payload.prioridade,
        descricao=payload.descricao,
        data_prazo=data_prazo,
        data_intimacao=payload.data_intimacao,
        base_legal=base,
        case_id=payload.case_id,
        responsavel_id=payload.responsavel_id or cu.id,
        confirmado=confirmado,
    )
    db.add(d)
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "CREATE",
        "deadlines",
        d.id,
        dados_depois=(
            {
                "calculo_automatico": True,
                "regime_calculo": calculo_audit.get("regime_calculo"),
                "calendario_status": calculo_audit.get("calendario_status"),
                "resultado_preliminar": calculo_audit.get("resultado_preliminar"),
            }
            if calculo_audit else {"calculo_automatico": False}
        ),
    )
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
        await verificar_caso_editavel(db, cu, d.case_id)
        # O prazo foi lido antes do lock para descobrir o case_id. Reidrata após
        # o lock para não aplicar um PATCH sobre estado ORM obsoleto caso outro
        # request do mesmo caso tenha aguardado/commitado antes.
        await db.refresh(d)

    mudancas = payload.model_dump(exclude_unset=True)
    status_antes = getattr(d.status, "value", d.status)
    if "data_prazo" in mudancas and mudancas["data_prazo"] != d.data_prazo:
        await criar_audit_log(
            db, cu.id, cu.role.value, "PRAZO_ALTERADO", "deadlines", deadline_id,
            dados_antes={"data_prazo": str(d.data_prazo)},
            dados_depois={"data_prazo": str(mudancas["data_prazo"])},
        )
    for k, v in mudancas.items():
        setattr(d, k, v)

    # Reagendar para o futuro devolve o prazo a 'pendente' (achado 29, 22/08).
    # `exclude_unset` faz o PATCH aplicar só o que veio: `CentralAtividades`
    # reagenda mandando SÓ `data_prazo`, então o status 'vencido' escrito pelo
    # job das 07:10 (`scheduler._marcar_prazos_vencidos`) sobrevivia à mudança e
    # o prazo aparecia como vencido com data futura. É a regra inversa do job —
    # ele faz pendente→vencido quando a data passa; aqui é vencido→pendente
    # quando a data volta para frente. Sem isso, a aba "Vencidos" mostrava
    # prazo que não venceu, e o painel (que conta por DATA) discordava da
    # listagem (que filtra por STATUS) sobre o mesmo prazo.
    #
    # Só toca o par (vencido → data futura): status definido explicitamente
    # nesta chamada manda, e 'concluido'/'cancelado' nunca são reabertos por
    # uma troca de data.
    if (
        "data_prazo" in mudancas
        and "status" not in mudancas
        and getattr(d.status, "value", d.status) == "vencido"
        and d.data_prazo >= date.today()
    ):
        d.status = "pendente"
        await criar_audit_log(
            db, cu.id, cu.role.value, "PRAZO_REABERTO", "deadlines", deadline_id,
            dados_antes={"status": "vencido"},
            dados_depois={"status": "pendente",
                          "motivo": "reagendado para data futura"},
        )

    if mudancas.get("status") == "concluido" and status_antes != "concluido":
        d.data_conclusao = datetime.now(timezone.utc)
        d.concluido_por = cu.id
        await criar_audit_log(
            db, cu.id, cu.role.value, "PRAZO_CONCLUIDO", "deadlines", deadline_id,
            dados_antes={"status": status_antes},
            dados_depois={
                "status": "concluido",
                "concluido_por": cu.id,
                "data_conclusao": d.data_conclusao.isoformat(),
            },
        )
    await db.commit()
    await db.refresh(d)
    return DeadlineResponse.model_validate(d)


@router.patch("/{deadline_id}/confirmar", response_model=DeadlineResponse)
async def confirmar(
    deadline_id: str,
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
    requer_advogado(cu, detail="Sem permissão para cancelar prazos")
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
