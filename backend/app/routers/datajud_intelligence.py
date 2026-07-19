# ── app/routers/datajud_intelligence.py ───────────────────────────────────────
"""Rotas nativas de governança do feed DataJud → inteligência do caso.

Este subrouter é anexado a ``app.routers.andamentos.router`` no startup, mantendo
as funcionalidades dentro do workspace de Casos/Processos, sem criar módulo ou
menu paralelo.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, require_roles
from app.models.audit_log import criar_audit_log
from app.models.user import User
from app.services.datajud_cognitive_feed import (
    alimentar_caso,
    alimentar_lote,
    status_caso,
)

router = APIRouter(tags=["Andamentos — Inteligência do caso"])


@router.post(
    "/inteligencia/datajud/reconstruir-lote",
    dependencies=[Depends(rate_limit("datajud_feed_lote", 2))],
)
async def reconstruir_feed_lote(
    limite: int = Query(100, ge=1, le=500),
    indexar_agora: bool = Query(
        False,
        description=(
            "Quando false, grava chunks pendentes e usa o auto-reindex do EJC. "
            "Quando true, gera embeddings na própria requisição."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio"])),
):
    """Backfill administrativo, idempotente, dos processos já monitorados."""
    resultado = await alimentar_lote(
        db,
        limite=limite,
        embutir_vetores=indexar_agora,
    )
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "RAG_BACKFILL",
        "datajud_cognitive_feed",
        "lote",
        dados_depois={
            "limite": limite,
            "indexar_agora": indexar_agora,
            **resultado,
        },
    )
    await db.commit()
    return resultado


@router.get("/{case_id}/andamentos/inteligencia")
async def consultar_status_feed(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Mostra se a linha do tempo do caso está disponível e vetorizada."""
    case = await verificar_acesso_caso(db, cu, case_id)
    return await status_caso(db, case)


@router.post(
    "/{case_id}/andamentos/alimentar-ia",
    dependencies=[Depends(rate_limit("datajud_alimentar_ia", 5))],
)
async def alimentar_inteligencia_do_caso(
    case_id: str,
    indexar_agora: bool = Query(
        True,
        description="Gera embeddings imediatamente quando o serviço estiver disponível.",
    ),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Reconstrói o contexto cognitivo usando a timeline já armazenada.

    Não consulta tribunal e não cria prazo; é seguro repetir, pois o upsert é
    idempotente e versionado.
    """
    case = await verificar_acesso_caso(db, cu, case_id)
    resultado = await alimentar_caso(
        db,
        case,
        embutir_vetores=indexar_agora,
    )
    await criar_audit_log(
        db,
        cu.id,
        cu.role.value,
        "RAG_SYNC",
        "datajud_cognitive_feed",
        case_id,
        dados_depois={
            "indexar_agora": indexar_agora,
            "movimentos": resultado.get("movimentos", 0),
            "novos": resultado.get("novos", 0),
            "atualizados": resultado.get("atualizados", 0),
            "status": resultado.get("status"),
            "deadline_source": False,
        },
    )
    await db.commit()
    return resultado
