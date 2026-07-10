from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class GoogleDriveSyncRequest(BaseModel):
    folder_id: str | None = Field(
        None,
        description="ID da pasta Google Drive. Se vazio, usa a configuração institucional.",
    )
    limit: int | None = Field(None, ge=1, le=500)
    categoria: str | None = Field(
        None,
        description=(
            "Categoria RAG manual. Para forçar uma categoria única, informe este "
            "campo e use categorizar_automaticamente=false."
        ),
    )
    confianca: str = Field("media", pattern="^(alta|media|baixa|bloqueado)$")
    categorizar_automaticamente: bool = Field(
        True,
        description="Quando true, classifica por sinais documentais e evita categoria única indevida.",
    )


class GoogleDriveCuradoriaPreviewRequest(BaseModel):
    limit: int | None = Field(500, ge=1, le=5000)
    only_changes: bool = True


class GoogleDriveCuradoriaApplyRequest(BaseModel):
    limit: int | None = Field(500, ge=1, le=5000)
    only_changes: bool = True
    confirmacao: Literal["RECLASSIFICAR_RAG_DRIVE"] = Field(
        ...,
        description=(
            "Confirmação operacional obrigatória. Deve ser exatamente "
            "RECLASSIFICAR_RAG_DRIVE."
        ),
    )
