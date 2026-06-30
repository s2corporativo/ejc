"""Conversão para judicial — POST /cases/{case_id}/converter-judicial

MIGRADO (E2): cria um PROCESSO no PRÓPRIO caso (entidade `processes`, 1 Caso : N),
em vez de clonar o caso num segundo registro. Marca o caso como judicial e mantém
todos os satélites (deadlines, documents, fees, movimentos) no mesmo case_id —
elimina a duplicação Caso×Processo. linked_judicial_case_id deixa de ser usado
(preservado só p/ casos legados já vinculados). Agora com RBAC (lacuna do audit).

#CHK: ao judicializar, dispara em background a geração do checklist por legislação
(gatilho=pre_processo) — rascunho HITL, fail-safe (não bloqueia nem quebra a conversão).
"""
import logging
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.core.security import require_roles
from app.models.user import User
from app.models.audit_log import criar_audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cases/{case_id}/converter-judicial", tags=["Conversão de Caso"])

_ESCRITA = ["superadmin", "admin", "socio", "advogado", "advogado_auxiliar"]


async def _bg_gerar_checklist(case_id: str, user_id: str):
    """Background: gera checklist por legislação (rascunho) ao judicializar. Fail-safe."""
    from app.core.database import AsyncSessionLocal
    from app.services.checklist_ia import gerar_checklist_ia
    try:
        async with AsyncSessionLocal() as bgdb:
            await gerar_checklist_ia(bgdb, case_id, "pre_processo", user_id)
    except Exception as e:
        logger.warning(f"[conversao] checklist IA automático falhou p/ caso {case_id}: {e}")


@router.post("", status_code=201)
async def converter_judicial(
    case_id: str,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(_ESCRITA)),
):
    orig = (await db.execute(text("""
        SELECT id, titulo, numero_processo, tribunal, comarca, vara, valor_causa,
               case_type, has_judicial_process
        FROM cases WHERE id = :cid AND deleted_at IS NULL
    """), {"cid": case_id})).mappings().first()
    if not orig:
        raise HTTPException(404, "Caso não encontrado")

    # Evita duplicar: se já há processo judicial neste caso, recusa.
    ja = (await db.execute(text("""
        SELECT 1 FROM processes
        WHERE case_id = :cid AND tipo = 'judicial' AND deleted_at IS NULL LIMIT 1
    """), {"cid": case_id})).first()
    if ja:
        raise HTTPException(409, "Este caso já possui um processo judicial")

    # Cria o PROCESSO no próprio caso (1 Caso : N Processos) — sem clonar o caso.
    pid = str(uuid4())
    await db.execute(text("""
        INSERT INTO processes
            (id, case_id, numero_cnj, tribunal, comarca, vara, tipo, valor_causa, status, created_at, updated_at)
        VALUES
            (:id, :cid, NULLIF(:cnj, ''), :trib, :com, :vara, 'judicial', :vc, 'ativo', now(), now())
    """), {
        "id": pid, "cid": case_id, "cnj": orig["numero_processo"],
        "trib": orig["tribunal"], "com": orig["comarca"], "vara": orig["vara"],
        "vc": orig["valor_causa"],
    })

    # Marca o caso como judicial (mantém continuidade e satélites no mesmo case_id).
    await db.execute(text("""
        UPDATE cases SET case_type = 'judicial', has_judicial_process = true, updated_at = now()
        WHERE id = :cid
    """), {"cid": case_id})

    await db.execute(text("""
        INSERT INTO case_movimentos (id, case_id, tipo, descricao, created_by, created_at)
        VALUES (:id, :cid, 'nota', :desc, :uid, now())
    """), {"id": str(uuid4()), "cid": case_id,
           "desc": "Caso judicializado — processo judicial criado no próprio caso.",
           "uid": cu.id})

    await criar_audit_log(db, cu.id, cu.role.value, "CONVERTER_JUDICIAL", "processes", pid)
    await db.commit()

    # #CHK: gera o checklist por legislação em background (não bloqueia a resposta).
    background.add_task(_bg_gerar_checklist, case_id, cu.id)

    return {"ok": True, "case_id": case_id, "process_id": pid, "checklist": "gerando"}
