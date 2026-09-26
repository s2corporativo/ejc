# ── app/routers/trash.py ─────────────────────────────────────────────────────
# Lixeira: lista, restaura e (V2-4.4, LGPD art. 16/18 VI) purga definitivamente
# registros soft-deleted. Admin/sócio para listar/restaurar; purgar (irreversível)
# é superadmin apenas.
from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_roles
from app.models.audit_log import criar_audit_log
from app.models.case import Case
from app.models.client import Client
from app.models.deadline import Deadline
from app.models.document import Document
from app.models.fee import Fee
from app.models.legal_doc import LegalDoc
from app.models.rag import KnowledgeDoc
from app.models.procuracao import Procuracao
from app.models.task import Task
from app.models.user import User
from app.modules.legacy_verticals.trash_entities import LEGACY_TRASH_ENTITIES

ENTIDADES = {
    "clients": (Client, lambda x: x.nome or x.razao_social),
    "cases": (Case, lambda x: f"{x.numero_interno} {x.titulo}"),
    "deadlines": (Deadline, lambda x: x.titulo),
    "documents": (Document, lambda x: x.titulo),
    "legal_docs": (LegalDoc, lambda x: x.titulo),
    "fees": (Fee, lambda x: x.descricao),
    "procuracoes": (Procuracao, lambda x: f"Procuração {x.id[:8]}"),
    **LEGACY_TRASH_ENTITIES,
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


def _validar_purga_irreversivel_disponivel(entidade: str) -> None:
    """Bloqueia purga documental até existir política de retenção verificável.

    `Document` ainda não possui no schema canônico campos que permitam ao
    backend provar, no instante da purga, que o período de retenção terminou e
    que não existe legal hold ativo. Autorizar hard delete somente com papel de
    superadmin + motivo seria irreversível sem uma barreira jurídica objetiva.

    O bloqueio é deliberadamente restrito a `documents`: as demais entidades
    mantêm o fluxo existente. A futura implementação de #1359 deve substituir
    esta contenção por validação server-side de retenção/legal hold, com trilha
    de auditoria e migration própria após reconciliação do head Alembic.
    """
    if entidade == "documents":
        raise HTTPException(
            status_code=409,
            detail=(
                "Purga definitiva de documentos temporariamente bloqueada: "
                "a política de retenção e legal hold ainda não está codificada "
                "no schema canônico. Use a lixeira/soft delete até a validação "
                "server-side de retenção estar disponível."
            ),
        )


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

    rag_docs_restaurados = 0
    if entidade == "legal_docs":
        # O soft-delete da peça aposenta somente a versão RAG vigente. A
        # restauração reativa a versão mais recente aposentada pela própria
        # peça, sem promover versões históricas antigas a vigente.
        rag_doc = (
            await db.execute(
                select(KnowledgeDoc)
                .where(
                    KnowledgeDoc.chave_origem == f"legaldoc:{registro_id}",
                    KnowledgeDoc.deleted_at.isnot(None),
                )
                .order_by(KnowledgeDoc.versao.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if rag_doc is not None:
            rag_doc.deleted_at = None
            rag_doc.vigente = True
            rag_docs_restaurados = 1

    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "RESTORE",
        entidade,
        registro_id,
        dados_antes={"deleted_at": excluido_em.isoformat() if excluido_em else None},
        dados_depois={
            "deleted_at": None,
            "rag_docs_restaurados": rag_docs_restaurados,
        },
    )
    await db.commit()
    return {"detail": "Registro restaurado"}


class PurgarRequest(BaseModel):
    motivo: str = Field(
        ...,
        min_length=5,
        max_length=500,
        description="Motivo da purga (LGPD art. 18, VI) — obrigatório.",
    )


@router.post("/{entidade}/{registro_id}/purgar")
async def purgar(
    entidade: str,
    registro_id: str,
    payload: PurgarRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin"])),
):
    """Exclusão DEFINITIVA (hard delete) — LGPD art. 16 e art. 18, VI.

    Salvaguardas:
    - somente superadmin;
    - somente registro previamente soft-deleted;
    - motivo obrigatório;
    - audit log antes do delete físico;
    - sem cascade automático de exclusão irreversível;
    - documentos permanecem bloqueados para hard purge até o backend conseguir
      verificar retenção e legal hold de forma objetiva (issue #1359).
    """
    if entidade not in ENTIDADES:
        raise HTTPException(status_code=422, detail="Entidade inválida")
    modelo, rotulo = ENTIDADES[entidade]
    # `with_for_update()`: sem lock, um `restaurar` concorrente (admin/socio,
    # nível de permissão mais baixo) entre este SELECT e o commit abaixo podia
    # apagar fisicamente um registro que acabara de ser restaurado.
    registro = (
        await db.execute(
            select(modelo).where(
                modelo.id == registro_id, modelo.deleted_at.isnot(None)
            ).with_for_update()
        )
    ).scalar_one_or_none()
    if not registro:
        raise HTTPException(
            status_code=404,
            detail=(
                "Registro não está na lixeira — purga exige exclusão "
                "(soft delete) prévia."
            ),
        )

    _validar_purga_irreversivel_disponivel(entidade)

    excluido_em = registro.deleted_at
    rotulo_registro = rotulo(registro)
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "PURGE",
        entidade,
        registro_id,
        detalhes=payload.motivo,
        dados_antes={
            "rotulo": rotulo_registro,
            "excluido_em": excluido_em.isoformat() if excluido_em else None,
        },
        dados_depois={"purgado": True},
    )
    await db.delete(registro)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                "Não é possível purgar: há registros dependentes vinculados a "
                f"este {entidade[:-1] if entidade.endswith('s') else entidade}. "
                "Purgue as dependências primeiro."
            ),
        )
    return {"detail": "Registro purgado definitivamente"}
