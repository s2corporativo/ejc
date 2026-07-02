# app/routers/validador_juridico.py
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.ownership import verificar_acesso_caso
from app.models.user import User
from app.services.validador_juridico_service import ValidacaoInput, validar_rascunho_juridico

router = APIRouter(prefix="/validador-juridico", tags=["Validador Juridico"])

Nivel = Literal["padrao", "alto", "maximo"]


class ValidacaoJuridicaRequest(BaseModel):
    rascunho: str = Field(..., min_length=100, max_length=120000)
    tipo_documento: str = Field("peca_juridica", max_length=80)
    area: str | None = Field(None, max_length=80)
    rito: str | None = Field(None, max_length=80)
    fase: str | None = Field(None, max_length=80)
    documentos: list[str] = Field(default_factory=list)
    case_id: str | None = None
    nivel_inteligencia: Nivel = "alto"


@router.get("/status")
async def status_validador(cu: User = Depends(get_current_user)):
    return {
        "modulo": "validador_juridico",
        "status": "ativo",
        "verifica": [
            "fontes normativas",
            "jurisprudencia pendente",
            "provas e onus probatorio",
            "rito e pedidos",
            "coerencia interna",
            "score de confianca",
            "checklist de revisao humana",
        ],
        "aviso": "Controle interno. Nenhuma peca deve ser protocolada sem revisao humana.",
    }


@router.post("/validar")
async def validar(
    req: ValidacaoJuridicaRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    try:
        # Bloco 5 (continuação): case_id existia mas sem checagem de ownership.
        escopo_cli = None
        if req.case_id:
            await verificar_acesso_caso(db, cu, req.case_id)
            from app.services.ai_service import _escopo_cliente_do_caso
            escopo_cli = await _escopo_cliente_do_caso(db, req.case_id)
        payload = ValidacaoInput(
            rascunho=req.rascunho,
            tipo_documento=req.tipo_documento,
            area=req.area,
            rito=req.rito,
            fase=req.fase,
            documentos=req.documentos,
            case_id=req.case_id,
            nivel_inteligencia=req.nivel_inteligencia,
        )
        return await validar_rascunho_juridico(payload, db=db, user_id=cu.id, scope_client_id=escopo_cli)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
