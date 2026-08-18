from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func as sqlfunc, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.ai_provider_metric import AIProviderMetric
from app.models.user import User
from app.services.ai.provider_registry import (
    PROVIDERS_SUPORTADOS,
    motivo_inelegivel,
    provider_elegivel,
)

router = APIRouter(prefix="/ia-governanca", tags=["IA — Provedores (Admin)"])


def _role(user: User) -> str:
    return str(getattr(user.role, "value", user.role))


def _require_gestao(user: User) -> None:
    if _role(user) not in ("superadmin", "admin", "socio"):
        raise HTTPException(403, "Acesso restrito à governança da IA")


def _modelo_configurado(provider: str) -> str | None:
    settings = get_settings()
    return {
        "anthropic": settings.ANTHROPIC_MODEL_COMPLEXO or settings.ANTHROPIC_MODEL_RAPIDO,
        "maritaca": settings.MARITACA_MODEL or settings.MARITACA_MODEL_RAPIDO,
        "groq": settings.GROQ_MODEL,
        "ollama": settings.OLLAMA_MODEL_ANALISE,
    }.get(provider)


def _status_operacional(elegivel: bool, tentativas: int, falhas: int, sucessos: int) -> str:
    if not elegivel:
        return "desabilitado"
    if tentativas == 0:
        return "configurado_sem_uso"
    if sucessos == 0:
        return "indisponivel"
    if falhas / tentativas >= 0.25:
        return "atencao"
    return "operacional"


