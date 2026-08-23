# ── app/routers/teses_juridicas.py ────────────────────────────────────────────
# Banco Nacional de Teses Jurídicas — CRUD + busca filtrada por força jurídica.
# Integrado ao RAG para análise semântica de casos.
#
# GET    /teses                          → listar com filtros (área, tipo, score, status)
# POST   /teses                          → criar (validador+)
# GET    /teses/{tese_id}                → detalhe com fundamentações + precedentes
# PUT    /teses/{tese_id}                → atualizar (validador+)
# DELETE /teses/{tese_id}                → soft-delete (admin)
# POST   /teses/{tese_id}/scoring        → recalcular score (admin)
# POST   /teses/analise                  → análise RAG de caso vs teses
#
# GET    /taxonomias                     → listar taxonomias
# POST   /taxonomias                     → criar (admin)
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, List
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func as sqlfunc, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, require_roles
from app.models.user import User
from app.models.tese_juridica import (
    Taxonomia, TeseJuridica, FundamentacaoLegal, Precedente,
    TipoTese, StatusTese
)
from app.schemas.tese_schemas import (
    TaxonomiaResponse, TaxonomiaCreate,
    TeseJuridicaResponse, TeseJuridicaCreate, TeseJuridicaUpdate,
    TeseJuridicaDetalhesResponse,
    FundamentacaoLegalResponse, PrecedenteResponse,
)
from app.schemas.common import MsgResponse

logger = logging.getLogger("ejc.teses_juridicas")

router = APIRouter(prefix="/teses", tags=["Banco de Teses Jurídicas"])


# ── TAXONOMIAS ────────────────────────────────────────────────────────────────

taxonomias_router = APIRouter(prefix="/taxonomias", tags=["Banco de Teses — Taxonomias"])


