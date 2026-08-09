# ── app/routers/trash.py ─────────────────────────────────────────────────────
# Lixeira: lista e restaura registros soft-deleted. Admin/sócio apenas.
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_roles
from app.models.audit_log import criar_audit_log
from app.models.case import Case
from app.models.client import Client
from app.models.deadline import Deadline
from app.models.document import Document
from app.models.environmental import EnvironmentalCase
from app.models.fee import Fee
from app.models.legal_doc import LegalDoc
from app.models.procuracao import Procuracao
from app.models.task import Task
from app.models.user import User

ENTIDADES = {
    "clients": (Client, lambda x: x.nome or x.razao_social),
    "cases": (Case, lambda x: f"{x.numero_interno} {x.titulo}"),
    "deadlines": (Deadline, lambda x: x.titulo),
    "documents": (Document, lambda x: x.titulo),
    "legal_docs": (LegalDoc, lambda x: x.titulo),
    "fees": (Fee, lambda x: x.descricao),
    "procuracoes": (Procuracao, lambda x: f"Procuração {x.id[:8]}"),
    "environmental_cases": (EnvironmentalCase, lambda x: f"Auto {x.numero_auto}"),
    "tasks": (Task, lambda x: x.titulo),
}

router = APIRouter(prefix="/trash", tags=["Lixeira"])


async def _exigir_pai_ativo(
    db: AsyncSession, modelo, registro_id: str, rotulo: str
) -> None:
    pai = await db.scalar(select(modelo).where(modelo.id == registro_id))
    if pai is None:
        raise HTTPException(
            status_code=409,
            detail=f"Não é possível restaurar: {rotulo} vinculado não existe mais.",
        )
    if getattr(pai, "deleted_at", None) is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Não é possível restaurar enquanto {rotulo} vinculado estiver "
                "na lixeira. Restaure a dependência primeiro."
            ),
        )


async def _validar_dependencias_restauração(
    db: AsyncSession, entidade: str, registro
) -> None:
    """Evita reativar filho cujo caso/cliente continua soft-deleted.

    Não tenta restaurar dependências automaticamente: a ordem precisa ser uma
    decisão explícita do operador e cada restauração mantém seu próprio audit log.
    """
    if entidade == "clients":
        return

    if entidade == "cases":
        client_id = getattr(registro, "client_id", None)
        if client_id:
            await _exigir_pai_ativo(db, Client, client_id, "o cliente")
        return

    case_id = getattr(registro, "case_id", None)
    if case_id:
        await _exigir_pai_ativo(db, Case, case_id, "o caso")

    client_id = getattr(registro, "client_id", None)
    if client_id:
        await _exigir_pai_ativo(db, Client, client_id, "o cliente")


@router.get("/")
async def listar(
    entidade: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio"])),
):
    if entidade not in ENTIDADES:
        raise HTTPException(
            status_code=422, detail=f"Entidade inválida. Use: {list(ENTIDADES)}"
        )
    modelo, rotulo = ENTIDADES[entidade]
    total = int(
        await db.scalar(
            select(func.count())
            .select_from(modelo)
            .where(modelo.deleted_at.isnot(None))
        )
        or 0
    )
    rows = (
        await db.execute(
            select(modelo)
            .where(modelo.deleted_at.isnot(None))
            .order_by(modelo.deleted_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return {
        "data": [
            {"id": r.id, "rotulo": rotulo(r), "excluido_em": r.deleted_at}
            for r in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/{entidade}/{registro_id}/restaurar")
async def restaurar(
    entidade: str,
    registro_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio"])),
):
    if entidade not in ENTIDADES:
        raise HTTPException(status_code=422, detail="Entidade inválida")
    modelo, _ = ENTIDADES[entidade]
    registro = (
        await db.execute(
            select(modelo).where(
                modelo.id == registro_id, modelo.deleted_at.isnot(None)
            )
        )
    ).scalar_one_or_none()
    if not registro:
        raise HTTPException(status_code=404, detail="Registro não está na lixeira")

    await _validar_dependencias_restauração(db, entidade, registro)
    excluido_em = registro.deleted_at
    registro.deleted_at = None
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "RESTORE",
        entidade,
        registro_id,
        dados_antes={"deleted_at": excluido_em.isoformat() if excluido_em else None},
        dados_depois={"deleted_at": None},
    )
    await db.commit()
    return {"detail": "Registro restaurado"}
