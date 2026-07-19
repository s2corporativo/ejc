"""Compatibilidade do antigo Banco de Teses v4.

A URL `/teses-v4` permanece temporariamente, mas toda nova leitura e escrita usa
`teses`. `teses_juridicas_v4` fica somente como origem histórica do backfill.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Column, DateTime, Float, String, Text, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base, get_db
from app.core.rate_limit import rate_limit
from app.core.security import ROLE_LEVEL, get_current_user, require_roles
from app.models.tese import Tese, TeseStatus, TeseTipo
from app.models.user import User

logger = logging.getLogger(__name__)


# Mantido no metadata até a etapa final de exclusão física da tabela legada.
# Nenhum endpoint abaixo cria, atualiza ou remove registros nesta classe.
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
    titulo: str = Field(min_length=1, max_length=255)
    descricao: str = Field(min_length=1)
    fundamentacao: str = Field(min_length=1)
    jurisprudencia: Optional[str] = None
    area_juridica: str = Field(min_length=1, max_length=50)
    tribunal: Optional[str] = Field(default=None, max_length=100)
    magistrado: Optional[str] = Field(default=None, max_length=100)


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


def _headers(response: Response) -> None:
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</api/v1/teses>; rel="successor-version"'


def _compat(item: Tese) -> dict:
    return {
        "id": item.id,
        "titulo": item.titulo,
        "descricao": item.descricao,
        "fundamentacao": item.fundamentacao or "",
        "jurisprudencia": item.jurisprudencia,
        "area_juridica": item.area_juridica or "",
        "tribunal": item.tribunal,
        "magistrado": item.magistrado,
        "taxa_sucesso": float(item.taxa_sucesso or 0),
        "vencedora": bool(item.legacy_vencedora) or int(item.vezes_venceu or 0) > 0,
    }


async def _listar_canonicas(
    db: AsyncSession,
    *,
    area: str | None = None,
    vencedoras: bool = False,
    limit: int = 100,
) -> list[Tese]:
    query = select(Tese).where(
        Tese.deleted_at.is_(None),
        Tese.status == TeseStatus.ativa,
    )
    if area:
        query = query.where(Tese.area_juridica == area)
    if vencedoras:
        query = query.where(
            or_(Tese.legacy_vencedora.is_(True), Tese.vezes_venceu > 0)
        )
    query = query.order_by(Tese.taxa_sucesso.desc().nullslast(), Tese.created_at.desc())
    return (await db.execute(query.limit(limit))).scalars().all()


@router.post("/", response_model=TeseResponse, status_code=201, deprecated=True)
async def criar_tese(
    payload: TeseCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["admin", "socio", "advogado"])),
):
    tese = Tese(
        id=str(uuid4()),
        titulo=payload.titulo,
        descricao=payload.descricao,
        fundamentacao=payload.fundamentacao,
        jurisprudencia=payload.jurisprudencia,
        area_juridica=payload.area_juridica,
        tribunal=payload.tribunal,
        magistrado=payload.magistrado,
        tipo=TeseTipo.escritorio,
        status=TeseStatus.ativa,
        vezes_usada=0,
        vezes_venceu=0,
        vezes_perdeu=0,
        taxa_sucesso=0.0,
        legacy_vencedora=False,
        observacoes="Criada pela rota de compatibilidade /teses-v4.",
        created_by=cu.id,
    )
    db.add(tese)
    await db.commit()
    await db.refresh(tese)
    _headers(response)
    return _compat(tese)


@router.get("/", response_model=list[TeseResponse], deprecated=True)
async def listar_teses(
    response: Response,
    area: Optional[str] = None,
    vencedoras: bool = False,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_staff(cu):
        raise HTTPException(403, "Acesso restrito")
    items = await _listar_canonicas(
        db,
        area=area,
        vencedoras=vencedoras,
        limit=100,
    )
    _headers(response)
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
    """Compatibilidade da sugestão antiga usando gateway e dados canônicos."""
    from app.models.ai_log import AITipoUso
    from app.services import ai_gateway as gateway_central
    from app.services.ai_guard import registrar_ai_log, sanitizar_ou_abortar

    if not _is_staff(cu):
        raise HTTPException(403, "Acesso restrito")
    contexto_limpo, pii = sanitizar_ou_abortar(contexto)
    teses = await _listar_canonicas(db, limit=5)
    contexto_teses = "\n".join(
        f"- {item.titulo}: {item.descricao}" for item in teses
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
    _headers(response)
    return {
        "modelo_utilizado": f"{result.provedor}/{result.modelo}",
        "tipo_demanda": "juridico_profundo",
        "resposta": result.texto,
        "status": "sucesso",
        "log_id": log_id,
        "is_rascunho": True,
        "aviso_hitl": "Rascunho sujeito à revisão humana (HITL obrigatório — OAB).",
    }
