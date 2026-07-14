# ── app/routers/atendimentos.py ────────────────────────────────────────────────
# Histórico de atendimentos ao cliente — CRM básico jurídico.
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.security import ROLE_LEVEL, get_current_user
from app.models.atendimento import Atendimento, AtendimentoTipo
from app.models.client import Client
from app.models.user import User
from app.modules.auditoria.middleware import registrar_acao

router = APIRouter(prefix="/atendimentos", tags=["Atendimentos"])

# O módulo Clientes usa esta mesma matriz. A lista explícita evita que perfis
# internos sem atribuição de CRM (financeiro, estagiário e auxiliar) recebam
# acesso apenas por estarem numericamente acima de secretaria em ROLE_LEVEL.
_ATENDIMENTO_ROLES = {"superadmin", "admin", "socio", "advogado", "secretaria"}


# ── Schemas ───────────────────────────────────────────────────────────────────

class AtendimentoIn(BaseModel):
    client_id:               str
    case_id:                 Optional[str]   = None
    tipo:                    AtendimentoTipo
    data_atendimento:        datetime
    duracao_min:             Optional[str]   = Field(None, max_length=10)
    resumo:                  str = Field(min_length=10, max_length=4000)
    proximo_passo:           Optional[str]   = Field(None, max_length=4000)
    solicitacao:             Optional[str]   = Field(None, max_length=4000)
    solicitacao_atendida:    bool            = False
    observacoes_privadas:    Optional[str]   = Field(None, max_length=4000)
    advogado_responsavel_id: Optional[str]   = None
    duracao_horas:           Optional[float] = Field(None, ge=0, le=24)
    satisfacao_cliente:      Optional[int]   = Field(None, ge=1, le=5)


class AtendimentoPatch(BaseModel):
    tipo:                    Optional[AtendimentoTipo] = None
    data_atendimento:        Optional[datetime]        = None
    duracao_min:             Optional[str]             = Field(None, max_length=10)
    resumo:                  Optional[str]             = Field(None, min_length=10, max_length=4000)
    proximo_passo:           Optional[str]             = Field(None, max_length=4000)
    solicitacao:             Optional[str]             = Field(None, max_length=4000)
    solicitacao_atendida:    Optional[bool]            = None
    observacoes_privadas:    Optional[str]             = Field(None, max_length=4000)
    advogado_responsavel_id: Optional[str]             = None
    duracao_horas:           Optional[float]           = Field(None, ge=0, le=24)
    satisfacao_cliente:      Optional[int]             = Field(None, ge=1, le=5)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _role_str(user: User) -> str:
    role = getattr(user, "role", None)
    return role.value if hasattr(role, "value") else str(role)


def _is_staff(user: User) -> bool:
    return _role_str(user) in _ATENDIMENTO_ROLES


def _pode_ver_privado(user: User) -> bool:
    return ROLE_LEVEL.get(_role_str(user), 0) >= ROLE_LEVEL["advogado"]


def _pode_editar_atendimento(a: Atendimento, user: User) -> bool:
    if not _is_staff(user):
        return False
    if ROLE_LEVEL.get(_role_str(user), 0) >= ROLE_LEVEL["socio"]:
        return True
    return user.id in {a.created_by, a.advogado_responsavel_id}


def _out(a: Atendimento, user: User, com_privado: bool = True) -> dict:
    return {
        "id":                      a.id,
        "client_id":               a.client_id,
        "case_id":                 a.case_id,
        "tipo":                    a.tipo.value if hasattr(a.tipo, "value") else a.tipo,
        "data_atendimento":        a.data_atendimento.isoformat() if a.data_atendimento else None,
        "duracao_min":             a.duracao_min,
        "duracao_horas":           float(a.duracao_horas) if a.duracao_horas is not None else None,
        "resumo":                  a.resumo,
        "proximo_passo":           a.proximo_passo,
        "solicitacao":             a.solicitacao,
        "solicitacao_atendida":    bool(a.solicitacao_atendida),
        "atendida_em":             a.atendida_em.isoformat() if a.atendida_em else None,
        "atendida_por_id":         a.atendida_por_id,
        "observacoes_privadas":    a.observacoes_privadas if com_privado else None,
        "advogado_responsavel_id": a.advogado_responsavel_id,
        "satisfacao_cliente":      a.satisfacao_cliente,
        "created_by":              a.created_by,
        "created_at":              a.created_at.isoformat() if a.created_at else None,
        "updated_at":              a.updated_at.isoformat() if a.updated_at else None,
        "pode_editar":             _pode_editar_atendimento(a, user),
    }


