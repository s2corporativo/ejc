# ── app/routers/document_url_import.py ────────────────────────────────────────
"""Importação de conteúdo jurídico por URL.

Endpoint de prévia: não grava documento físico no GED. Ele baixa a página pública
com validações anti-SSRF, extrai texto, monta dossiê jurídico e opcionalmente roda
análise estratégica como rascunho para um caso existente.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.security import get_current_user
from app.models.case import Case
from app.models.user import User
from app.services.document_url_import_service import importar_url_juridica

router = APIRouter(prefix="/documents/url", tags=["Documentos / Importação por URL"])


class ImportarUrlRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=2048)
    titulo: Optional[str] = Field(None, max_length=255)
    case_id: Optional[str] = Field(None, description="Caso existente para análise estratégica opcional")
    executar_analise: bool = Field(
        False,
        description="Quando true e case_id informado, roda análise estratégica como rascunho.",
    )


@router.post("/preview")
async def importar_url_preview(
    req: ImportarUrlRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Importa uma URL jurídica pública como prévia revisável.

    Fluxo seguro:
    - valida URL e rede antes de buscar;
    - extrai texto sem executar JS;
    - monta dossiê jurídico;
    - se solicitado, analisa o dossiê no contexto de um caso que o usuário acessa.
    """
    caso = None
    if req.case_id:
        await verificar_acesso_caso(db, cu, req.case_id)
        caso = (await db.execute(
            select(Case).where(Case.id == req.case_id, Case.deleted_at.is_(None))
        )).scalar_one_or_none()
        if not caso:
            raise HTTPException(status_code=404, detail="Caso não encontrado")

    resultado = await importar_url_juridica(req.url, titulo=req.titulo)
    out = resultado.model_dump() if hasattr(resultado, "model_dump") else resultado.dict()
    out["requer_revisao_humana"] = True
    out["pode_aplicar_ao_caso"] = bool(req.case_id and not resultado.bloqueado and resultado.dossie)

    if req.executar_analise:
        if not caso:
            raise HTTPException(status_code=422, detail="Informe case_id para executar análise")
        if resultado.bloqueado or not resultado.dossie:
            out["analise"] = None
            out["analise_aviso"] = "Análise não executada porque a URL não gerou texto importável."
            return out
        try:
            from app.services.analise_estrategica import analisar_caso
            analise = await analisar_caso(
                titulo=caso.titulo or req.titulo or resultado.titulo or "Importação por URL",
                area=caso.area or "",
                numero_processo=caso.numero_processo or "",
                texto_documento=resultado.dossie,
                scope_client_id=caso.client_id,
                db=db,
            )
            out["analise"] = analise
            out["analise_aviso"] = "Análise gerada como rascunho. Revise antes de usar no caso."
        except Exception as exc:
            out["analise"] = None
            out["analise_aviso"] = f"Falha ao executar análise estratégica: {str(exc)[:180]}"

    return out
