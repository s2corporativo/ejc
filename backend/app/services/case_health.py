# ── app/services/case_health.py ──────────────────────────────────────────────
# Saúde operacional do caso, derivada exclusivamente de fatos existentes no
# banco. O score legado 0–100 é preservado por compatibilidade de contrato, mas
# novas telas devem preferir `estado_operacional` (normal|atencao|critico), que
# não sugere probabilidade de êxito nem cria falsa precisão jurídica.
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ownership import pode_ver_todos
from app.models.case import Case, CaseMovimento, CaseStatus
from app.models.deadline import Deadline, DeadlineStatus
from app.models.fee import Fee, FeeStatus
from app.models.procuracao import Procuracao
from app.models.user import User

ABERTOS = [
    CaseStatus.aberto,
    CaseStatus.em_instrucao,
    CaseStatus.em_producao,
    CaseStatus.protocolado,
]
FECHADOS = [CaseStatus.encerrado, CaseStatus.arquivado]

# Contrato legado. Mantido enquanto consumidores ainda dependem de
# `score`/`classificacao`; não usar como chance de êxito.
LIMIAR_SAUDAVEL = 80
LIMIAR_ATENCAO = 60
LIMIAR_RISCO = 40

# Bloqueadores operacionais que justificam estado crítico independentemente da
# soma do score. A lista deve conter apenas fatos verificáveis nesta camada.
_FATORES_CRITICOS = frozenset({"prazo_vencido"})


def _classificar(score: int) -> str:
    """Classificação histórica do score, preservada por compatibilidade."""
    if score >= LIMIAR_SAUDAVEL:
        return "saudavel"
    if score >= LIMIAR_ATENCAO:
        return "atencao"
    if score >= LIMIAR_RISCO:
        return "risco"
    return "critico"


def _estado_operacional(fatores: list[dict]) -> str:
    """Retorna normal|atencao|critico sem inferir probabilidade jurídica.

    - `critico`: existe ao menos um bloqueador operacional comprovado;
    - `atencao`: há pendência/fator relevante, mas nenhum bloqueador crítico;
    - `normal`: nenhum fator objetivo foi encontrado por este serviço.

    Este helper deliberadamente não usa o valor numérico do score. Assim um
    ajuste futuro de pesos não muda silenciosamente a severidade operacional.
    """
    codigos = {str(item.get("fator") or "") for item in fatores}
    if codigos & _FATORES_CRITICOS:
        return "critico"
    if codigos:
        return "atencao"
    return "normal"


def _filtro_acesso(user: User):
    """Advogado/auxiliar enxergam apenas casos próprios; admin+ vê todos."""
    if pode_ver_todos(user):
        return None
    return or_(
        Case.advogado_responsavel_id == user.id,
        Case.advogado_auxiliar_id == user.id,
    )


