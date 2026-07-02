"""Processos — entidade independente do Caso (1 Caso : N Processos).

Substitui o achatamento Caso=Processo (auto-FK linked_judicial_case_id, 1:1).
Aditivo/transicional: NAO altera cases nem conversao_caso. Permite que um caso
tenha N processos (principal + recurso + cautelar + execucao, tribunais distintos).
SQL cru (padrao do projeto). cliente_externo nao alcanca (bloqueado no AuthMiddleware).
"""
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.security import get_current_user, require_roles
from app.models.user import User
from app.models.audit_log import criar_audit_log

router = APIRouter(tags=["Processos"])

_ESCRITA = ["superadmin", "admin", "socio", "advogado", "advogado_auxiliar"]


class ProcessoIn(BaseModel):
    numero_cnj: Optional[str] = None
    instancia: Optional[str] = None
    tribunal: Optional[str] = None
    comarca: Optional[str] = None
    vara: Optional[str] = None
    classe: Optional[str] = None
    fase: Optional[str] = None
    tipo: str = "judicial"
    processo_principal_id: Optional[str] = None
    valor_causa: Optional[float] = None
    status: str = "ativo"


class ProcessoPatch(BaseModel):
    numero_cnj: Optional[str] = None
    instancia: Optional[str] = None
    tribunal: Optional[str] = None
    comarca: Optional[str] = None
    vara: Optional[str] = None
    classe: Optional[str] = None
    fase: Optional[str] = None
    tipo: Optional[str] = None
    valor_causa: Optional[float] = None
    status: Optional[str] = None


class ArchiveProcessRequest(BaseModel):
    motivo: Optional[str] = Field(default=None, max_length=1000)


async def _case_id_do_processo(db: AsyncSession, pid: str) -> str:
    row = (await db.execute(
        text("SELECT case_id FROM processes WHERE id = :pid AND deleted_at IS NULL"),
        {"pid": pid},
    )).first()
    if row is None:
        raise HTTPException(404, "Processo não encontrado")
    return row[0]


@router.get("/cases/{case_id}/processes")
async def listar_processos(
    case_id: str,
    arquivo: str = Query("ativos", pattern="^(ativos|arquivados|todos)$"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    await verificar_acesso_caso(db, cu, case_id)
    filtro_arquivo = ""
    if arquivo == "ativos":
        filtro_arquivo = "AND status <> 'arquivado'"
    elif arquivo == "arquivados":
        filtro_arquivo = "AND status = 'arquivado'"
    rows = (await db.execute(text("""
        SELECT id, case_id, numero_cnj, instancia, tribunal, comarca, vara, classe, fase, tipo,
               processo_principal_id, valor_causa, status, archived_at, archive_reason,
               created_at, updated_at
        FROM processes WHERE case_id = :c AND deleted_at IS NULL
        """ + filtro_arquivo + """
        ORDER BY (processo_principal_id IS NOT NULL), created_at
    """), {"c": case_id})).mappings().all()
    return {"data": [dict(r) for r in rows]}


@router.post("/cases/{case_id}/processes", status_code=201)
async def criar_processo(
    case_id: str,
    body: ProcessoIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(_ESCRITA)),
):
    await verificar_acesso_caso(db, cu, case_id)
    pid = str(uuid4())
    await db.execute(text("""
        INSERT INTO processes
            (id, case_id, numero_cnj, instancia, tribunal, comarca, vara, classe, fase,
             tipo, processo_principal_id, valor_causa, status, created_at, updated_at)
        VALUES
            (:id, :c, :cnj, :inst, :trib, :com, :vara, :classe, :fase,
             :tipo, :pp, :vc, :st, now(), now())
    """), {
        "id": pid, "c": case_id, "cnj": body.numero_cnj, "inst": body.instancia,
        "trib": body.tribunal, "com": body.comarca, "vara": body.vara, "classe": body.classe,
        "fase": body.fase, "tipo": body.tipo, "pp": body.processo_principal_id,
        "vc": body.valor_causa, "st": body.status,
    })
    await criar_audit_log(db, cu.id, cu.role.value, "CREATE", "processes", pid)
    await db.commit()
    return {"id": pid, "case_id": case_id}


@router.patch("/processes/{pid}")
async def atualizar_processo(
    pid: str,
    body: ProcessoPatch,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(_ESCRITA)),
):
    case_id = await _case_id_do_processo(db, pid)
    await verificar_acesso_caso(db, cu, case_id)
    res = await db.execute(text("""
        UPDATE processes SET
            numero_cnj = COALESCE(:cnj, numero_cnj),
            instancia  = COALESCE(:inst, instancia),
            tribunal   = COALESCE(:trib, tribunal),
            comarca    = COALESCE(:com, comarca),
            vara       = COALESCE(:vara, vara),
            classe     = COALESCE(:classe, classe),
            fase       = COALESCE(:fase, fase),
            tipo       = COALESCE(:tipo, tipo),
            valor_causa= COALESCE(:vc, valor_causa),
            status     = COALESCE(:st, status),
            archived_at = CASE
                WHEN :st = 'arquivado' AND archived_at IS NULL THEN now()
                WHEN :st IS NOT NULL AND :st <> 'arquivado' THEN NULL
                ELSE archived_at
            END,
            archive_reason = CASE
                WHEN :st IS NOT NULL AND :st <> 'arquivado' THEN NULL
                ELSE archive_reason
            END,
            updated_at = now()
        WHERE id = :pid AND deleted_at IS NULL
    """), {
        "cnj": body.numero_cnj, "inst": body.instancia, "trib": body.tribunal,
        "com": body.comarca, "vara": body.vara, "classe": body.classe, "fase": body.fase,
        "tipo": body.tipo, "vc": body.valor_causa, "st": body.status, "pid": pid,
    })
    if res.rowcount == 0:
        raise HTTPException(404, "Processo não encontrado")
    await criar_audit_log(db, cu.id, cu.role.value, "UPDATE", "processes", pid)
    await db.commit()
    return {"ok": True}