async def _obter_atendimento(atendimento_id: str, db: AsyncSession) -> Atendimento:
    atendimento = (await db.execute(
        select(Atendimento).where(Atendimento.id == atendimento_id)
    )).scalar_one_or_none()
    if atendimento is None:
        raise HTTPException(status_code=404, detail="Atendimento não encontrado")
    return atendimento


async def _validar_cliente(db: AsyncSession, client_id: str) -> Client:
    cliente = (await db.execute(
        select(Client).where(Client.id == client_id, Client.deleted_at.is_(None))
    )).scalar_one_or_none()
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return cliente


async def _validar_responsavel(db: AsyncSession, user_id: Optional[str]) -> None:
    if not user_id:
        return
    responsavel = (await db.execute(
        select(User).where(User.id == user_id, User.is_active.is_(True))
    )).scalar_one_or_none()
    if responsavel is None or _role_str(responsavel) not in _ATENDIMENTO_ROLES:
        raise HTTPException(status_code=422, detail="Responsável pelo atendimento inválido")


def _aplicar_status_solicitacao(
    atendimento: Atendimento,
    atendida: bool,
    user_id: str,
) -> None:
    if atendida and not (atendimento.solicitacao or "").strip():
        raise HTTPException(
            status_code=422,
            detail="Informe o que foi solicitado antes de marcar como atendido",
        )
    atendimento.solicitacao_atendida = atendida
    atendimento.atendida_em = datetime.now(timezone.utc) if atendida else None
    atendimento.atendida_por_id = user_id if atendida else None


# ── Endpoints base ─────────────────────────────────────────────────────────────

@router.get("")
async def listar_atendimentos(
    client_id:             Optional[str] = Query(None),
    case_id:               Optional[str] = Query(None),
    tipo:                  Optional[AtendimentoTipo] = Query(None),
    advogado_id:           Optional[str] = Query(None),
    solicitacao_atendida:  Optional[bool] = Query(None),
    page:                  int = Query(1, ge=1),
    per_page:              int = Query(20, ge=1, le=100),
    db:                    AsyncSession = Depends(get_db),
    cu:                    User = Depends(get_current_user),
):
    if not _is_staff(cu):
        raise HTTPException(status_code=403, detail="Sem permissão para atendimentos")
    if client_id:
        await _validar_cliente(db, client_id)

    q = select(Atendimento)
    if client_id:
        q = q.where(Atendimento.client_id == client_id)
    if case_id:
        q = q.where(Atendimento.case_id == case_id)
    if tipo:
        q = q.where(Atendimento.tipo == tipo)
    if advogado_id:
        q = q.where(Atendimento.advogado_responsavel_id == advogado_id)
    if solicitacao_atendida is not None:
        q = q.where(Atendimento.solicitacao_atendida == solicitacao_atendida)

    q = q.order_by(Atendimento.data_atendimento.desc())
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    items = (await db.execute(
        q.offset((page - 1) * per_page).limit(per_page)
    )).scalars().all()
    privado = _pode_ver_privado(cu)
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": [_out(a, cu, com_privado=privado) for a in items],
    }


