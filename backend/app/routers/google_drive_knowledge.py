# ── app/routers/google_drive_knowledge.py ────────────────────────────────────
# Endpoints Google Drive → RAG.
#
# Este módulo é carregado por app/routers/__init__.py e registra suas rotas como
# sub-rotas do router RAG existente. Assim, não precisamos alterar main.py:
# rotas finais: /api/rag/google-drive/*
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models.user import User
from app.routers.rag import router as rag_router
from app.services import google_drive_service as gdrive

router = APIRouter(prefix="/google-drive", tags=["Base de Conhecimento / Google Drive"])


class GoogleDriveSyncRequest(BaseModel):
    folder_id: Optional[str] = Field(
        None,
        description="ID da pasta Google Drive. Se vazio, usa GOOGLE_DRIVE_KNOWLEDGE_FOLDER_ID.",
    )
    limit: Optional[int] = Field(None, ge=1, le=500)
    categoria: Optional[str] = Field(
        None,
        description="Categoria RAG. Se vazio, usa GOOGLE_DRIVE_DEFAULT_CATEGORIA ou 'doutrina'.",
    )
    confianca: str = Field("media", pattern="^(alta|media|baixa|bloqueado)$")


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
        "max_file_mb": gdrive.max_file_bytes() // (1024 * 1024),
        "allowed_mime_types": sorted(gdrive.allowed_mime_types()),
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
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Falha ao reindexar arquivo Google Drive: {type(exc).__name__}: {str(exc)[:300]}",
        ) from exc


# Registro efetivo: main.py já inclui rag_router com prefixo /api.
# Resultado: /api/rag/google-drive/status, /api/rag/google-drive/files, etc.
rag_router.include_router(router)
