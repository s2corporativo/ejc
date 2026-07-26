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
from sqlalchemy import select, func as sqlfunc, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, requer_advogado, ROLE_LEVEL
from app.core.ownership import verificar_acesso_caso, is_gestao, role_str
from app.models.user import User
from app.models.case import Case
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


def _ids_casos_do_usuario(user: User):
    """IDs dos casos onde o usuário é responsável ou auxiliar (espelha
    fees._ids_casos_do_usuario / verificar_acesso_caso)."""
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


def _eh_advogado(cu: User) -> bool:
    """True se o usuário é advogado+ (advogado=6, socio=7, admin=8, superadmin=9).
    Espelho NÃO-levantador de `requer_advogado` — para decidir fluxo (rascunho vs
    confirmado, gate de prazo avulso) sem estourar 403 na hora."""
    return ROLE_LEVEL.get(role_str(cu), 0) >= ROLE_LEVEL["advogado"]


def _pode_mutar_prazo_avulso(cu: User, d: Deadline) -> bool:
    """[SYS-035] Prazo AVULSO (case_id=NULL) não tem gate de caso: só o dono
    (owner_id), o criador (created_by), o responsável direto (responsavel_id) ou
    advogado+ podem alterar/confirmar. Fecha a brecha de qualquer interno mexer
    em prazo avulso alheio."""
    if _eh_advogado(cu):
        return True
    return cu.id in (d.owner_id, d.created_by, d.responsavel_id)


def _gate_mutacao_prazo(cu: User, d: Deadline) -> None:
    """Gate de ESCRITA unificado por prazo já carregado. Prazo COM caso segue o
    gate canônico de caso (verificar_acesso_caso, chamado pelo handler); prazo
    SEM caso passa pelo escopo de dono acima."""
    if d.case_id:
        return  # handler chama verificar_acesso_caso (async) separadamente
    if not _pode_mutar_prazo_avulso(cu, d):
        raise HTTPException(status_code=403, detail="Sem permissão para este prazo")


def _filtro_escopo_prazos(q, cu: User):
    """[A3/SYS-036] Escopo de ownership por DEFAULT para não-gestão: só prazos de
    casos próprios (responsável/auxiliar), prazos onde é o responsável direto, ou
    prazos AVULSOS (sem caso) DE QUE É DONO — owner_id/created_by/responsavel_id.
    Antes o ramo de avulsos (`case_id IS NULL`) era amplo e expunha prazo avulso
    de qualquer um. Gestão (socio+) enxerga tudo. Espelha fees._filtro_fees_lista."""
    if is_gestao(cu):
        return q
    return q.where(
        or_(
            Deadline.case_id.in_(_ids_casos_do_usuario(cu)),
            Deadline.responsavel_id == cu.id,
            and_(
                Deadline.case_id.is_(None),
                or_(
                    Deadline.owner_id == cu.id,
                    Deadline.created_by == cu.id,
                    Deadline.responsavel_id == cu.id,
                ),
            ),
        )
    )


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
    # [A3] Escopo de ownership por DEFAULT (não-gestão só vê prazos dos próprios
    # casos / avulsos); gestão vê tudo. `apenas_meus` continua estreitando p/
    # os prazos onde o usuário é o responsável direto.
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
    # [A3] Mesmo escopo de ownership do GET /deadlines: não-gestão só exporta os
    # prazos que já enxerga; gestão exporta tudo.
    q = _filtro_escopo_prazos(q, cu)
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

    # [SYS-034] Prazo JURÍDICO confirmado (fatal) só nasce das mãos de advogado+.
    # Perfis operacionais (secretaria/estagiário) podem lançar o prazo, mas ele
    # nasce como RASCUNHO (confirmado=False, "a confirmar") — nunca prazo fatal
    # confirmado. Um advogado depois valida via PATCH /confirmar. O prazo já
    # dispara alertas mesmo como rascunho (semântica do Gap C #83).
    eh_advogado = _eh_advogado(cu)
    responsavel = payload.responsavel_id or cu.id
    d = Deadline(
        id=str(uuid4()),
        titulo=payload.titulo, tipo=payload.tipo,
        prioridade=payload.prioridade, descricao=payload.descricao,
        data_prazo=data_prazo, data_intimacao=payload.data_intimacao,
        base_legal=base, case_id=payload.case_id,
        responsavel_id=responsavel,
        owner_id=responsavel,          # responsável jurídico = dono do prazo
        created_by=cu.id,              # autoria (trilha de quem lançou)
        confirmado=eh_advogado,        # não-advogado → rascunho (a confirmar)
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
    else:
        _gate_mutacao_prazo(cu, d)  # [SYS-035] prazo avulso: só dono/criador/advogado+

    mudancas = payload.model_dump(exclude_unset=True)
    # Status ANTES de aplicar mudanças (o loop abaixo sobrescreve d.status):
    # usado para gravar a baixa só na TRANSIÇÃO para concluído (idempotente).
    status_antes = getattr(d.status, "value", d.status)
    # Alteração de data_prazo é sensível: audit detalhado
    if "data_prazo" in mudancas and mudancas["data_prazo"] != d.data_prazo:
        await criar_audit_log(
            db, cu.id, cu.role.value, "PRAZO_ALTERADO", "deadlines", deadline_id,
            dados_antes={"data_prazo": str(d.data_prazo)},
            dados_depois={"data_prazo": str(mudancas["data_prazo"])},
        )
    for k, v in mudancas.items():
        setattr(d, k, v)
    # Baixa (conclusão): além de carimbar data_conclusao, registra QUEM concluiu
    # e deixa trilha PRAZO_CONCLUIDO. Guarda `status_antes != concluido` evita
    # regravar audit/autor quando o prazo já estava concluído (idempotente,
    # mesmo padrão de `confirmar`).
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
    """Confirma um prazo RASCUNHO extraído por IA (confirmado=false → true, #83
    Gap C). O prazo já dispara alertas mesmo como rascunho — isto apenas remove
    a marca "a confirmar" e deixa trilha de auditoria (PRAZO_CONFIRMADO).

    [SYS-035] A CONFIRMAÇÃO de prazo fatal é ato jurídico: exige advogado+
    (advogado responsável/sócio), nunca qualquer interno. Prazo COM caso mantém
    o gate de caso; prazo avulso já é coberto pelo piso de advogado. Idempotente:
    reconfirmar não regrava audit."""
    # Piso por NÍVEL (advogado+) — perfis operacionais não confirmam prazo fatal.
    requer_advogado(cu, detail="Confirmação de prazo exige advogado responsável")
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
    else:
        _gate_mutacao_prazo(cu, d)  # [SYS-035] prazo avulso: só dono/criador/advogado+

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
    # [B1] Piso por NÍVEL (advogado+), não por tupla literal — a lista antiga
    # ("admin","socio","advogado") excluía superadmin(9) e causava lockout do
    # superadmin. requer_advogado garante advogado(6)+ e nunca barra superadmin.
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