@router.post("", status_code=201)
async def criar_atendimento(
    req: AtendimentoIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_staff(cu):
        raise HTTPException(status_code=403, detail="Sem permissão para atendimentos")

    await _validar_cliente(db, req.client_id)
    if req.case_id:
        caso = await verificar_acesso_caso(db, cu, req.case_id)
        if caso.client_id != req.client_id:
            raise HTTPException(
                status_code=422,
                detail="O caso informado não pertence ao cliente",
            )

    data = req.model_dump(exclude={"solicitacao_atendida"})
    if not data.get("advogado_responsavel_id"):
        data["advogado_responsavel_id"] = cu.id
    await _validar_responsavel(db, data["advogado_responsavel_id"])

    atendimento = Atendimento(id=str(uuid4()), created_by=cu.id, **data)
    _aplicar_status_solicitacao(atendimento, req.solicitacao_atendida, cu.id)
    db.add(atendimento)
    await db.commit()
    await db.refresh(atendimento)

    await registrar_acao(
        db,
        cu.id,
        "criar",
        "atendimentos",
        atendimento.id,
        f"Atendimento {atendimento.tipo} registrado para cliente {atendimento.client_id}",
    )
    return _out(atendimento, cu, com_privado=_pode_ver_privado(cu))


@router.get("/meus")
async def meus_atendimentos(
    page:     int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db:       AsyncSession = Depends(get_db),
    cu:       User = Depends(get_current_user),
):
    """Atendimentos em que o usuário autenticado é o responsável."""
    if not _is_staff(cu):
        raise HTTPException(status_code=403, detail="Sem permissão para atendimentos")
    q = (
        select(Atendimento)
        .where(Atendimento.advogado_responsavel_id == cu.id)
        .order_by(Atendimento.data_atendimento.desc())
    )
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    items = (await db.execute(
        q.offset((page - 1) * per_page).limit(per_page)
    )).scalars().all()
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": [_out(a, cu, com_privado=_pode_ver_privado(cu)) for a in items],
    }


@router.get("/por-advogado/{advogado_id}")
async def por_advogado(
    advogado_id: str,
    page:        int = Query(1, ge=1),
    per_page:    int = Query(20, ge=1, le=100),
    db:          AsyncSession = Depends(get_db),
    cu:          User = Depends(get_current_user),
):
    """Lista atendimentos de um responsável específico."""
    if not _is_staff(cu):
        raise HTTPException(status_code=403, detail="Sem permissão para atendimentos")
    nivel = ROLE_LEVEL.get(_role_str(cu), 0)
    if advogado_id != cu.id and nivel < ROLE_LEVEL["socio"]:
        raise HTTPException(
            status_code=403,
            detail="Somente a gestão pode ver atendimentos de outros responsáveis",
        )

    q = (
        select(Atendimento)
        .where(Atendimento.advogado_responsavel_id == advogado_id)
        .order_by(Atendimento.data_atendimento.desc())
    )
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    items = (await db.execute(
        q.offset((page - 1) * per_page).limit(per_page)
    )).scalars().all()
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": [_out(a, cu, com_privado=_pode_ver_privado(cu)) for a in items],
    }


