"""Compatibilidade temporária do antigo Banco de Teses v4.

A URL `/teses-v4` permanece para consumidores históricos, mas toda nova leitura
e escrita usa a tabela canônica `teses`. `teses_juridicas_v4` permanece apenas
como origem do backfill da migration 114, sem receber novas gravações.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Column, DateTime, Float, String, Text, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base, get_db
from app.core.rate_limit import rate_limit
from app.core.security import ROLE_LEVEL, get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)


# Mantido no metadata até exclusão física posterior a telemetria e homologação.
class TeseJuridica(Base):
    __tablename__ = "teses_juridicas_v4"

    id = Column(String(36), primary_key=True)
    titulo = Column(String(255), nullable=False)
    descricao = Column(Text, nullable=False)
    fundamentacao = Column(Text, nullable=False)
    jurisprudencia = Column(Text, nullable=True)
    taxa_sucesso = Column(Float, default=0.0)
    area_juridica = Column(String(50), nullable=False)
    tribunal = Column(String(100), nullable=True)
    magistrado = Column(String(100), nullable=True)
    vencedora = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TeseCreate(BaseModel):
    titulo: str = Field(min_length=5, max_length=300)
    descricao: str = Field(min_length=10)
    fundamentacao: str
    jurisprudencia: Optional[str] = None
    area_juridica: str
    tribunal: Optional[str] = None
    magistrado: Optional[str] = None


class TeseResponse(TeseCreate):
    id: str
    taxa_sucesso: float
    vencedora: bool


router = APIRouter(
    prefix="/teses-v4",
    tags=["Banco de Teses — compatibilidade"],
    deprecated=True,
)


def _is_staff(user: User) -> bool:
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    return ROLE_LEVEL.get(role, 0) >= ROLE_LEVEL["estagiario"]


def _headers_deprecacao(response: Response) -> None:
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</api/teses>; rel="successor-version"'


def _compat(item: dict) -> dict:
    return {
        "id": item["id"],
        "titulo": item["titulo"],
        "descricao": item["descricao"],
        "fundamentacao": item.get("fundamentacao") or "",
        "jurisprudencia": item.get("jurisprudencia"),
        "area_juridica": item.get("area_juridica") or "",
        "tribunal": item.get("tribunal"),
        "magistrado": item.get("magistrado"),
        "taxa_sucesso": float(item.get("taxa_sucesso") or 0),
        "vencedora": int(item.get("vezes_venceu") or 0) > 0,
    }


@router.post(
    "/",
    response_model=TeseResponse,
    status_code=201,
    deprecated=True,
)
async def criar_tese(
    payload: TeseCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Cria a tese no domínio canônico, sem dupla escrita na tabela v4."""
    from app.routers.teses import TeseIn, criar_tese as criar_tese_canonica

    item = await criar_tese_canonica(
        TeseIn(
            titulo=payload.titulo,
            descricao=payload.descricao,
            fundamentacao=payload.fundamentacao,
            jurisprudencia=payload.jurisprudencia,
            area_juridica=payload.area_juridica,
            tribunal=payload.tribunal,
            magistrado=payload.magistrado,
            observacoes="Criada pela rota de compatibilidade /teses-v4.",
        ),
        db=db,
        cu=cu,
    )
    _headers_deprecacao(response)
    return _compat(item)


@router.get(
    "/",
    response_model=list[TeseResponse],
    deprecated=True,
)
async def listar_teses(
    response: Response,
    area: Optional[str] = None,
    vencedoras: bool = False,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_staff(cu):
        raise HTTPException(403, "Acesso restrito")

    from app.routers.teses import listar_teses as listar_teses_canonicas

    page = await listar_teses_canonicas(
        area=area,
        status="ativa",
        tipo=None,
        tribunal=None,
        busca=None,
        order_by="taxa_sucesso",
        page=1,
        per_page=100,
        db=db,
        cu=cu,
    )
    items = page["items"]
    if vencedoras:
        items = [item for item in items if int(item.get("vezes_venceu") or 0) > 0]
    _headers_deprecacao(response)
    return [_compat(item) for item in items]


@router.get(
    "/sugestao-ia",
    dependencies=[Depends(rate_limit("teses-sugestao-ia", 15))],
    deprecated=True,
)
async def sugerir_teses_ia(
    response: Response,
    contexto: str = Query(..., min_length=3, max_length=12000),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Mantém o contrato legado usando somente gateway e teses canônicos."""
    from app.models.ai_log import AITipoUso
    from app.routers.teses import listar_teses as listar_teses_canonicas
    from app.services import ai_gateway as gateway_central
    from app.services.ai_guard import registrar_ai_log, sanitizar_ou_abortar

    if not _is_staff(cu):
        raise HTTPException(403, "Acesso restrito")

    contexto_limpo, pii = sanitizar_ou_abortar(contexto)
    page = await listar_teses_canonicas(
        area=None,
        status="ativa",
        tipo=None,
        tribunal=None,
        busca=None,
        order_by="taxa_sucesso",
        page=1,
        per_page=5,
        db=db,
        cu=cu,
    )
    contexto_teses = "\n".join(
        f"- {item['titulo']}: {item['descricao']}" for item in page["items"]
    )
    prompt = (
        f"Com base no contexto do caso: {contexto_limpo}\n\n"
        f"E nestas teses do escritório:\n{contexto_teses}\n\n"
        "Sugira a melhor estratégia e novas teses. Não invente julgados ou artigos; "
        "não prometa resultado. Toda sugestão é rascunho sob revisão do advogado."
    )
    try:
        result = await gateway_central.chat(
            [{"role": "user", "content": prompt}],
            task_type="analise_juridica",
        )
    except Exception as exc:
        logger.exception("Falha na sugestão de teses pela rota de compatibilidade")
        raise HTTPException(502, "IA indisponível no momento") from exc

    log_id = await registrar_ai_log(
        db,
        user_id=cu.id,
        tipo_uso=AITipoUso.analise_caso,
        case_id=None,
        prompt_sanitizado=prompt,
        pii_removida=pii,
        resposta=result.texto,
        modelo=f"{result.provedor}/{result.modelo}",
        tokens_input=result.input_tokens,
        tokens_output=result.output_tokens,
    )
    _headers_deprecacao(response)
    return {
        "modelo_utilizado": f"{result.provedor}/{result.modelo}",
        "tipo_demanda": "juridico_profundo",
        "resposta": result.texto,
        "status": "sucesso",
        "log_id": log_id,
        "is_rascunho": True,
        "aviso_hitl": "Rascunho sujeito à revisão humana (HITL obrigatório — OAB).",
    }