async def calcular_score_caso(
    db: AsyncSession,
    case: Case,
    hoje: date | None = None,
) -> dict:
    """Calcula saúde do caso com memória factual de cada achado.

    `score` e `classificacao` são mantidos para consumidores legados.
    `estado_operacional` é o contrato recomendado para decisão operacional.
    """
    hoje = hoje or date.today()
    agora = datetime.now(timezone.utc)
    score = 100
    fatores: list[dict] = []
    fechado = case.status in FECHADOS

    ult_mov = (
        await db.execute(
            select(func.max(CaseMovimento.data_evento)).where(
                CaseMovimento.case_id == case.id
            )
        )
    ).scalar()
    referencia = ult_mov or case.created_at
    dias_parado: int | None = None
    if referencia is not None:
        if referencia.tzinfo is None:
            referencia = referencia.replace(tzinfo=timezone.utc)
        dias_parado = (agora - referencia).days

    if not fechado:
        # Prazo vencido: fato crítico e não mero redutor estatístico.
        venc = (
            await db.execute(
                select(func.count())
                .select_from(Deadline)
                .where(
                    Deadline.case_id == case.id,
                    Deadline.deleted_at.is_(None),
                    or_(
                        Deadline.status == DeadlineStatus.vencido,
                        and_(
                            Deadline.status == DeadlineStatus.pendente,
                            Deadline.data_prazo < hoje,
                        ),
                    ),
                )
            )
        ).scalar() or 0
        if venc > 0:
            score -= 20
            fatores.append(
                {
                    "fator": "prazo_vencido",
                    "impacto": -20,
                    "detalhe": f"{venc} prazo(s) vencido(s) em aberto",
                }
            )

        # Prazo próximo sem ciência confirmada: atenção, não confirmação de
        # perda de prazo. A origem do prazo continua governada pelo módulo de
        # Prazos/HITL.
        criticos = (
            await db.execute(
                select(func.count())
                .select_from(Deadline)
                .where(
                    Deadline.case_id == case.id,
                    Deadline.deleted_at.is_(None),
                    Deadline.status == DeadlineStatus.pendente,
                    Deadline.data_prazo >= hoje,
                    Deadline.data_prazo <= hoje + timedelta(days=7),
                    Deadline.ciencia_confirmada.is_(False),
                )
            )
        ).scalar() or 0
        if criticos > 0:
            score -= 10
            fatores.append(
                {
                    "fator": "prazo_critico_sem_ciencia",
                    "impacto": -10,
                    "detalhe": (
                        f"{criticos} prazo(s) ≤7 dias sem confirmação de ciência"
                    ),
                }
            )

        if dias_parado is not None and dias_parado > 30:
            score -= 15
            fatores.append(
                {
                    "fator": "sem_movimentacao",
                    "impacto": -15,
                    "detalhe": f"{dias_parado} dias sem movimentação",
                }
            )

    proc_ativa = (
        await db.execute(
            select(func.count())
            .select_from(Procuracao)
            .where(
                Procuracao.client_id == case.client_id,
                Procuracao.deleted_at.is_(None),
                Procuracao.revogada.is_(False),
                or_(
                    Procuracao.data_validade.is_(None),
                    Procuracao.data_validade >= hoje,
                ),
            )
        )
    ).scalar() or 0
    if proc_ativa == 0:
        score -= 10
        fatores.append(
            {
                "fator": "sem_procuracao",
                "impacto": -10,
                "detalhe": "Cliente sem procuração ativa/vigente",
            }
        )

    hon_atraso = (
        await db.execute(
            select(func.count())
            .select_from(Fee)
            .where(
                Fee.case_id == case.id,
                Fee.deleted_at.is_(None),
                or_(
                    Fee.status == FeeStatus.atrasado,
                    and_(
                        Fee.status == FeeStatus.pendente,
                        Fee.data_vencimento < hoje,
                    ),
                ),
            )
        )
    ).scalar() or 0
    if hon_atraso > 0:
        score -= 10
        fatores.append(
            {
                "fator": "honorario_atrasado",
                "impacto": -10,
                "detalhe": f"{hon_atraso} honorário(s) em atraso",
            }
        )

    if fechado and not (case.licoes_aprendidas or "").strip():
        score -= 5
        fatores.append(
            {
                "fator": "sem_posmortem",
                "impacto": -5,
                "detalhe": "Caso encerrado sem lições aprendidas registradas",
            }
        )

    score = max(0, min(100, score))
    return {
        "case_id": case.id,
        "numero_interno": case.numero_interno,
        "titulo": case.titulo,
        "status": case.status.value,
        "score": score,
        "classificacao": _classificar(score),
        "estado_operacional": _estado_operacional(fatores),
        "fatores": fatores,
        "dias_parado": dias_parado,
    }


async def ranking_saude(
    db: AsyncSession,
    user: User,
    limit: int = 50,
    apenas_abertos: bool = True,
) -> dict:
    """Ranking de saúde dos casos, respeitando o mesmo ownership canônico."""
    q = select(Case).where(Case.deleted_at.is_(None))
    if apenas_abertos:
        q = q.where(Case.status.in_(ABERTOS))
    filtro = _filtro_acesso(user)
    if filtro is not None:
        q = q.where(filtro)
    casos = (await db.execute(q.limit(500))).scalars().all()

    scores = [await calcular_score_caso(db, c) for c in casos]
    scores.sort(key=lambda s: s["score"])

    # Contrato legado.
    distribuicao = {"saudavel": 0, "atencao": 0, "risco": 0, "critico": 0}
    # Contrato recomendado para UX operacional.
    distribuicao_operacional = {"normal": 0, "atencao": 0, "critico": 0}
    for item in scores:
        distribuicao[item["classificacao"]] += 1
        distribuicao_operacional[item["estado_operacional"]] += 1

    return {
        "total_casos": len(scores),
        "distribuicao": distribuicao,
        "distribuicao_operacional": distribuicao_operacional,
        "score_medio": (
            round(sum(s["score"] for s in scores) / len(scores), 1)
            if scores
            else None
        ),
        "casos": scores[:limit],
    }