@router.get("/dashboard")
async def dashboard_atendimentos(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Estatísticas agregadas por responsável.
    Somente a gestão visualiza todos; demais veem apenas o próprio.
    """
    if not _is_staff(cu):
        raise HTTPException(status_code=403, detail="Sem permissão para atendimentos")

    nivel = ROLE_LEVEL.get(_role_str(cu), 0)
    q_base = select(
        Atendimento.advogado_responsavel_id,
        func.count(Atendimento.id).label("total"),
        func.coalesce(func.sum(Atendimento.duracao_horas), 0).label("total_horas"),
        func.coalesce(func.avg(Atendimento.satisfacao_cliente), 0).label("satisfacao_media"),
    ).group_by(Atendimento.advogado_responsavel_id)

    if nivel < ROLE_LEVEL["socio"]:
        q_base = q_base.where(Atendimento.advogado_responsavel_id == cu.id)

    rows = (await db.execute(q_base)).all()
    return [
        {
            "advogado_id": r.advogado_responsavel_id,
            "total_atendimentos": r.total,
            "total_horas": round(float(r.total_horas), 2),
            "satisfacao_media": round(float(r.satisfacao_media), 2),
        }
        for r in rows
    ]


@router.get("/stats")
async def stats_mensais(
    ano: int = Query(default=2026),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Breakdown mensal de atendimentos — quantidade e horas por mês."""
    if not _is_staff(cu):
        raise HTTPException(status_code=403, detail="Sem permissão para atendimentos")

    from sqlalchemy import extract

    nivel = ROLE_LEVEL.get(_role_str(cu), 0)
    q = (
        select(
            extract("month", Atendimento.data_atendimento).label("mes"),
            func.count(Atendimento.id).label("total"),
            func.coalesce(func.sum(Atendimento.duracao_horas), 0).label("total_horas"),
            func.coalesce(func.avg(Atendimento.satisfacao_cliente), 0).label("satisfacao_media"),
        )
        .where(extract("year", Atendimento.data_atendimento) == ano)
        .group_by(extract("month", Atendimento.data_atendimento))
        .order_by(extract("month", Atendimento.data_atendimento))
    )

    if nivel < ROLE_LEVEL["socio"]:
        q = q.where(Atendimento.advogado_responsavel_id == cu.id)

    rows = (await db.execute(q)).all()
    meses = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
             "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
    return [
        {
            "mes": int(r.mes),
            "mes_nome": meses[int(r.mes) - 1],
            "total": r.total,
            "total_horas": round(float(r.total_horas), 2),
            "satisfacao_media": round(float(r.satisfacao_media), 2),
        }
        for r in rows
    ]


# ── Endpoints individuais ──────────────────────────────────────────────────────

@router.get("/{atendimento_id}")
async def obter_atendimento(
    atendimento_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_staff(cu):
        raise HTTPException(status_code=403, detail="Sem permissão para atendimentos")
    atendimento = await _obter_atendimento(atendimento_id, db)
    return _out(atendimento, cu, com_privado=_pode_ver_privado(cu))


@router.patch("/{atendimento_id}")
async def atualizar_atendimento(
    atendimento_id: str,
    req: AtendimentoPatch,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_staff(cu):
        raise HTTPException(status_code=403, detail="Sem permissão para atendimentos")
    atendimento = await _obter_atendimento(atendimento_id, db)
    if not _pode_editar_atendimento(atendimento, cu):
        raise HTTPException(status_code=403, detail="Sem permissão para editar este atendimento")

    data = req.model_dump(exclude_unset=True)
    for obrigatorio in ("tipo", "data_atendimento", "resumo"):
        if obrigatorio in data and data[obrigatorio] is None:
            raise HTTPException(status_code=422, detail=f"{obrigatorio} não pode ser nulo")

    status_solicitacao = data.pop("solicitacao_atendida", None)
    if "advogado_responsavel_id" in data:
        await _validar_responsavel(db, data["advogado_responsavel_id"])

    for campo, valor in data.items():
        setattr(atendimento, campo, valor)
    if status_solicitacao is not None:
        _aplicar_status_solicitacao(atendimento, status_solicitacao, cu.id)
    elif not (atendimento.solicitacao or "").strip():
        _aplicar_status_solicitacao(atendimento, False, cu.id)

    atendimento.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(atendimento)

    await registrar_acao(
        db,
        cu.id,
        "atualizar",
        "atendimentos",
        atendimento.id,
        "Atendimento atualizado; campos: " + ", ".join(sorted(req.model_fields_set)),
    )
    return _out(atendimento, cu, com_privado=_pode_ver_privado(cu))


@router.delete("/{atendimento_id}", status_code=204)
async def remover_atendimento(
    atendimento_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_staff(cu) or ROLE_LEVEL.get(_role_str(cu), 0) < ROLE_LEVEL["advogado"]:
        raise HTTPException(status_code=403, detail="Sem permissão para excluir atendimentos")
    atendimento = await _obter_atendimento(atendimento_id, db)
    if not _pode_editar_atendimento(atendimento, cu):
        raise HTTPException(status_code=403, detail="Sem permissão para excluir este atendimento")

    atendimento_id_audit = atendimento.id
    cliente_id_audit = atendimento.client_id
    await db.delete(atendimento)
    await db.commit()
    await registrar_acao(
        db,
        cu.id,
        "excluir",
        "atendimentos",
        atendimento_id_audit,
        f"Atendimento removido do cliente {cliente_id_audit}",
    )
