# ── app/routers/portal.py ────────────────────────────────────────────────────
# Portal do Cliente: acesso EXTERNO read-only.
# Segurança em camadas:
#   1. Middleware confina cliente_externo a /api/portal/*
#   2. Cada endpoint filtra por cu.client_id (nunca expõe dados de terceiros)
#   3. Documentos: apenas confidencialidade=normal
#   4. Estratégia do caso (tese, pontos fortes/fracos) NUNCA é exposta
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User, UserRole
from app.models.case import Case, CaseMovimento
from app.models.deadline import Deadline
from app.models.fee import Fee
from app.models.document import Document, DocConfidencialidade

router = APIRouter(prefix="/portal", tags=["Portal do Cliente"])


def _exigir_cliente(cu: User) -> str:
    """Garante perfil cliente_externo com vínculo; retorna client_id."""
    if cu.role != UserRole.cliente_externo or not cu.client_id:
        raise HTTPException(status_code=403, detail="Acesso exclusivo do Portal do Cliente")
    return cu.client_id


@router.get("/meus-casos")
async def meus_casos(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    client_id = _exigir_cliente(cu)
    rows = (await db.execute(
        select(Case).where(
            Case.client_id == client_id, Case.deleted_at.is_(None)
        ).order_by(Case.created_at.desc())
    )).scalars().all()
    # Visão do cliente: status e dados públicos — SEM estratégia interna
    return {"data": [
        {"id": c.id, "numero_interno": c.numero_interno, "titulo": c.titulo,
         "area": c.area.value if hasattr(c.area, "value") else str(c.area),
         "status": c.status.value if hasattr(c.status, "value") else str(c.status),
         "numero_processo": c.numero_processo, "comarca": c.comarca,
         "created_at": c.created_at}
        for c in rows
    ]}


@router.get("/casos/{case_id}")
async def caso_detalhe(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    client_id = _exigir_cliente(cu)
    c = (await db.execute(select(Case).where(
        Case.id == case_id, Case.client_id == client_id,  # ← isolamento
        Case.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Caso não encontrado")

    movs = (await db.execute(
        select(CaseMovimento).where(CaseMovimento.case_id == case_id)
        .order_by(CaseMovimento.data_evento.desc()).limit(50)
    )).scalars().all()

    prazos = (await db.execute(
        select(Deadline).where(
            Deadline.case_id == case_id, Deadline.deleted_at.is_(None),
            Deadline.status == "pendente",
        ).order_by(Deadline.data_prazo)
    )).scalars().all()

    return {
        "caso": {
            "numero_interno": c.numero_interno, "titulo": c.titulo,
            "status": c.status.value if hasattr(c.status, "value") else str(c.status),
            "numero_processo": c.numero_processo,
            "comarca": c.comarca, "vara": c.vara,
        },
        "andamentos": [
            {"data": m.data_evento, "descricao": m.descricao.split(" [dj:")[0]}
            for m in movs
        ],
        "proximas_datas": [
            {"titulo": d.titulo, "data": d.data_prazo} for d in prazos
        ],
    }


@router.get("/documentos")
async def documentos(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Apenas docs do cliente com confidencialidade NORMAL (liberados)."""
    client_id = _exigir_cliente(cu)
    rows = (await db.execute(
        select(Document).where(
            Document.client_id == client_id,
            Document.deleted_at.is_(None),
            Document.confidencialidade == DocConfidencialidade.normal,
        ).order_by(Document.created_at.desc())
    )).scalars().all()
    return {"data": [
        {"id": d.id, "titulo": d.titulo, "filename": d.filename,
         "created_at": d.created_at}
        for d in rows
    ]}


@router.get("/financeiro")
async def financeiro(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    client_id = _exigir_cliente(cu)
    rows = (await db.execute(
        select(Fee).where(
            Fee.client_id == client_id, Fee.deleted_at.is_(None),
        ).order_by(Fee.data_vencimento)
    )).scalars().all()
    return {"data": [
        {"descricao": f.descricao,
         "valor": float(f.valor) if f.valor else None,
         "vencimento": f.data_vencimento,
         "status": f.status.value if hasattr(f.status, "value") else str(f.status)}
        for f in rows
    ]}