@taxonomias_router.get("", response_model=List[TaxonomiaResponse])
async def listar_taxonomias(
    area: Optional[str] = Query(None, description="Filtrar por área"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Lista taxonomias com filtro opcional por área."""
    q = select(Taxonomia).where(Taxonomia.deleted_at.is_(None))
    if area:
        q = q.where(Taxonomia.area.ilike(f"%{area}%"))
    q = q.order_by(Taxonomia.area, Taxonomia.subarea, Taxonomia.tema)
    result = await db.execute(q)
    return result.scalars().all()


@taxonomias_router.post("", response_model=TaxonomiaResponse)
async def criar_taxonomia(
    body: TaxonomiaCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles("superadmin", "admin")),
):
    """Cria nova entrada de taxonomia (admin+)."""
    # Verifica duplicata
    existente = await db.execute(
        select(Taxonomia).where(
            Taxonomia.area == body.area,
            Taxonomia.subarea == body.subarea,
            Taxonomia.tema == body.tema,
            Taxonomia.subtema == body.subtema,
        )
    )
    if existente.scalar_one_or_none():
        raise HTTPException(409, "Taxonomia já existe (área/subarea/tema/subtema)")

    tax = Taxonomia(**body.model_dump())
    db.add(tax)
    await db.commit()
    await db.refresh(tax)
    return tax


# ── TESES JURÍDICAS ───────────────────────────────────────────────────────────

@router.get("", response_model=dict)
async def listar_teses(
    area: Optional[str] = Query(None, description="Filtrar por área jurídica"),
    tipo: Optional[str] = Query(None, description="ataque|defesa|ambos"),
    status: Optional[str] = Query(None, description="rascunho|em_revisao|validada|nao_validada|descontinuada"),
    score_min: float = Query(0, ge=0, le=100, description="Score mínimo (0–100)"),
    score_max: float = Query(100, ge=0, le=100, description="Score máximo (0–100)"),
    tema: Optional[str] = Query(None, description="Filtrar por tema"),
    ordenar_por: str = Query("score", enum=["score", "criada_em", "titulo"]),
    pagina: int = Query(1, ge=1),
    limite: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Lista teses com filtros e paginação."""
    q = select(TeseJuridica).where(TeseJuridica.deleted_at.is_(None))

    # Filtros
    if area:
        q = q.where(
            TeseJuridica.taxonomia_id.in_(
                select(Taxonomia.id).where(
                    Taxonomia.area.ilike(f"%{area}%"),
                    Taxonomia.deleted_at.is_(None),
                )
            )
        )
    if tema:
        q = q.where(
            TeseJuridica.taxonomia_id.in_(
                select(Taxonomia.id).where(
                    Taxonomia.tema.ilike(f"%{tema}%"),
                    Taxonomia.deleted_at.is_(None),
                )
            )
        )
    if tipo:
        try:
            tipo_enum = TipoTese(tipo)
            q = q.where(TeseJuridica.tipo == tipo_enum)
        except ValueError:
            raise HTTPException(422, f"Tipo inválido: {tipo}")
    if status:
        try:
            status_enum = StatusTese(status)
            q = q.where(TeseJuridica.status == status_enum)
        except ValueError:
            raise HTTPException(422, f"Status inválido: {status}")

    q = q.where(TeseJuridica.score >= score_min, TeseJuridica.score <= score_max)

    # Ordenação
    if ordenar_por == "score":
        q = q.order_by(TeseJuridica.score.desc(), TeseJuridica.criada_em.desc())
    elif ordenar_por == "titulo":
        q = q.order_by(TeseJuridica.titulo)
    else:  # criada_em
        q = q.order_by(TeseJuridica.criada_em.desc())

    # Contagem total
    count_q = select(sqlfunc.count(TeseJuridica.id)).select_from(
        select(TeseJuridica).where(TeseJuridica.deleted_at.is_(None))
    )
    if area:
        count_q = count_q.where(
            TeseJuridica.taxonomia_id.in_(
                select(Taxonomia.id).where(
                    Taxonomia.area.ilike(f"%{area}%"),
                    Taxonomia.deleted_at.is_(None),
                )
            )
        )
    total = await db.scalar(count_q) or 0

    # Paginação
    offset = (pagina - 1) * limite
    q = q.offset(offset).limit(limite)

    result = await db.execute(q)
    teses = result.scalars().all()

    return {
        "total": total,
        "pagina": pagina,
        "limite": limite,
        "teses": [
            TeseJuridicaResponse.model_validate(t) for t in teses
        ]
    }


@router.post("", response_model=TeseJuridicaResponse, dependencies=[Depends(rate_limit("teses-criar", 10))])
async def criar_tese(
    body: TeseJuridicaCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles("superadmin", "admin", "pesquisador_juridico", "auditor_juridico")),
):
    """Cria nova tese jurídica (validador+)."""
    # Verifica taxonomia
    tax = await db.get(Taxonomia, body.taxonomia_id)
    if not tax or tax.deleted_at:
        raise HTTPException(404, "Taxonomia não encontrada")

    tese = TeseJuridica(
        id=str(uuid4()),
        **body.model_dump(exclude={"id"}),
        criada_por=cu.id,
        criada_em=datetime.now(timezone.utc),
    )
    db.add(tese)
    await db.commit()
    await db.refresh(tese)
    logger.info(f"Tese criada: {tese.id} por {cu.id}")
    return TeseJuridicaResponse.model_validate(tese)


@router.get("/{tese_id}", response_model=TeseJuridicaDetalhesResponse)
async def obter_tese(
    tese_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Obtém detalhes completos da tese (com fundamentações e precedentes)."""
    q = select(TeseJuridica).where(
        TeseJuridica.id == tese_id,
        TeseJuridica.deleted_at.is_(None),
    ).options(
        selectinload(TeseJuridica.fundamentacoes),
        selectinload(TeseJuridica.precedentes),
        selectinload(TeseJuridica.processos_vitoriosos),
    )
    tese = (await db.execute(q)).scalar_one_or_none()
    if not tese:
        raise HTTPException(404, "Tese não encontrada")

    return TeseJuridicaDetalhesResponse.model_validate(tese)


@router.put("/{tese_id}", response_model=TeseJuridicaResponse)
async def atualizar_tese(
    tese_id: str,
    body: TeseJuridicaUpdate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles("superadmin", "admin", "pesquisador_juridico", "auditor_juridico")),
):
    """Atualiza tese jurídica (validador+)."""
    tese = await db.get(TeseJuridica, tese_id)
    if not tese or tese.deleted_at:
        raise HTTPException(404, "Tese não encontrada")

    # Verifica novo taxonomia_id se fornecido
    if body.taxonomia_id and body.taxonomia_id != tese.taxonomia_id:
        tax = await db.get(Taxonomia, body.taxonomia_id)
        if not tax or tax.deleted_at:
            raise HTTPException(404, "Taxonomia não encontrada")

    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(tese, key, value)

    tese.revisada_por = cu.id
    tese.revisada_em = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(tese)
    logger.info(f"Tese atualizada: {tese_id} por {cu.id}")
    return TeseJuridicaResponse.model_validate(tese)


@router.delete("/{tese_id}", response_model=MsgResponse)
async def deletar_tese(
    tese_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles("superadmin", "admin")),
):
    """Soft-deleta tese jurídica (admin+)."""
    tese = await db.get(TeseJuridica, tese_id)
    if not tese or tese.deleted_at:
        raise HTTPException(404, "Tese não encontrada")

    tese.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    logger.info(f"Tese deletada: {tese_id} por {cu.id}")
    return {"msg": "Tese removida com sucesso"}


@router.post("/{tese_id}/scoring", response_model=TeseJuridicaResponse)
async def recalcular_score(
    tese_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles("superadmin", "admin")),
):
    """Recalcula score de força jurídica da tese (admin+).

    Score é calculado como:
    - Base: 50 (vinculante) ou 30 (não vinculante)
    - +10 se tipo=ataque
    - +5 por precedente favorável
    - -10 por precedente contrário
    """
    tese = await db.get(TeseJuridica, tese_id)
    if not tese or tese.deleted_at:
        raise HTTPException(404, "Tese não encontrada")

    # Carregar precedentes
    q = select(Precedente).where(
        Precedente.tese_id == tese_id,
        Precedente.deleted_at.is_(None),
    )
    result = await db.execute(q)
    precedentes = result.scalars().all()

    score = 50 if tese.vinculante else 30
    if tese.tipo == TipoTese.ataque:
        score += 10

    for prec in precedentes:
        if prec.tipo_relacao == "favoravel":
            score += 5
        elif prec.tipo_relacao == "contradiz":
            score -= 10

    tese.score = min(100, max(0, score))
    tese.auditada_por = cu.id
    tese.auditada_em = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(tese)
    logger.info(f"Score recalculado: {tese_id} = {tese.score} por {cu.id}")
    return TeseJuridicaResponse.model_validate(tese)


# ── ANÁLISE RAG ────────────────────────────────────────────────────────────────

class AnaliseTeseRequest(BaseModel):
    texto_caso: str = Field(..., min_length=20, max_length=50000)
    documento_id: Optional[str] = None
    processo_id: Optional[str] = None
    areas_interesse: Optional[List[str]] = None
    apenas_ataque: bool = False
    apenas_defesa: bool = False
    limite_teses: int = Field(10, ge=1, le=50)


class AnaliseTeseResponse(BaseModel):
    questao_juridica: str
    teses_ataque: List[TeseJuridicaResponse]
    teses_defesa: List[TeseJuridicaResponse]
    contrateses: dict  # mapeamento de tese A → [tesas que a contradizem]
    confianca: float  # 0.0-1.0
    notas: str


@router.post("/analise", response_model=AnaliseTeseResponse, dependencies=[Depends(rate_limit("teses-analise", 5))])
async def analisar_caso_vs_teses(
    body: AnaliseTeseRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Análise RAG: retorna teses jurídicas relevantes para o caso.

    Futura integração com embeddings semânticos via pgvector.
    Por ora, busca por taxonomia e score.
    """
    # TODO: implementar análise semântica com RAG na Etapa 3
    # Por enquanto, busca simples por score e validade

    q = select(TeseJuridica).where(
        TeseJuridica.deleted_at.is_(None),
        TeseJuridica.status == StatusTese.validada,
        TeseJuridica.score >= 60,
    ).options(
        selectinload(TeseJuridica.fundamentacoes),
        selectinload(TeseJuridica.precedentes),
    ).order_by(TeseJuridica.score.desc()).limit(body.limite_teses)

    if not body.apenas_defesa:
        q = q.where(
            or_(
                TeseJuridica.tipo == TipoTese.ataque,
                TeseJuridica.tipo == TipoTese.ambos,
            )
        )
    if not body.apenas_ataque:
        q = q.where(
            or_(
                TeseJuridica.tipo == TipoTese.defesa,
                TeseJuridica.tipo == TipoTese.ambos,
            )
        )

    result = await db.execute(q)
    teses = result.scalars().all()

    teses_ataque = [
        t for t in teses if t.tipo in (TipoTese.ataque, TipoTese.ambos)
    ]
    teses_defesa = [
        t for t in teses if t.tipo in (TipoTese.defesa, TipoTese.ambos)
    ]

    # Extrair contrateses (teses que se contradizem)
    contrateses = {}
    for tese in teses:
        q_contra = select(Precedente).where(
            Precedente.tese_id == tese.id,
            Precedente.tipo_relacao == "contradiz",
            Precedente.deleted_at.is_(None),
        )
        result = await db.execute(q_contra)
        contrateses[tese.id] = [p.precedente_id for p in result.scalars().all() if p.precedente_id]

    logger.info(f"Análise RAG: {len(teses)} teses para caso por {cu.id}")

    return AnaliseTeseResponse(
        questao_juridica="[Análise semântica RAG — implementado na Etapa 3]",
        teses_ataque=[TeseJuridicaResponse.model_validate(t) for t in teses_ataque],
        teses_defesa=[TeseJuridicaResponse.model_validate(t) for t in teses_defesa],
        contrateses=contrateses,
        confianca=0.6,  # placeholder
        notas="Busca por score validado; análise semântica com pgvector em desenvolvimento",
    )


# ── PRECEDENTES (sub-routers) ──────────────────────────────────────────────────

precedentes_router = APIRouter(prefix="/teses/{tese_id}/precedentes", tags=["Banco de Teses — Precedentes"])


@precedentes_router.post("", response_model=PrecedenteResponse)
async def adicionar_precedente(
    tese_id: str,
    tribunal: str = Query(...),
    classe: str = Query(...),
    numero: str = Query(...),
    tipo_relacao: str = Query(..., enum=["favoravel", "desfavoravel", "parcial", "contradiz"]),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles("superadmin", "admin", "pesquisador_juridico")),
):
    """Adiciona precedente/jurisprudência vinculado à tese."""
    tese = await db.get(TeseJuridica, tese_id)
    if not tese or tese.deleted_at:
        raise HTTPException(404, "Tese não encontrada")

    precedente = Precedente(
        id=str(uuid4()),
        tese_id=tese_id,
        tribunal=tribunal,
        classe=classe,
        numero=numero,
        tipo_relacao=tipo_relacao,
        fonte="manual",
        fonte_url="",  # URL será preenchida com scraping real
    )
    db.add(precedente)
    await db.commit()
    await db.refresh(precedente)
    logger.info(f"Precedente adicionado: {precedente.id} a tese {tese_id}")
    return PrecedenteResponse.model_validate(precedente)


# ── HEALTH CHECK ───────────────────────────────────────────────────────────────

@router.get("/health", tags=["Health"])
async def health_check(db: AsyncSession = Depends(get_db)):
    """Health check da base de teses jurídicas."""
    try:
        total = await db.scalar(
            select(sqlfunc.count(TeseJuridica.id)).where(
                TeseJuridica.deleted_at.is_(None)
            )
        )
        validadas = await db.scalar(
            select(sqlfunc.count(TeseJuridica.id)).where(
                TeseJuridica.deleted_at.is_(None),
                TeseJuridica.status == StatusTese.validada,
            )
        )
        return {
            "status": "ok",
            "total_teses": total or 0,
            "teses_validadas": validadas or 0,
        }
    except Exception as e:
        logger.error(f"Health check falhou: {e}")
        return {"status": "erro", "detalhe": str(e)}