@router.post("/processes/{pid}/arquivar")
async def arquivar_processo(
    pid: str,
    body: Optional[ArchiveProcessRequest] = Body(default=None),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(_ESCRITA)),
):
    case_id = await _case_id_do_processo(db, pid)
    await verificar_acesso_caso(db, cu, case_id)
    motivo = ((body.motivo if body else None) or "").strip() or None
    res = await db.execute(text("""
        UPDATE processes
        SET status = 'arquivado',
            archived_at = COALESCE(archived_at, now()),
            archive_reason = :motivo,
            updated_at = now()
        WHERE id = :pid AND deleted_at IS NULL AND status <> 'arquivado'
    """), {"pid": pid, "motivo": motivo})
    if res.rowcount == 0:
        exists = (await db.execute(text(
            "SELECT 1 FROM processes WHERE id=:pid AND deleted_at IS NULL"
        ), {"pid": pid})).first()
        if not exists:
            raise HTTPException(404, "Processo não encontrado")
        raise HTTPException(409, "Processo já arquivado")
    await criar_audit_log(
        db, cu.id, cu.role.value, "ARCHIVE", "processes", pid,
        dados_depois={"status": "arquivado", "motivo": motivo or ""},
    )
    await db.commit()
    return {"ok": True, "status": "arquivado"}


@router.post("/processes/{pid}/desarquivar")
async def desarquivar_processo(
    pid: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(_ESCRITA)),
):
    case_id = await _case_id_do_processo(db, pid)
    await verificar_acesso_caso(db, cu, case_id)
    res = await db.execute(text("""
        UPDATE processes
        SET status = 'ativo',
            archived_at = NULL,
            archive_reason = NULL,
            updated_at = now()
        WHERE id = :pid AND deleted_at IS NULL AND status = 'arquivado'
    """), {"pid": pid})
    if res.rowcount == 0:
        exists = (await db.execute(text(
            "SELECT 1 FROM processes WHERE id=:pid AND deleted_at IS NULL"
        ), {"pid": pid})).first()
        if not exists:
            raise HTTPException(404, "Processo não encontrado")
        raise HTTPException(409, "Processo não está arquivado")
    await criar_audit_log(
        db, cu.id, cu.role.value, "UNARCHIVE", "processes", pid,
        dados_depois={"status": "ativo"},
    )
    await db.commit()
    return {"ok": True, "status": "ativo"}


@router.delete("/processes/{pid}")
async def remover_processo(
    pid: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(_ESCRITA)),
):
    case_id = await _case_id_do_processo(db, pid)
    await verificar_acesso_caso(db, cu, case_id)
    res = await db.execute(text(
        "UPDATE processes SET deleted_at = now() WHERE id = :pid AND deleted_at IS NULL"
    ), {"pid": pid})
    if res.rowcount == 0:
        raise HTTPException(404, "Processo não encontrado")
    await criar_audit_log(db, cu.id, cu.role.value, "DELETE", "processes", pid)
    await db.commit()
    return {"ok": True}
