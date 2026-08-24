# ── app/routers/teses_alertas_radar.py ────────────────────────────────────────
# Radar Jurisprudencial — consulta e tratamento de alertas (PR 4, Commit 7).
#
#   GET  /teses/alertas                       (staff — EQUIPE_JURIDICA)
#   GET  /teses/{tese_id}/alertas              (staff)
#   POST /teses/alertas/{alerta_id}/tratar     (advogado+, _pode_editar)
#
# Reusa os helpers de RBAC de routers/teses.py (_is_staff/_pode_editar) — não
# redefine. IMPORTANTE: este router é registrado em main.py ANTES de
# teses.router, porque `GET /teses/alertas` (2 segmentos) tem a MESMA forma
# de `GET /teses/{tese_id}` (rota dinâmica de teses.py) — o mesmo tipo de
# colisão que já produziu o bug `/teses/health` na Fase 1 desta série
# (rota dinâmica capturando rota literal). Registrar este router primeiro
# garante que o literal vença, sem precisar tocar em teses.py.
#
# Tratar um alerta (`POST .../tratar`) NUNCA chama `POST /teses/{id}/validacao`
# automaticamente — são atos humanos distintos e deliberadamente
# desacoplados: concordar que um alerta procede não é o mesmo que promover o
# status_validacao da tese, e a especificação do titular proíbe qualquer
# automação nesse encadeamento.
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.audit_log import criar_audit_log
from app.models.tese_extensoes import STATUS_ALERTA, TeseAlertaJurisprudencial
from app.models.user import User
from app.routers.teses import _is_staff, _pode_editar

router = APIRouter(prefix="/teses", tags=["Banco de Teses — Radar Jurisprudencial"])

# Transições que um humano pode aplicar via este endpoint. "novo" fica de
# fora de propósito: é o estado inicial que só o próprio radar atribui —
# tratar um alerta é sempre avançar dele, nunca voltar para "não visto".
_STATUS_APLICAVEIS = tuple(s for s in STATUS_ALERTA if s != "novo")


def _alerta_out(a: TeseAlertaJurisprudencial) -> dict:
    return {
        "id": a.id, "fonte": a.fonte, "titulo": a.titulo, "ementa": a.ementa,
        "tribunal": a.tribunal, "numero_processo": a.numero_processo,
        "link": a.link, "data_julgamento": a.data_julgamento,
        "severidade": a.severidade, "teses_afetadas": a.teses_afetadas,
        "casos_afetados": a.casos_afetados, "status": a.status,
        "tratado_por": a.tratado_por, "tratado_em": a.tratado_em,
        "observacao": a.observacao, "created_at": a.created_at,
    }


@router.get("/alertas")
async def listar_alertas(
    status: Optional[str] = Query(None),
    severidade: Optional[str] = Query(None),
    fonte: Optional[str] = Query(None),
    limite: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _is_staff(cu):
        raise HTTPException(403, "Permissão insuficiente")
    stmt = select(TeseAlertaJurisprudencial)
    if status:
        stmt = stmt.where(TeseAlertaJurisprudencial.status == status)
    if severidade:
        stmt = stmt.where(TeseAlertaJurisprudencial.severidade == severidade)
    if fonte:
        stmt = stmt.where(TeseAlertaJurisprudencial.fonte == fonte)
    stmt = stmt.order_by(TeseAlertaJurisprudencial.created_at.desc()).limit(limite)
    linhas = (await db.execute(stmt)).scalars().all()
    return [_alerta_out(a) for a in linhas]


@router.get("/{tese_id}/alertas")
async def listar_alertas_da_tese(
    tese_id: str,
    limite: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Alertas cujo `teses_afetadas` cita `tese_id`.

    Sem FK direta entre alerta e tese (uma decisão pode afetar N teses,
    `teses_afetadas` é JSON) — filtra em memória sobre uma janela recente.
    Volume esperado é baixo (1 alerta por decisão relevante, não por tese
    afetada), então a janela cobre folgadamente o `limite` pedido.
    """
    if not _is_staff(cu):
        raise HTTPException(403, "Permissão insuficiente")
    candidatos = (await db.execute(
        select(TeseAlertaJurisprudencial)
        .order_by(TeseAlertaJurisprudencial.created_at.desc())
        .limit(limite * 5)
    )).scalars().all()
    filtrados = [
        a for a in candidatos
        if any(t.get("tese_id") == tese_id for t in (a.teses_afetadas or []))
    ][:limite]
    return [_alerta_out(a) for a in filtrados]


class TratarAlertaIn(BaseModel):
    novo_status: str = Field(..., max_length=20)
    observacao: Optional[str] = None


@router.post("/alertas/{alerta_id}/tratar")
async def tratar_alerta(
    alerta_id: str,
    req: TratarAlertaIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if not _pode_editar(cu):
        raise HTTPException(403, "Permissão insuficiente")
    if req.novo_status not in _STATUS_APLICAVEIS:
        raise HTTPException(
            422,
            f"novo_status inválido; use um de {_STATUS_APLICAVEIS}",
        )
    alerta = (await db.execute(
        select(TeseAlertaJurisprudencial).where(TeseAlertaJurisprudencial.id == alerta_id)
    )).scalar_one_or_none()
    if not alerta:
        raise HTTPException(404, "Alerta não encontrado")

    status_anterior = alerta.status
    alerta.status = req.novo_status
    alerta.tratado_por = cu.id
    alerta.tratado_em = datetime.now(timezone.utc)
    if req.observacao:
        alerta.observacao = req.observacao

    await criar_audit_log(
        db, cu.id, getattr(cu.role, "value", str(cu.role)),
        acao="TESE_ALERTA_TRATADO", entidade="teses_alertas_jurisprudenciais",
        registro_id=alerta.id,
        detalhes=f"status: {status_anterior} → {req.novo_status}",
    )
    await db.commit()
    return _alerta_out(alerta)
