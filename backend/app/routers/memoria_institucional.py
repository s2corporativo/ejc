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
from app.core.security import get_current_user, requer_equipe_juridica
from app.core.ownership import is_gestao, verificar_acesso_caso
from app.core.sql_safe import construir_update
from app.models.user import User
from app.models.audit_log import criar_audit_log


def _req_staff(cu: User = Depends(get_current_user)) -> User:
    # Conhecimento interno do escritório: só EQUIPE_JURIDICA. Issue #694:
    # allowlist EXATA — financeiro nunca passa aqui, mesmo com ROLE_LEVEL
    # acima de estagiario (cliente_externo/secretaria já ficavam de fora).
    requer_equipe_juridica(cu, "Acesso restrito à equipe do escritório")
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


async def _obter_memoria_autorizada(
    db: AsyncSession,
    cu: User,
    mem_id: str,
) -> dict:
    """Carrega um registro ativo e aplica o ownership do caso vinculado.

    O router já restringe a equipe jurídica por papel. Esta segunda barreira
    impede que um usuário obtenha/edite/remova uma memória de caso que não
    poderia consultar diretamente. Registros institucionais sem ``case_id``
    continuam disponíveis à equipe jurídica, preservando o uso transversal do
    acervo do escritório.
    """
    result = await db.execute(
        text("""
            SELECT id, case_id, advogado_id, tipo, titulo, conteudo, resultado,
                   area_direito, tags, metadados, created_by, created_at, updated_at
            FROM memoria_institucional
            WHERE id = :id AND deleted_at IS NULL
        """),
        {"id": mem_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(404, "Registro não encontrado")
    memoria = dict(row)
    if memoria.get("case_id"):
        await verificar_acesso_caso(db, cu, memoria["case_id"])
    return memoria


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
    params: dict = {
        "limit": limit,
        "tipo": tipo,
        "area": f"%{area}%" if area else None,
        "q": f"%{q}%" if q else None,
    }
    if case_id:
        await verificar_acesso_caso(db, cu, case_id)  # ownership do caso filtrado
        params["case_id"] = case_id
        consulta = text("""
            SELECT id, case_id, advogado_id, tipo, titulo, conteudo, resultado,
                   area_direito, tags, metadados, created_by, created_at, updated_at
            FROM memoria_institucional
            WHERE deleted_at IS NULL
              AND case_id = :case_id
              AND (CAST(:tipo AS text) IS NULL OR tipo = :tipo)
              AND (CAST(:area AS text) IS NULL OR area_direito ILIKE :area)
              AND (CAST(:q AS text) IS NULL OR titulo ILIKE :q OR conteudo ILIKE :q)
            ORDER BY created_at DESC
            LIMIT :limit
        """)
    elif is_gestao(cu):
        consulta = text("""
            SELECT id, case_id, advogado_id, tipo, titulo, conteudo, resultado,
                   area_direito, tags, metadados, created_by, created_at, updated_at
            FROM memoria_institucional
            WHERE deleted_at IS NULL
              AND (CAST(:tipo AS text) IS NULL OR tipo = :tipo)
              AND (CAST(:area AS text) IS NULL OR area_direito ILIKE :area)
              AND (CAST(:q AS text) IS NULL OR titulo ILIKE :q OR conteudo ILIKE :q)
            ORDER BY created_at DESC
            LIMIT :limit
        """)
    else:
        # A listagem global também respeita ownership antes da paginação.
        params["cu_id"] = cu.id
        consulta = text("""
            SELECT id, case_id, advogado_id, tipo, titulo, conteudo, resultado,
                   area_direito, tags, metadados, created_by, created_at, updated_at
            FROM memoria_institucional
            WHERE deleted_at IS NULL
              AND (
                case_id IS NULL OR case_id IN (
                    SELECT id FROM cases
                    WHERE deleted_at IS NULL
                      AND (
                        advogado_responsavel_id = :cu_id
                        OR advogado_auxiliar_id = :cu_id
                      )
                )
              )
              AND (CAST(:tipo AS text) IS NULL OR tipo = :tipo)
              AND (CAST(:area AS text) IS NULL OR area_direito ILIKE :area)
              AND (CAST(:q AS text) IS NULL OR titulo ILIKE :q OR conteudo ILIKE :q)
            ORDER BY created_at DESC
            LIMIT :limit
        """)
    result = await db.execute(consulta, params)
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
    return await _obter_memoria_autorizada(db, cu, mem_id)


@router.patch("/{mem_id}")
async def atualizar(
    mem_id: str,
    body: MemoriaUpdate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    # A validação de ownership acontece ANTES de qualquer mutação.
    await _obter_memoria_autorizada(db, cu, mem_id)
    if body.tipo is not None and body.tipo not in TIPOS:
        raise HTTPException(422, f"tipo inválido; use um de {sorted(TIPOS)}")
    if body.resultado is not None and body.resultado not in RESULTADOS:
        raise HTTPException(422, f"resultado inválido; use um de {sorted(RESULTADOS)}")

    campos = {
        field: getattr(body, field)
        for field in ("tipo", "titulo", "conteudo", "resultado", "area_direito")
        if getattr(body, field) is not None
    }
    if not campos and body.tags is None:
        raise HTTPException(422, "Nada para atualizar")

    afetadas = 0
    if campos:
        stmt, params = construir_update(
            campos,
            tabela="memoria_institucional",
            exigir_nao_excluido=True,
        )
        params["where_id"] = mem_id
        result = await db.execute(stmt, params)
        afetadas = max(afetadas, result.rowcount or 0)

    if body.tags is not None:
        # tags requer CAST jsonb, mas o SQL é totalmente estático.
        result = await db.execute(
            text(
                "UPDATE memoria_institucional "
                "SET tags=CAST(:tags AS jsonb), updated_at=NOW() "
                "WHERE id=:id AND deleted_at IS NULL"
            ),
            {"id": mem_id, "tags": json.dumps(body.tags)},
        )
        afetadas = max(afetadas, result.rowcount or 0)

    if afetadas == 0:
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
    # Mesmo ownership de GET/PATCH: memória vinculada acompanha o caso.
    await _obter_memoria_autorizada(db, cu, mem_id)
    res = await db.execute(
        text("UPDATE memoria_institucional SET deleted_at = now() "
             "WHERE id = :id AND deleted_at IS NULL"),
        {"id": mem_id},
    )
    if res.rowcount == 0:
        raise HTTPException(404, "Registro não encontrado")
    await criar_audit_log(db, cu.id, cu.role.value, "DELETE", "memoria_institucional", mem_id)
    await db.commit()
