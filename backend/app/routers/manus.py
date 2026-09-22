from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, requer_equipe_juridica
from app.models.user import User
from app.services.manus_client import verify_manus_webhook
from app.services.manus_service import aplicar_webhook, iniciar_analise, obter_tarefa

router = APIRouter(prefix="/manus", tags=["IA — Manus"])


class ManusAnalysisRequest(BaseModel):
    case_id: str = Field(min_length=1, max_length=64)
    texto: str = Field(min_length=30, max_length=60_000)
    area: str | None = Field(default=None, max_length=80)
    profile: str = Field(default="standard", pattern="^(lite|standard|max)$")


class ManusTaskResponse(BaseModel):
    id: str
    manus_task_id: str
    status: str
    task_url: str | None = None
    result: dict | None = None
    review_required: bool = True


@router.post(
    "/analises",
    response_model=ManusTaskResponse,
    status_code=202,
    dependencies=[Depends(rate_limit("manus-analysis", 10))],
)
async def criar_analise(
    body: ManusAnalysisRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    requer_equipe_juridica(user, "Acesso restrito à equipe jurídica")
    registro = await iniciar_analise(
        db, user=user, case_id=body.case_id, texto=body.texto,
        area=body.area, profile=body.profile,
    )
    return ManusTaskResponse(
        id=registro.id,
        manus_task_id=registro.manus_task_id,
        status=registro.status,
        task_url=registro.task_url,
    )


@router.get("/analises/{task_id}", response_model=ManusTaskResponse)
async def consultar_analise(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    requer_equipe_juridica(user, "Acesso restrito à equipe jurídica")
    registro = await obter_tarefa(db, task_id=task_id, user=user)
    return ManusTaskResponse(
        id=registro.id,
        manus_task_id=registro.manus_task_id,
        status=registro.status,
        task_url=registro.task_url,
        result=registro.resultado_json,
    )


@router.post("/webhook", include_in_schema=False)
async def webhook_manus(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    x_webhook_signature: str | None = Header(default=None),
    x_webhook_timestamp: str | None = Header(default=None),
):
    settings = get_settings()
    if not settings.MANUS_API_ENABLED or not settings.MANUS_WEBHOOK_PUBLIC_KEY:
        raise HTTPException(status_code=404, detail="Webhook Manus não configurado")
    raw = await request.body()
    if not x_webhook_signature or not x_webhook_timestamp:
        raise HTTPException(status_code=401, detail="Assinatura ausente")
    if not verify_manus_webhook(
        public_key_pem=settings.MANUS_WEBHOOK_PUBLIC_KEY,
        url=str(request.url),
        body=raw,
        signature_b64=x_webhook_signature,
        timestamp=x_webhook_timestamp,
    ):
        raise HTTPException(status_code=401, detail="Assinatura inválida")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Payload inválido") from exc
    await aplicar_webhook(db, payload)
    return {"ok": True}
