# ── app/routers/google_drive_knowledge.py ────────────────────────────────────
# Endpoints Google Drive → RAG.
#
# Este módulo é carregado por app/routers/__init__.py e registra suas rotas como
# sub-rotas do router RAG existente. Rotas finais: /api/rag/google-drive/*
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models.audit_log import criar_audit_log
from app.models.user import User
from app.routers.rag import router as rag_router
from app.schemas.google_drive_knowledge import (
    GoogleDriveCuradoriaApplyRequest,
    GoogleDriveCuradoriaPreviewRequest,
    GoogleDriveSyncRequest,
)
from app.services import google_drive_service as gdrive
from app.services.rag_drive_reclassifier import reclassificar_docs_drive

logger = logging.getLogger("ejc.rag.google_drive")

router = APIRouter(prefix="/google-drive", tags=["Base de Conhecimento / Google Drive"])


@router.get("/status")
async def status_google_drive(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Status da integração Google Drive → RAG."""
    folder_id = gdrive.knowledge_folder_id()
    state = await gdrive.get_sync_state(db, folder_id) if folder_id else None
    return {
        "enabled": gdrive.drive_enabled(),
        "folder_id_configurado": bool(folder_id),
        "folder_id": folder_id or None,
        "shared_drive_id_configurado": bool(gdrive.shared_drive_id()),
        "categoria_padrao": gdrive.default_categoria(),
        "auto_categorizar": gdrive.auto_categorizar_enabled(),
        "max_file_mb": gdrive.max_file_bytes() // (1024 * 1024),
        "allowed_mime_types": sorted(gdrive.allowed_mime_types()),
        "auth": gdrive.auth_status(),
        "sync_state": state,
    }


@router.get("/files")
async def listar_arquivos_google_drive(
    folder_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Lista arquivos da pasta configurada, sem ingerir no RAG."""
    try:
        files = await gdrive.listar_arquivos_pasta(folder_id=folder_id, limit=limit)
        return {"total": len(files), "data": files}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao consultar Google Drive: {type(exc).__name__}: {str(exc)[:200]}",
        ) from exc


@router.get("/audit")
async def auditar_google_drive(
    folder_id: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Audita e classifica a pasta de conhecimento sem alterar o banco."""
    try:
        return await gdrive.auditar_pasta_conhecimento(folder_id=folder_id, limit=limit)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao auditar Google Drive: {type(exc).__name__}: {str(exc)[:200]}",
        ) from exc


@router.post("/curadoria/preview")
async def preview_curadoria_google_drive(
    req: GoogleDriveCuradoriaPreviewRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio"])),
):
    """Pré-visualiza reclassificação de documentos ingeridos, sem persistência."""
    try:
        return await reclassificar_docs_drive(
            db,
            apply=False,
            limit=req.limit,
            only_changes=req.only_changes,
        )
    except Exception as exc:
        await db.rollback()
        logger.exception("Falha interna na prévia de curadoria do RAG Google Drive")
        raise HTTPException(
            status_code=500,
            detail="Falha interna ao gerar a prévia de curadoria do RAG.",
        ) from exc


@router.post("/curadoria/apply")
async def aplicar_curadoria_google_drive(
    req: GoogleDriveCuradoriaApplyRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio"])),
):
    """Aplica reclassificação revisada, sem excluir documentos fisicamente."""
    try:
        role = getattr(cu.role, "value", str(cu.role))
        await criar_audit_log(
            db,
            user_id=cu.id,
            user_role=role,
            acao="UPDATE",
            entidade="rag_drive_curadoria",
            detalhes=(
                "Aplicação confirmada de curadoria Google Drive/RAG; "
                f"limit={req.limit}; only_changes={req.only_changes}"
            ),
        )
        resultado = await reclassificar_docs_drive(
            db,
            apply=True,
            limit=req.limit,
            only_changes=req.only_changes,
        )
        logger.warning(
            "[RAG:Drive:Curadoria] aplicação concluída total_lidos=%s total_aplicados=%s",
            resultado.get("total_docs_drive_lidos"),
            resultado.get("total_aplicados"),
        )
        return resultado
    except Exception as exc:
        await db.rollback()
        logger.exception("Falha interna ao aplicar curadoria do RAG Google Drive")
        raise HTTPException(
            status_code=500,
            detail="Falha interna ao aplicar a curadoria do RAG.",
        ) from exc


@router.post("/sync")
async def sincronizar_google_drive(
    req: GoogleDriveSyncRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio"])),
):
    """Sincroniza a pasta Google Drive com a Base de Conhecimento RAG."""
    try:
        return await gdrive.sincronizar_pasta_conhecimento(
            db,
            folder_id=req.folder_id,
            limit=req.limit,
            categoria=req.categoria,
            confianca=req.confianca,
            categorizar_automaticamente=req.categorizar_automaticamente,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Falha na sincronização Google Drive → RAG: {type(exc).__name__}: {str(exc)[:300]}",
        ) from exc


@router.post("/reindex/{file_id}")
async def reindexar_arquivo_google_drive(
    file_id: str,
    categoria: Optional[str] = Query(None),
    confianca: str = Query("media", pattern="^(alta|media|baixa|bloqueado)$"),
    categorizar_automaticamente: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio"])),
):
    """Reindexa um único arquivo do Google Drive pelo file_id."""
    try:
        return await gdrive.reindexar_arquivo(
            db,
            file_id,
            categoria=categoria,
            confianca=confianca,
            categorizar_automaticamente=categorizar_automaticamente,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Falha ao reindexar arquivo Google Drive: {type(exc).__name__}: {str(exc)[:300]}",
        ) from exc


# main.py inclui rag_router com prefixo /api.
rag_router.include_router(router)
