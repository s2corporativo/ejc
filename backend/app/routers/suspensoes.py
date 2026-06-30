# ── app/routers/suspensoes.py ────────────────────────────────────────────────
# Suspensões de prazo por tribunal + simulador de prazo ciente de suspensões.
from __future__ import annotations
from datetime import date
from uuid import uuid4
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models.user import User
from app.models.suspensao import SuspensaoTribunal
from app.models.audit_log import criar_audit_log
from app.services import deadline_calculator as dc

router = APIRouter(prefix="/suspensoes", tags=["Suspensões de Prazo"])

# Tribunais de uso frequente do escritório (MG + superiores). Campo é livre:
# a UI usa isto só como sugestão de preenchimento.
TRIBUNAIS_SUGERIDOS = [
    "TJMG", "TRT3", "TRF6", "JEF-MG", "STJ", "STF", "TST", "TSE", "STM",
]


# ── Schemas ───────────────────────────────────────────────────────────────────
class SuspensaoIn(BaseModel):
    tribunal: str = Field(..., min_length=2, max_length=40)
    data_inicio: date
    data_fim: date
    motivo: str = Field(..., min_length=3, max_length=255)
    ato_normativo: Optional[str] = Field(None, max_length=255)


class SimularIn(BaseModel):
    data_inicio: date                       # ciência/intimação
    dias: int = Field(..., ge=1, le=3650)
    contagem: Literal["uteis", "corridos"] = "uteis"
    tribunal: Optional[str] = None          # None = só feriados nacionais/municipais


def _serial(s: SuspensaoTribunal) -> dict:
    return {
        "id": s.id, "tribunal": s.tribunal,
        "data_inicio": s.data_inicio, "data_fim": s.data_fim,
        "motivo": s.motivo, "ato_normativo": s.ato_normativo,
        "dias": (s.data_fim - s.data_inicio).days + 1,
    }


async def _recarregar_cache():
    """Recarrega o cache do calculador após qualquer mudança."""
    await dc.carregar_suspensoes_db()


# ── Endpoints ─────────────────────────────────────────────────────────────────
@router.get("/tribunais")
async def tribunais(cu: User = Depends(get_current_user)):
    """Lista de tribunais sugeridos para o seletor da UI."""
    return {"tribunais": TRIBUNAIS_SUGERIDOS}


@router.get("/")
async def listar(
    tribunal: Optional[str] = None,
    vigentes: bool = Query(False, description="Apenas suspensões que ainda não terminaram"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Lista suspensões (visível a toda a equipe). Filtra por tribunal/vigência."""
    base = select(SuspensaoTribunal).where(SuspensaoTribunal.deleted_at.is_(None))
    if tribunal:
        base = base.where(SuspensaoTribunal.tribunal == tribunal)
    if vigentes:
        base = base.where(SuspensaoTribunal.data_fim >= date.today())
    total = (await db.execute(
        select(sqlfunc.count()).select_from(base.subquery())
    )).scalar_one()
    q = base.order_by(SuspensaoTribunal.data_inicio.desc()).limit(limit).offset(offset)
    rows = (await db.execute(q)).scalars().all()
    return {"data": [_serial(s) for s in rows], "total": total, "limit": limit, "offset": offset}


@router.post("/", status_code=201)
async def criar(
    body: SuspensaoIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio"])),
):
    """Registra uma suspensão (somente admin/sócio)."""
    if body.data_fim < body.data_inicio:
        raise HTTPException(422, "data_fim não pode ser anterior a data_inicio")
    s = SuspensaoTribunal(
        id=str(uuid4()),
        tribunal=body.tribunal.strip().upper(),
        data_inicio=body.data_inicio, data_fim=body.data_fim,
        motivo=body.motivo.strip(),
        ato_normativo=(body.ato_normativo or "").strip() or None,
        created_by=cu.id,
    )
    db.add(s)
    await criar_audit_log(
        db, cu.id, cu.role.value, "CREATE", "suspensoes_tribunal", s.id,
        detalhes=f"{s.tribunal} {s.data_inicio}→{s.data_fim}: {s.motivo}",
    )
    await db.commit()
    await _recarregar_cache()
    return _serial(s)


@router.delete("/{suspensao_id}")
async def remover(
    suspensao_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio"])),
):
    """Remove (soft-delete) uma suspensão."""
    s = (await db.execute(
        select(SuspensaoTribunal).where(
            SuspensaoTribunal.id == suspensao_id,
            SuspensaoTribunal.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Suspensão não encontrada")
    s.deleted_at = sqlfunc.now()
    await criar_audit_log(
        db, cu.id, cu.role.value, "DELETE", "suspensoes_tribunal", s.id,
        detalhes=f"{s.tribunal} {s.data_inicio}→{s.data_fim}",
    )
    await db.commit()
    await _recarregar_cache()
    return {"detail": "Suspensão removida"}


@router.post("/simular")
async def simular(
    body: SimularIn,
    cu: User = Depends(get_current_user),
):
    """
    Simula o vencimento de um prazo considerando feriados nacionais/municipais
    e, se informado o tribunal, também as suspensões dele.
    NÃO grava nada — apenas calcula (rascunho; o advogado decide).
    """
    if body.contagem == "uteis":
        venc = dc.prazo_dias_uteis(body.data_inicio, body.dias, tribunal=body.tribunal)
        base = "Dias úteis (CPC art. 219 / CLT art. 775)"
    else:
        venc = dc.prazo_dias_corridos(
            body.data_inicio, body.dias, prorrogar_fim=True, tribunal=body.tribunal
        )
        base = "Dias corridos c/ prorrogação (Lei 9.784/99 art. 66 §1º)"

    return {
        "data_inicio": body.data_inicio,
        "dias": body.dias,
        "contagem": body.contagem,
        "tribunal": body.tribunal,
        "data_vencimento": venc,
        "base_legal": base,
        "aviso": "Cálculo de apoio. Confirme suspensões/portarias vigentes do tribunal.",
    }
