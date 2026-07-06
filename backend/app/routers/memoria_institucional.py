# ── app/routers/memoria_institucional.py ─────────────────────────────────────
# Memória Institucional (FASE 8): registros estruturados do conhecimento do
# escritório — peças vencedoras, estratégias, pareceres, acordos. Filtrável por
# caso/tipo/área/resultado + busca textual. Auditado em audit_logs.
from __future__ import annotations
import json
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL
from app.core.ownership import verificar_acesso_caso
from app.models.user import User
from app.models.audit_log import criar_audit_log


def _req_staff(cu: User = Depends(get_current_user)) -> User:
    # Conhecimento interno do escritório: só equipe (estagiario+); nunca
    # cliente_externo/secretaria.
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["estagiario"]:
        raise HTTPException(403, "Acesso restrito à equipe do escritório")
    return cu


router = APIRouter(prefix="/memoria-institucional", tags=["Memória Institucional"],
                   dependencies=[Depends(_req_staff)])

TIPOS = {"peticao", "recurso", "parecer", "contrato", "decisao",
         "acordo", "tese_vencedora", "estrategia"}
RESULTADOS = {"favoravel", "desfavoravel", "parcial", "acordo", "em_andamento"}

_COLS = """id, case_id, advogado_id, tipo, titulo, conteudo, resultado,
           area_direito, tags, metadados, created_by, created_at, updated_at"""


class MemoriaCreate(BaseModel):
    tipo: str
    titulo: str
    conteudo: str
    resultado: Optional[str] = None
    area_direito: Optional[str] = None
    case_id: Optional[str] = None
    advogado_id: Optional[str] = None
    tags: List[str] = []
    metadados: dict = {}


class MemoriaUpdate(BaseModel):
    tipo: Optional[str] = None
    titulo: Optional[str] = None
    conteudo: Optional[str] = None
    resultado: Optional[str] = None
    area_direito: Optional[str] = None
    tags: Optional[List[str]] = None


@router.get("")
async def listar(
    case_id: Optional[str] = None,
    tipo: Optional[str] = None,
    area: Optional[str] = None,
    q: Optional[str] = Query(None, description="busca em título/conteúdo"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    cond = ["deleted_at IS NULL"]
    params: dict = {"limit": limit}
    if case_id:
        await verificar_acesso_caso(db, cu, case_id)  # ownership do caso filtrado
        cond.append("case_id = :case_id"); params["case_id"] = case_id
    if tipo:
        cond.append("tipo = :tipo"); params["tipo"] = tipo
    if area:
        cond.append("area_direito ILIKE :area"); params["area"] = f"%{area}%"
    if q:
        cond.append("(titulo ILIKE :q OR conteudo ILIKE :q)"); params["q"] = f"%{q}%"
    result = await db.execute(
        text(f"SELECT {_COLS} FROM memoria_institucional "
             f"WHERE {' AND '.join(cond)} ORDER BY created_at DESC LIMIT :limit"),
        params,
    )
    return [dict(r) for r in result.mappings().all()]


@router.post("", status_code=201)
async def criar(
    body: MemoriaCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if body.tipo not in TIPOS:
        raise HTTPException(422, f"tipo inválido; use um de {sorted(TIPOS)}")
    if body.resultado and body.resultado not in RESULTADOS:
        raise HTTPException(422, f"resultado inválido; use um de {sorted(RESULTADOS)}")
    if body.case_id:
        await verificar_acesso_caso(db, cu, body.case_id)  # ownership do caso vinculado
    result = await db.execute(
        text("""
            INSERT INTO memoria_institucional
                (case_id, advogado_id, tipo, titulo, conteudo, resultado,
                 area_direito, tags, metadados, created_by)
            VALUES
                (:case_id, :adv, :tipo, :titulo, :conteudo, :resultado,
                 :area, CAST(:tags AS jsonb), CAST(:metadados AS jsonb), :user)
            RETURNING id
        """),
        {
            "case_id": body.case_id, "adv": body.advogado_id or cu.id,
            "tipo": body.tipo, "titulo": body.titulo, "conteudo": body.conteudo,
            "resultado": body.resultado, "area": body.area_direito,
            "tags": json.dumps(body.tags), "metadados": json.dumps(body.metadados),
            "user": cu.id,
        },
    )
    row = result.mappings().first()
    await criar_audit_log(db, cu.id, cu.role.value, "CREATE", "memoria_institucional", row["id"])
    await db.commit()
    return {"id": row["id"], "message": "Registro de memória criado"}


@router.get("/{mem_id}")
async def obter(
    mem_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    result = await db.execute(
        text(f"SELECT {_COLS} FROM memoria_institucional "
             f"WHERE id = :id AND deleted_at IS NULL"),
        {"id": mem_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(404, "Registro não encontrado")
    return dict(row)


@router.patch("/{mem_id}")
async def atualizar(
    mem_id: str,
    body: MemoriaUpdate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    sets: list[str] = []
    params: dict = {"id": mem_id}
    for field in ("tipo", "titulo", "conteudo", "resultado", "area_direito"):
        val = getattr(body, field)
        if val is not None:
            sets.append(f"{field} = :{field}"); params[field] = val
    if body.tags is not None:
        sets.append("tags = CAST(:tags AS jsonb)"); params["tags"] = json.dumps(body.tags)
    if not sets:
        raise HTTPException(422, "Nada para atualizar")
    sets.append("updated_at = now()")
    result = await db.execute(
        text(f"UPDATE memoria_institucional SET {', '.join(sets)} "
             f"WHERE id = :id AND deleted_at IS NULL RETURNING id"),
        params,
    )
    if not result.mappings().first():
        raise HTTPException(404, "Registro não encontrado")
    await criar_audit_log(db, cu.id, cu.role.value, "UPDATE", "memoria_institucional", mem_id)
    await db.commit()
    return {"id": mem_id, "message": "Atualizado"}


@router.delete("/{mem_id}", status_code=204)
async def remover(
    mem_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    res = await db.execute(
        text("UPDATE memoria_institucional SET deleted_at = now() "
             "WHERE id = :id AND deleted_at IS NULL"),
        {"id": mem_id},
    )
    if res.rowcount == 0:
        raise HTTPException(404, "Registro não encontrado")
    await criar_audit_log(db, cu.id, cu.role.value, "DELETE", "memoria_institucional", mem_id)
    await db.commit()
