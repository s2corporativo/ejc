# ── app/routers/search.py ─────────────────────────────────────────────────────
# Busca global unificada (clientes, casos, peças) respeitando o escopo do perfil.
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import get_current_user, ROLE_LEVEL
from app.models.user import User
from app.models.client import Client
from app.models.case import Case
from app.models.legal_doc import LegalDoc

router = APIRouter(prefix="/search", tags=["Busca global"])


def _ve_todos(user: User) -> bool:
    return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["socio"]


@router.get("")
@router.get("/")
@limiter.limit("30/minute")
async def busca_global(
    request: Request,
    q: str = Query(..., min_length=2, max_length=120),
    limit: int = Query(6, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Busca unificada em clientes, casos e peças (escopo por perfil)."""
    if cu.role.value == "cliente_externo":
        return {"q": q, "resultados": []}   # o portal do cliente tem visão própria

    termo = f"%{q.strip()}%"
    out = []

    # ── Clientes ──
    cli = (await db.execute(
        select(Client).where(
            Client.deleted_at.is_(None),
            or_(Client.nome.ilike(termo), Client.razao_social.ilike(termo),
                Client.cpf.ilike(termo), Client.cnpj.ilike(termo)),
        ).limit(limit)
    )).scalars().all()
    for c in cli:
        out.append({"tipo": "cliente", "id": c.id,
                    "titulo": c.nome or c.razao_social or "—",
                    "subtitulo": c.cpf or c.cnpj or "", "link": "/clientes"})

    # ── Casos (escopo) ──
    qc = select(Case).where(
        Case.deleted_at.is_(None),
        or_(Case.titulo.ilike(termo), Case.numero_interno.ilike(termo),
            Case.numero_processo.ilike(termo)),
    )
    if not _ve_todos(cu):
        qc = qc.where(or_(Case.advogado_responsavel_id == cu.id,
                          Case.advogado_auxiliar_id == cu.id))
    casos = (await db.execute(qc.limit(limit))).scalars().all()
    for c in casos:
        out.append({"tipo": "caso", "id": c.id, "titulo": c.titulo,
                    "subtitulo": c.numero_interno or c.numero_processo or "",
                    "link": f"/casos/{c.id}"})

    # ── Peças (escopo via caso) ──
    qp = select(LegalDoc).where(
        LegalDoc.deleted_at.is_(None), LegalDoc.titulo.ilike(termo),
    )
    if not _ve_todos(cu):
        sub = select(Case.id).where(or_(
            Case.advogado_responsavel_id == cu.id,
            Case.advogado_auxiliar_id == cu.id))
        qp = qp.where(LegalDoc.case_id.in_(sub))
    pecas = (await db.execute(qp.limit(limit))).scalars().all()
    for p in pecas:
        out.append({"tipo": "peca", "id": p.id, "titulo": p.titulo,
                    "subtitulo": str(p.status.value), "link": "/pecas"})

    return {"q": q, "total": len(out), "resultados": out}
