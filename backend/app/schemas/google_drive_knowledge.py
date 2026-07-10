from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class GoogleDriveSyncRequest(BaseModel):
    folder_id: Optional[str] = Field(
        None,
        description="ID da pasta Google Drive. Se vazio, usa GOOGLE_DRIVE_KNOWLEDGE_FOLDER_ID.",
    )
    limit: Optional[int] = Field(None, ge=1, le=500)
    categoria: Optional[str] = Field(
        None,
        description=(
            "Categoria RAG manual. Se vazio/auto, o sistema classifica por nome, "
            "caminho e MIME. Para forçar uma categoria única, envie este campo "
            "e categorizar_automaticamente=false."
        ),
    )
    confianca: str = Field("media", pattern="^(alta|media|baixa|bloqueado)$")
    categorizar_automaticamente: bool = Field(
        True,
        description="Quando true, evita sincronizar todo o Drive como doutrina.",
    )


class GoogleDriveCuradoriaPreviewRequest(BaseModel):
    limit: Optional[int] = Field(500, ge=1, le=5000)
    only_changes: bool = True


class GoogleDriveCuradoriaApplyRequest(BaseModel):
    limit: Optional[int] = Field(500, ge=1, le=5000)
    only_changes: bool = True
    confirmacao: Literal["RECLASSIFICAR_RAG_DRIVE"] = Field(
        ...,
        description=(
            "Confirmação operacional obrigatória. Deve ser exatamente "
            "RECLASSIFICAR_RAG_DRIVE."
        ),
    )
