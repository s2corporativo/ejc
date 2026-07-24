"""Sub-rotas conversacionais da Sala de Análise Jurídica.

Este router é anexado ao router canônico /raio-x pelo pacote app.routers. Assim,
a evolução reutiliza RBAC, documentos, conversão e trilha do Raio-X existente.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.ownership import is_gestao
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user
from app.models.audit_log import criar_audit_log
from app.models.raio_x import RaioXAnalise
from app.models.user import User
from app.schemas.raio_x import SalaAnaliseConsolidarRequest, SalaAnaliseMensagemRequest
from app.services.sala_analise_service import (
    estado_inicial,
    processar_mensagem,
    serializar_sala,
)

router = APIRouter(tags=["Sala de Análise Jurídica"])
_ROLES = {"superadmin", "admin", "socio", "advogado", "advogado_auxiliar", "estagiario"}


def _role(user: User) -> str:
    return user.role.value if hasattr(user.role, "value") else str(user.role)


async def _obter(db: AsyncSession, analise_id: str, user: User) -> RaioXAnalise:
    if _role(user) not in _ROLES:
        raise HTTPException(403, "Perfil sem acesso à Sala de Análise Jurídica")
    analise = (
        await db.execute(
            select(RaioXAnalise)
            .options(selectinload(RaioXAnalise.documentos))
            .where(RaioXAnalise.id == analise_id, RaioXAnalise.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if not analise:
        raise HTTPException(404, "Análise preliminar não encontrada")
    if not is_gestao(user) and analise.created_by != user.id:
        raise HTTPException(403, "Sem permissão para esta análise preliminar")
    return analise


@router.get("/{analise_id}/sala")
async def obter_sala(
    analise_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    analise = await _obter(db, analise_id, user)
    if not analise.estado_analise:
        analise.estado_analise = estado_inicial(analise)
        await db.commit()
        await db.refresh(analise)
    return serializar_sala(analise)


@router.post(
    "/{analise_id}/mensagens",
    dependencies=[Depends(rate_limit("sala-analise-mensagem", 20))],
)
async def enviar_mensagem(
    analise_id: str,
    payload: SalaAnaliseMensagemRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    analise = await _obter(db, analise_id, user)
    if analise.convertido_case_id:
        raise HTTPException(
            409,
            "A análise já foi convertida em caso. Continue a estratégia no workspace do caso.",
        )
    try:
        resultado = await processar_mensagem(
            db,
            analise=analise,
            user_id=user.id,
            mensagem=payload.mensagem,
            modo=payload.modo,
        )
        await criar_audit_log(
            db,
            user.id,
            _role(user),
            "AI_ANALYSIS",
            "raio_x_analises",
            analise.id,
            detalhes=f"Sala de Análise Jurídica: modo={payload.modo}; resposta em rascunho",
        )
        await db.commit()
        return resultado
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        raise HTTPException(502, f"A análise jurídica não pôde ser concluída: {str(exc)[:180]}")


@router.post(
    "/{analise_id}/consolidar",
    dependencies=[Depends(rate_limit("sala-analise-consolidar", 8))],
)
async def consolidar(
    analise_id: str,
    payload: SalaAnaliseConsolidarRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    analise = await _obter(db, analise_id, user)
    instrucao = (
        "Consolide o estado atual da análise com base em todos os documentos e mensagens. "
        "Elimine duplicidades, preserve contradições e marque premissas superadas."
    )
    if payload.instrucao_adicional:
        instrucao += f"\nObservação do advogado: {payload.instrucao_adicional}"
    try:
        resultado = await processar_mensagem(
            db,
            analise=analise,
            user_id=user.id,
            mensagem=instrucao,
            modo="consolidar",
        )
        analise.ultima_consolidacao_em = datetime.now(timezone.utc)
        await criar_audit_log(
            db,
            user.id,
            _role(user),
            "AI_CONSOLIDATE",
            "raio_x_analises",
            analise.id,
            detalhes="Estado probatório consolidado; revisão humana obrigatória",
        )
        await db.commit()
        return resultado
    except Exception as exc:
        await db.rollback()
        raise HTTPException(502, f"A consolidação não pôde ser concluída: {str(exc)[:180]}")


@router.delete("/{analise_id}/mensagens")
async def limpar_conversa(
    analise_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    analise = await _obter(db, analise_id, user)
    analise.conversa = []
    analise.estado_analise = estado_inicial(analise)
    analise.ultima_consolidacao_em = None
    await criar_audit_log(
        db,
        user.id,
        _role(user),
        "RESET",
        "raio_x_analises",
        analise.id,
        detalhes="Conversa da Sala de Análise reiniciada; documentos preservados",
    )
    await db.commit()
    return {"ok": True, "estado_analise": analise.estado_analise}
