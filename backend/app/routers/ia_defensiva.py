# app/routers/ia_defensiva.py
from __future__ import annotations

from typing import Any, Literal
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func as sqlfunc, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL
from app.models.user import User
from app.models.ai_log import AILog, AIStatusHITL
from app.services.ia_defensiva_service import IaDefensivaInput, executar_ia_defensiva

router = APIRouter(prefix="/ia-defensiva", tags=["IA Defensiva"])

Nivel = Literal["padrao", "alto", "maximo"]

Etapa = Literal[
    "analise_inicial",
    "fragilidades",
    "teses_defensivas",
    "provas_comparativas",
    "esqueleto_contestacao",
    "redigir_contestacao",
    "jec_triagem_minuta",
    "fluxo_completo",
]


class IaDefensivaRequest(BaseModel):
    etapa: Etapa = Field("fluxo_completo", description="Etapa analitica ou fluxo completo")
    peticao_inicial: str = Field(..., min_length=50, max_length=120000)
    rito: str | None = Field(None, description="comum, sumario, JEC, CLT, penal etc.")
    area: str | None = Field(None, description="civil, trabalhista, consumidor, familia etc.")
    documentos_autor: list[str] = Field(default_factory=list)
    documentos_defesa: list[str] = Field(default_factory=list)
    analises_anteriores: str | None = None
    dados_formais: dict[str, Any] = Field(default_factory=dict)
    case_id: str | None = None
    momento: str | None = Field(None, description="novo_caso, andamento, revisao, manual")
    nivel_inteligencia: Nivel = Field("alto", description="padrao, alto ou maximo")


@router.get("/status")
async def status_ia_defensiva(cu: User = Depends(get_current_user)):
    return {
        "modulo": "ia_defensiva",
        "status": "ativo",
        "etapas": [
            "analise_inicial",
            "fragilidades",
            "teses_defensivas",
            "provas_comparativas",
            "esqueleto_contestacao",
            "redigir_contestacao",
            "jec_triagem_minuta",
            "fluxo_completo",
        ],
        "uso": "novo caso, decorrer do caso, contestacao ou triagem JEC",
        "niveis_inteligencia": ["padrao", "alto", "maximo"],
        "aviso": "Rascunho interno. Revisao humana obrigatoria antes de protocolo ou envio ao cliente.",
    }


class IaDefensivaStatusRequest(BaseModel):
    status: Literal["revisado", "aplicado", "descartado"]


def _role_value(user: User) -> str:
    return getattr(user.role, "value", user.role)


def _is_ia_defensiva_log(log: AILog) -> bool:
    resposta = log.resposta or ""
    marcadores = (
        "# analise_inicial",
        "# fragilidades",
        "# teses_defensivas",
        "# provas_comparativas",
        "# esqueleto_contestacao",
        "# redigir_contestacao",
        "# jec_triagem_minuta",
    )
    return any(m in resposta for m in marcadores)


@router.get("/historico/{case_id}")
async def historico_ia_defensiva(
    case_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Historico HITL da IA Defensiva vinculado ao caso."""
    filtros_ia_defensiva = or_(
        AILog.resposta.ilike("%# analise_inicial%"),
        AILog.resposta.ilike("%# fragilidades%"),
        AILog.resposta.ilike("%# teses_defensivas%"),
        AILog.resposta.ilike("%# provas_comparativas%"),
        AILog.resposta.ilike("%# esqueleto_contestacao%"),
        AILog.resposta.ilike("%# redigir_contestacao%"),
        AILog.resposta.ilike("%# jec_triagem_minuta%"),
    )
    q = select(AILog).where(AILog.case_id == case_id, filtros_ia_defensiva)
    if ROLE_LEVEL.get(_role_value(cu), 0) < ROLE_LEVEL["socio"]:
        q = q.where(AILog.user_id == cu.id)
    q = q.order_by(AILog.created_at.desc())

    total = (await db.execute(select(sqlfunc.count()).select_from(q.subquery()))).scalar() or 0
    rows = (await db.execute(q.offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {
        "data": [
            {
                "id": l.id,
                "case_id": l.case_id,
                "modelo": l.modelo,
                "status_hitl": l.status_hitl.value,
                "pii_removida": l.pii_removida,
                "tokens_input": l.tokens_input,
                "tokens_output": l.tokens_output,
                "created_at": l.created_at,
                "revisado_por": l.revisado_por,
                "revisado_em": l.revisado_em,
                "resposta": l.resposta,
            }
            for l in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.patch("/historico/{log_id}/status")
async def atualizar_status_ia_defensiva(
    log_id: str,
    req: IaDefensivaStatusRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    log = (await db.execute(select(AILog).where(AILog.id == log_id))).scalar_one_or_none()
    if not log or not _is_ia_defensiva_log(log):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Historico de IA Defensiva nao encontrado")
    if log.user_id != cu.id and ROLE_LEVEL.get(_role_value(cu), 0) < ROLE_LEVEL["socio"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sem permissao para revisar este resultado")

    log.status_hitl = AIStatusHITL(req.status)
    log.revisado_por = cu.id
    log.revisado_em = datetime.now(timezone.utc)
    await db.commit()
    return {"detail": f"Status HITL atualizado para {req.status}", "status_hitl": req.status}


@router.post("/analisar")
async def analisar_ia_defensiva(
    req: IaDefensivaRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    try:
        payload = IaDefensivaInput(
            etapa=req.etapa,
            peticao_inicial=req.peticao_inicial,
            rito=req.rito,
            area=req.area,
            documentos_autor=req.documentos_autor,
            documentos_defesa=req.documentos_defesa,
            analises_anteriores=req.analises_anteriores,
            dados_formais=req.dados_formais,
            case_id=req.case_id,
            momento=req.momento,
            nivel_inteligencia=req.nivel_inteligencia,
        )
        return await executar_ia_defensiva(payload, db=db, user_id=cu.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
