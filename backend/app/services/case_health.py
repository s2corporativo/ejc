# ── app/services/case_health.py ──────────────────────────────────────────────
# Case Health Score (Bloco D) — score 0–100 por caso a partir de dados que já
# existem no banco (prazos, movimentação, procuração, honorários, pós-mortem).
# Não inventa nada: cada dedução aponta o fato concreto que a originou.
#
# Pesos (partindo de 100, descontando):
#   prazo vencido ........................ −20
#   prazo crítico (≤7d) sem ciência ...... −10
#   > 30 dias sem movimentação ........... −15
#   cliente sem procuração ativa ......... −10
#   honorário atrasado ................... −10
#   encerrado/arquivado sem pós-mortem ... −5
from __future__ import annotations

from datetime import date, datetime, timezone, timedelta

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import ROLE_LEVEL
from app.models.user import User
from app.models.case import Case, CaseStatus, CaseMovimento
from app.models.deadline import Deadline, DeadlineStatus
from app.models.fee import Fee, FeeStatus
from app.models.procuracao import Procuracao

ABERTOS = [CaseStatus.triagem, CaseStatus.ativo, CaseStatus.suspenso, CaseStatus.acordo]
FECHADOS = [CaseStatus.encerrado, CaseStatus.arquivado]


def _classificar(score: int) -> str:
    if score >= 80:
        return "saudavel"
    if score >= 60:
        return "atencao"
    if score >= 40:
        return "risco"
    return "critico"


def pode_ver_todos(user: User) -> bool:
    return ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["admin"]


def _filtro_acesso(user: User):
    """Advogado/auxiliar enxergam apenas casos próprios; admin+ vê todos."""
    if pode_ver_todos(user):
        return None
    return or_(Case.advogado_responsavel_id == user.id,
               Case.advogado_auxiliar_id == user.id)


async def calcular_score_caso(db: AsyncSession, case: Case, hoje: date | None = None) -> dict:
    """Score 0–100 de um caso, com a memória de cada dedução."""
    hoje = hoje or date.today()
    agora = datetime.now(timezone.utc)
    score = 100
    fatores: list[dict] = []
    fechado = case.status in FECHADOS

    # Dias sem movimentação — calculado UMA vez, para todo status (fechado
    # incluso), e devolvido no resultado (evita query duplicada nos routers
    # que também precisam do dado, ex.: /visual-law/casos/{id}/alertas).
    # None quando não há referência alguma (sem movimento e sem created_at).
    ult_mov = (await db.execute(
        select(func.max(CaseMovimento.data_evento)).where(CaseMovimento.case_id == case.id)
    )).scalar()
    referencia = ult_mov or case.created_at
    dias_parado: int | None = None
    if referencia is not None:
        if referencia.tzinfo is None:
            referencia = referencia.replace(tzinfo=timezone.utc)
        dias_parado = (agora - referencia).days

    if not fechado:
        # 1) Prazos vencidos (vencido explícito OU pendente com data passada)
        venc = (await db.execute(
            select(func.count()).select_from(Deadline).where(
                Deadline.case_id == case.id, Deadline.deleted_at.is_(None),
                or_(Deadline.status == DeadlineStatus.vencido,
                    and_(Deadline.status == DeadlineStatus.pendente,
                         Deadline.data_prazo < hoje)),
            ))).scalar() or 0
        if venc > 0:
            score -= 20
            fatores.append({"fator": "prazo_vencido", "impacto": -20,
                            "detalhe": f"{venc} prazo(s) vencido(s) em aberto"})

        # 2) Prazo crítico (≤ 7 dias) sem ciência confirmada
        criticos = (await db.execute(
            select(func.count()).select_from(Deadline).where(
                Deadline.case_id == case.id, Deadline.deleted_at.is_(None),
                Deadline.status == DeadlineStatus.pendente,
                Deadline.data_prazo >= hoje,
                Deadline.data_prazo <= hoje + timedelta(days=7),
                Deadline.ciencia_confirmada.is_(False),
            ))).scalar() or 0
        if criticos > 0:
            score -= 10
            fatores.append({"fator": "prazo_critico_sem_ciencia", "impacto": -10,
                            "detalhe": f"{criticos} prazo(s) ≤7 dias sem confirmação de ciência"})

        # 3) Mais de 30 dias sem movimentação (fator não se aplica a fechados)
        if dias_parado is not None and dias_parado > 30:
            score -= 15
            fatores.append({"fator": "sem_movimentacao", "impacto": -15,
                            "detalhe": f"{dias_parado} dias sem movimentação"})

    # 4) Cliente sem procuração ativa (procuração é por cliente)
    proc_ativa = (await db.execute(
        select(func.count()).select_from(Procuracao).where(
            Procuracao.client_id == case.client_id, Procuracao.deleted_at.is_(None),
            Procuracao.revogada.is_(False),
            or_(Procuracao.data_validade.is_(None), Procuracao.data_validade >= hoje),
        ))).scalar() or 0
    if proc_ativa == 0:
        score -= 10
        fatores.append({"fator": "sem_procuracao", "impacto": -10,
                        "detalhe": "Cliente sem procuração ativa/vigente"})

    # 5) Honorário atrasado vinculado ao caso
    hon_atraso = (await db.execute(
        select(func.count()).select_from(Fee).where(
            Fee.case_id == case.id, Fee.deleted_at.is_(None),
            or_(Fee.status == FeeStatus.atrasado,
                and_(Fee.status == FeeStatus.pendente, Fee.data_vencimento < hoje)),
        ))).scalar() or 0
    if hon_atraso > 0:
        score -= 10
        fatores.append({"fator": "honorario_atrasado", "impacto": -10,
                        "detalhe": f"{hon_atraso} honorário(s) em atraso"})

    # 6) Encerrado/arquivado sem pós-mortem (lições aprendidas)
    if fechado and not (case.licoes_aprendidas or "").strip():
        score -= 5
        fatores.append({"fator": "sem_posmortem", "impacto": -5,
                        "detalhe": "Caso encerrado sem lições aprendidas registradas"})

    score = max(0, min(100, score))
    return {
        "case_id": case.id,
        "numero_interno": case.numero_interno,
        "titulo": case.titulo,
        "status": case.status.value,
        "score": score,
        "classificacao": _classificar(score),
        "fatores": fatores,
        "saudavel": not fatores,
        "dias_parado": dias_parado,   # aditivo — consumidores existentes ignoram
    }


async def ranking_saude(db: AsyncSession, user: User, limit: int = 50,
                        apenas_abertos: bool = True) -> dict:
    """Ranking de saúde dos casos (piores primeiro), respeitando acesso."""
    q = select(Case).where(Case.deleted_at.is_(None))
    if apenas_abertos:
        q = q.where(Case.status.in_(ABERTOS))
    filtro = _filtro_acesso(user)
    if filtro is not None:
        q = q.where(filtro)
    casos = (await db.execute(q.limit(500))).scalars().all()

    scores = [await calcular_score_caso(db, c) for c in casos]
    scores.sort(key=lambda s: s["score"])
    distribuicao = {"saudavel": 0, "atencao": 0, "risco": 0, "critico": 0}
    for s in scores:
        distribuicao[s["classificacao"]] += 1
    return {
        "total_casos": len(scores),
        "distribuicao": distribuicao,
        "score_medio": round(sum(s["score"] for s in scores) / len(scores), 1) if scores else None,
        "casos": scores[:limit],
    }
