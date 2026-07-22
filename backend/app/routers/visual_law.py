# ── app/routers/visual_law.py ────────────────────────────────────────────────
# Módulo Visual Law — endpoints determinísticos (sem IA):
#   GET  /visual-law/casos/{id}/timeline      linha do tempo visual do processo
#   GET  /visual-law/casos/{id}/matriz-risco  matriz probabilidade × impacto (CPC 25)
#   GET  /visual-law/casos/{id}/alertas       badges de alerta (case_health)
#   POST /visual-law/breakeven                calculadora de ponto de equilíbrio (VPL)
#
# Visibilidade: mesmo gate dos casos (_filtro_visibilidade de routers/cases.py)
# — 404 quando o caso não existe OU não é visível ao usuário (não vaza existência).
# Lógica de negócio em app/services/visual_law_core.py (funções puras testáveis).
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user
from app.models.user import User
from app.models.case import Case
from app.models.deadline import Deadline, DeadlineStatus
from app.routers.cases import _filtro_visibilidade
from app.schemas.visual_law import BreakevenIn
from app.services import bcb_service
from app.services import visual_law_core as vl
from app.services.case_health import FECHADOS, calcular_score_caso

router = APIRouter(prefix="/visual-law", tags=["Visual Law"])


async def _obter_caso_visivel(db: AsyncSession, cu: User, case_id: str) -> Case:
    """Carrega o caso aplicando o MESMO controle de visibilidade dos casos
    (LGPD/RBAC). 404 se não existir ou não for visível ao usuário."""
    q = select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    q = _filtro_visibilidade(q, cu)
    case = (await db.execute(q)).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Caso não encontrado")
    return case


# ── Linha do tempo visual ─────────────────────────────────────────────────────
@router.get("/casos/{case_id}/timeline")
async def timeline_visual(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Linha do tempo VISUAL do caso: fases da jornada processual, eventos
    reais (mesma montagem de /cases/{id}/linha-do-tempo), próximos passos
    determinísticos (prazos reais + estimativas estáticas) e estagnação."""
    case = await _obter_caso_visivel(db, cu, case_id)
    fase = case.fase.value if case.fase else "pre_processual"

    eventos = await vl.montar_eventos_caso(db, case_id)
    dias_parado = await vl.dias_sem_movimentacao(db, case)

    # Prazos pendentes futuros reais do caso (base dos próximos passos)
    prazos_rows = (await db.execute(
        select(Deadline).where(
            Deadline.case_id == case_id,
            Deadline.deleted_at.is_(None),
            Deadline.status == DeadlineStatus.pendente,
            Deadline.data_prazo >= date.today(),
        ).order_by(Deadline.data_prazo).limit(20)
    )).scalars().all()
    prazos = [{"titulo": p.titulo,
               "data": p.data_prazo.isoformat() if p.data_prazo else None}
              for p in prazos_rows]

    return {
        "case_id": case_id,
        "fase_atual": fase,
        "fases": vl.montar_fases(fase),
        "eventos": eventos,
        "proximos_passos": vl.montar_proximos_passos(fase, prazos),
        # Caso encerrado/arquivado não estagna — nível sempre "ok"
        "estagnacao": vl.montar_estagnacao(dias_parado,
                                           fechado=case.status in FECHADOS),
    }


# ── Matriz de risco (probabilidade × impacto, CPC 25) ─────────────────────────
@router.get("/casos/{case_id}/matriz-risco")
async def matriz_risco(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Matriz Probabilidade × Impacto conforme CPC 25.

    A probabilidade só é posicionada quando o risco foi classificado
    explicitamente. O índice de saúde operacional nunca é convertido em chance
    de perda ou êxito.
    """
    case = await _obter_caso_visivel(db, cu, case_id)
    probabilidade, fonte = vl.derivar_probabilidade(case.risco)

    valor_causa = float(case.valor_causa) if case.valor_causa is not None else None
    impacto = vl.classificar_impacto(valor_causa)

    return {
        "case_id": case_id,
        "probabilidade": {"nivel": probabilidade, "fonte": fonte},
        "impacto": {"nivel": impacto, "valor_causa": valor_causa},
        "quadrante": (
            vl.montar_quadrante(probabilidade, impacto)
            if probabilidade is not None
            else None
        ),
        "matriz": vl.montar_matriz(),
    }


# ── Badges de alerta ──────────────────────────────────────────────────────────
@router.get("/casos/{case_id}/alertas")
async def alertas(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Badges de alerta do caso a partir dos fatores do case_health, com a
    regra visual de estagnação: >60 dias parado → badge crítico pulsante."""
    case = await _obter_caso_visivel(db, cu, case_id)
    saude = await calcular_score_caso(db, case)
    # dias_parado já vem do case_health (evita repetir a query de movimentos);
    # sem referência (None) ou referência futura → 0, como em dias_parado_desde.
    dias_parado = max(0, saude["dias_parado"] or 0)

    return {
        "case_id": case_id,
        "score": saude["score"],
        "classificacao": saude["classificacao"],
        "dias_parado": dias_parado,
        # Caso encerrado/arquivado não recebe badge de estagnação
        "badges": vl.montar_badges(saude["fatores"], dias_parado,
                                   fechado=case.status in FECHADOS),
    }


# ── Calculadora de ponto de equilíbrio (breakeven/VPL) ────────────────────────
@router.post("/breakeven",
             dependencies=[Depends(rate_limit("visual-breakeven", 15))])
async def breakeven(
    payload: BreakevenIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Ponto de equilíbrio do acordo: VPL do litígio × acordo imediato.
    Defaults determinísticos: valor/tribunal do caso (se case_id), tempo médio
    de tramitação por tribunal (CNJ) e Selic anualizada do BCB (com fallback)."""
    valor_causa = payload.valor_causa
    tribunal = payload.tribunal

    # Defaults a partir do caso (com o mesmo gate de visibilidade — 404)
    if payload.case_id:
        case = await _obter_caso_visivel(db, cu, payload.case_id)
        if valor_causa is None and case.valor_causa is not None:
            valor_causa = float(case.valor_causa)
        if not tribunal:
            tribunal = case.tribunal

    if not valor_causa or valor_causa <= 0:
        raise HTTPException(
            status_code=422,
            detail="valor_causa é obrigatório: informe no payload ou envie um "
                   "case_id de caso com valor da causa cadastrado.",
        )

    # Tempo de tramitação: informado > média do tribunal (CNJ) > default
    if payload.tempo_anos:
        tempo_anos, tempo_fonte = payload.tempo_anos, "informado"
    else:
        tempo_anos, tempo_fonte = vl.tempo_tramitacao_estimado(tribunal)

    # Selic anual: informada > BCB (série 4390 anualizada) > fallback fixo
    if payload.selic_anual is not None:
        selic_anual, selic_fonte = payload.selic_anual, "informada"
    else:
        selic = await bcb_service.selic_anualizada()
        selic_anual, selic_fonte = selic["selic_anual"], selic["fonte"]

    return vl.calcular_breakeven(
        valor_causa=valor_causa,
        prob_exito=payload.prob_exito,
        tempo_anos=tempo_anos,
        selic_anual=selic_anual,
        custas_pct=vl.normalizar_pct(payload.custas_pct),
        honorarios_sucumbencia_pct=vl.normalizar_pct(payload.honorarios_sucumbencia_pct),
        tribunal=tribunal,
        tempo_fonte=tempo_fonte,
        selic_fonte=selic_fonte,
    )