@router.get("/provedores")
async def painel_provedores(
    dias: int = Query(30, ge=1, le=365),
    limite: int = Query(40, ge=5, le=200),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Métricas técnicas agregadas, sem prompts, respostas ou dados pessoais."""
    _require_gestao(cu)
    desde = datetime.now(timezone.utc) - timedelta(days=dias)
    settings = get_settings()
    prioridade = [
        item.strip().lower()
        for item in (settings.AI_PROVIDER_PRIORITY or "").split(",")
        if item.strip()
    ]

    sucesso = case((AIProviderMetric.status == "sucesso", 1), else_=0)
    falha = case((AIProviderMetric.status != "sucesso", 1), else_=0)
    fallback_sucesso = case(
        (
            (AIProviderMetric.status == "sucesso")
            & AIProviderMetric.fallback_triggered.is_(True),
            1,
        ),
        else_=0,
    )

    try:
        resumo_row = (
            await db.execute(
                select(
                    sqlfunc.count(AIProviderMetric.id),
                    sqlfunc.coalesce(sqlfunc.sum(sucesso), 0),
                    sqlfunc.coalesce(sqlfunc.sum(falha), 0),
                    sqlfunc.coalesce(sqlfunc.sum(fallback_sucesso), 0),
                    sqlfunc.coalesce(sqlfunc.sum(AIProviderMetric.input_tokens), 0),
                    sqlfunc.coalesce(sqlfunc.sum(AIProviderMetric.output_tokens), 0),
                    sqlfunc.coalesce(sqlfunc.sum(AIProviderMetric.estimated_cost_brl), 0),
                    sqlfunc.avg(
                        case(
                            (AIProviderMetric.status == "sucesso", AIProviderMetric.duration_ms),
                            else_=None,
                        )
                    ),
                ).where(AIProviderMetric.created_at >= desde)
            )
        ).one()

        provider_rows = (
            await db.execute(
                select(
                    AIProviderMetric.provider,
                    sqlfunc.count(AIProviderMetric.id),
                    sqlfunc.coalesce(sqlfunc.sum(sucesso), 0),
                    sqlfunc.coalesce(sqlfunc.sum(falha), 0),
                    sqlfunc.coalesce(sqlfunc.sum(fallback_sucesso), 0),
                    sqlfunc.avg(
                        case(
                            (AIProviderMetric.status == "sucesso", AIProviderMetric.duration_ms),
                            else_=None,
                        )
                    ),
                    sqlfunc.coalesce(sqlfunc.sum(AIProviderMetric.input_tokens), 0),
                    sqlfunc.coalesce(sqlfunc.sum(AIProviderMetric.output_tokens), 0),
                    sqlfunc.coalesce(sqlfunc.sum(AIProviderMetric.estimated_cost_brl), 0),
                    sqlfunc.max(AIProviderMetric.created_at),
                )
                .where(AIProviderMetric.created_at >= desde)
                .group_by(AIProviderMetric.provider)
            )
        ).all()

        task_rows = (
            await db.execute(
                select(
                    AIProviderMetric.task_type,
                    AIProviderMetric.provider,
                    sqlfunc.count(AIProviderMetric.id),
                    sqlfunc.coalesce(sqlfunc.sum(sucesso), 0),
                    sqlfunc.avg(
                        case(
                            (AIProviderMetric.status == "sucesso", AIProviderMetric.duration_ms),
                            else_=None,
                        )
                    ),
                    sqlfunc.coalesce(sqlfunc.sum(AIProviderMetric.estimated_cost_brl), 0),
                )
                .where(AIProviderMetric.created_at >= desde)
                .group_by(AIProviderMetric.task_type, AIProviderMetric.provider)
                .order_by(sqlfunc.count(AIProviderMetric.id).desc())
                .limit(60)
            )
        ).all()

        recent = (
            await db.execute(
                select(AIProviderMetric)
                .where(AIProviderMetric.created_at >= desde)
                .order_by(AIProviderMetric.created_at.desc())
                .limit(limite)
            )
        ).scalars().all()
        historico_disponivel = True
    except SQLAlchemyError:
        # Durante o primeiro deploy a API continua utilizável enquanto a migration
        # ainda não terminou. O painel informa a ausência sem mascarar como zero real.
        resumo_row = (0, 0, 0, 0, 0, 0, 0, None)
        provider_rows = []
        task_rows = []
        recent = []
        historico_disponivel = False

    total, sucessos_total, falhas_total, fallbacks_total, tokens_in, tokens_out, custo, latencia = resumo_row
    por_nome = {row[0]: row for row in provider_rows}
    providers = []
    for provider in PROVIDERS_SUPORTADOS:
        row = por_nome.get(provider)
        tentativas = int(row[1]) if row else 0
        sucessos_provider = int(row[2]) if row else 0
        falhas_provider = int(row[3]) if row else 0
        fallbacks_provider = int(row[4]) if row else 0
        latencia_media = round(float(row[5]), 1) if row and row[5] is not None else None
        provider_tokens_in = int(row[6]) if row else 0
        provider_tokens_out = int(row[7]) if row else 0
        provider_custo = round(float(row[8]), 4) if row else 0.0
        ultimo_uso = row[9].isoformat() if row and row[9] else None
        elegivel = bool(provider_elegivel(provider))
        providers.append(
            {
                "provider": provider,
                "modelo_configurado": _modelo_configurado(provider),
                "elegivel": elegivel,
                # Sem isto o painel dizia só "desabilitado", sem distinguir
                # chave ausente de flag desligada ou kill-switch global.
                "motivo_inelegivel": None if elegivel else motivo_inelegivel(provider),
                "ordem_prioridade": prioridade.index(provider) + 1 if provider in prioridade else None,
                "status": _status_operacional(
                    elegivel, tentativas, falhas_provider, sucessos_provider
                ),
                "tentativas": tentativas,
                "sucessos": sucessos_provider,
                "falhas": falhas_provider,
                "taxa_sucesso_pct": round(sucessos_provider / tentativas * 100, 1)
                if tentativas
                else None,
                "fallbacks_concluidos": fallbacks_provider,
                "latencia_media_ms": latencia_media,
                "tokens_input": provider_tokens_in,
                "tokens_output": provider_tokens_out,
                "custo_brl": provider_custo,
                "custo_medio_sucesso_brl": round(provider_custo / sucessos_provider, 6)
                if sucessos_provider
                else None,
                "ultimo_uso": ultimo_uso,
            }
        )

    comparaveis = [p for p in providers if p["sucessos"] >= 3]
    comparaveis.sort(
        key=lambda p: (
            -(p["taxa_sucesso_pct"] or 0),
            p["latencia_media_ms"] if p["latencia_media_ms"] is not None else 10**12,
            p["custo_medio_sucesso_brl"]
            if p["custo_medio_sucesso_brl"] is not None
            else 10**12,
        )
    )

    return {
        "periodo_dias": dias,
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
        "historico_disponivel": historico_disponivel,
        "resumo": {
            "tentativas": int(total),
            "sucessos": int(sucessos_total),
            "falhas": int(falhas_total),
            "taxa_sucesso_pct": round(int(sucessos_total) / int(total) * 100, 1)
            if total
            else None,
            "fallbacks_concluidos": int(fallbacks_total),
            "latencia_media_ms": round(float(latencia), 1) if latencia is not None else None,
            "tokens_input": int(tokens_in),
            "tokens_output": int(tokens_out),
            "custo_brl": round(float(custo), 4),
        },
        "configuracao": {
            "ia_habilitada": bool(settings.AI_ENABLED),
            "externos_permitidos": bool(settings.AI_EXTERNAL_PROVIDERS_ALLOWED),
            "prioridade": prioridade,
        },
        "provedores": providers,
        "comparacao": {
            "melhor_equilibrio": comparaveis[0]["provider"] if comparaveis else None,
            "criterio": "taxa de sucesso, depois menor latência e menor custo; mínimo de 3 sucessos",
        },
        "por_tarefa": [
            {
                "task_type": task,
                "provider": provider,
                "tentativas": int(n),
                "sucessos": int(ok),
                "taxa_sucesso_pct": round(int(ok) / int(n) * 100, 1) if n else None,
                "latencia_media_ms": round(float(avg_ms), 1) if avg_ms is not None else None,
                "custo_brl": round(float(task_cost), 4),
            }
            for task, provider, n, ok, avg_ms, task_cost in task_rows
        ],
        "eventos_recentes": [
            {
                "id": item.id,
                "provider": item.provider,
                "model": item.model,
                "task_type": item.task_type,
                "status": item.status,
                "duration_ms": item.duration_ms,
                "input_tokens": item.input_tokens,
                "output_tokens": item.output_tokens,
                "estimated_cost_brl": round(float(item.estimated_cost_brl or 0), 6),
                "fallback_triggered": bool(item.fallback_triggered),
                "fallback_reason": item.fallback_reason,
                "error_type": item.error_type,
                "http_status": item.http_status,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in recent
        ],
        "privacidade": "Somente metadados técnicos. Prompts, respostas, nomes, CPF/CNPJ e conteúdo jurídico não são armazenados nesta telemetria.",
        "observacao": "O histórico começa após a aplicação da migration 111; chamadas anteriores permanecem apenas no AILog legado.",
    }
