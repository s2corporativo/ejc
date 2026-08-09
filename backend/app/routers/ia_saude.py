"""
ia_saude.py — Dashboard de saúde da IA (#91). Somente Admin/Sócio.
Agrega o AILog (uso, custo, aproveitamento HITL, modelos) — só leitura, sem schema novo.
"""
from __future__ import annotations

import importlib.util
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func as sqlfunc
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.ai_log import AILog
from app.models.user import User

router = APIRouter(prefix="/ia-saude", tags=["IA — Saúde (Admin)"])

# ── GET /ia/status — qualquer usuário logado (P0 usabilidade 2026-07-18) ──────
# Contrato com o frontend: {"disponivel": bool, "mensagem": str|null}.
# Leve e rápido: só configuração (ai_gateway.ia_disponivel), sem chamar
# provedores externos. Router separado porque o prefixo difere (/ia).
router_status = APIRouter(prefix="/ia", tags=["IA — Status"])


@router_status.get("/status")
async def ia_status(cu: User = Depends(get_current_user)):
    """Estado leigo da IA para a UI decidir banners/botões desabilitados."""
    from app.core.ai_errors import MSG_IA_NAO_ATIVADA
    from app.services.ai_gateway import ia_disponivel

    disponivel = ia_disponivel()
    return {
        "disponivel": disponivel,
        "mensagem": None if disponivel else MSG_IA_NAO_ATIVADA,
    }


def _v(x):
    return x.value if hasattr(x, "value") else x


def _busca_semantica_pronta(cfg, *, fastembed_instalado: bool) -> bool:
    """Estado operacional real do mecanismo de embeddings.

    Provider HTTP só está pronto com endpoint configurado. Providers locais
    dependem do FastEmbed instalado. Em ambos os casos EMBEDDINGS_ENABLED é o
    kill-switch autoritativo.
    """
    if not bool(cfg.EMBEDDINGS_ENABLED):
        return False
    provider = str(cfg.EMBEDDINGS_PROVIDER or "local").strip().lower()
    if provider == "http":
        return bool(str(cfg.EMBEDDINGS_API_URL or "").strip())
    return fastembed_instalado


@router.get("/dashboard")
async def dashboard(
    dias: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    role = cu.role.value if hasattr(cu.role, "value") else str(cu.role)
    if role not in ("superadmin", "admin", "socio"):
        raise HTTPException(403, "Acesso restrito (admin/sócio)")

    desde = datetime.now(timezone.utc) - timedelta(days=dias)
    w = AILog.created_at >= desde

    total = (
        await db.execute(select(sqlfunc.count()).select_from(AILog).where(w))
    ).scalar() or 0
    custo = (
        await db.execute(select(sqlfunc.coalesce(sqlfunc.sum(AILog.custo_estimado), 0)).where(w))
    ).scalar() or 0
    pii = (
        await db.execute(
            select(sqlfunc.count())
            .select_from(AILog)
            .where(w, AILog.pii_removida.is_(True))
        )
    ).scalar() or 0

    por_modelo = (
        await db.execute(select(AILog.modelo, sqlfunc.count()).where(w).group_by(AILog.modelo))
    ).all()
    por_tipo = (
        await db.execute(select(AILog.tipo_uso, sqlfunc.count()).where(w).group_by(AILog.tipo_uso))
    ).all()
    por_status = (
        await db.execute(
            select(AILog.status_hitl, sqlfunc.count()).where(w).group_by(AILog.status_hitl)
        )
    ).all()

    aplicados = sum(c for s, c in por_status if _v(s) == "aplicado")
    return {
        "periodo_dias": dias,
        "total_chamadas": total,
        "custo_total_brl": round(float(custo), 4),
        "taxa_aproveitamento_pct": round(aplicados / total * 100, 1) if total else None,
        "chamadas_com_pii_removida": pii,
        "por_modelo": {m: c for m, c in por_modelo},
        "por_tipo_uso": {_v(t): c for t, c in por_tipo},
        "por_status_hitl": {_v(s): c for s, c in por_status},
        "observacao": "Métricas de uso da IA (LGPD/OAB). Apenas leitura do AILog.",
    }


@router.get("/estado-operacional")
async def estado_operacional(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    role = cu.role.value if hasattr(cu.role, "value") else str(cu.role)
    if role not in ("superadmin", "admin", "socio"):
        raise HTTPException(403, "Acesso restrito (admin/socio)")

    cfg = get_settings()

    def _bool_env(name: str, default: bool = False) -> bool:
        val = os.getenv(name)
        if val is None:
            return default
        return val.lower() in ("1", "true", "yes", "on")

    total_logs = (
        await db.execute(select(sqlfunc.count()).select_from(AILog))
    ).scalar() or 0
    try:
        from sqlalchemy import text as _t

        knowledge_docs = (
            await db.execute(_t("select count(*) from knowledge_docs where deleted_at is null"))
        ).scalar() or 0
        knowledge_chunks = (
            await db.execute(_t("select count(*) from knowledge_chunks"))
        ).scalar() or 0
        chunks_embedding = (
            await db.execute(
                _t("select count(*) from knowledge_chunks where embedding is not null")
            )
        ).scalar() or 0
    except Exception:
        knowledge_docs = knowledge_chunks = chunks_embedding = 0

    por_status = (
        await db.execute(select(AILog.status_hitl, sqlfunc.count()).group_by(AILog.status_hitl))
    ).all()
    status_map = {_v(s): c for s, c in por_status}

    embeddings_provider = str(cfg.EMBEDDINGS_PROVIDER or "local").lower()
    fastembed_instalado = importlib.util.find_spec("fastembed") is not None
    embeddings_enabled = bool(cfg.EMBEDDINGS_ENABLED)
    semantic_ready = _busca_semantica_pronta(
        cfg, fastembed_instalado=fastembed_instalado
    )

    externos_permitidos = bool(cfg.AI_EXTERNAL_PROVIDERS_ALLOWED)
    anthropic_habilitado = bool(
        externos_permitidos and cfg.ANTHROPIC_ENABLED and cfg.ANTHROPIC_API_KEY
    )
    maritaca_habilitado = bool(
        externos_permitidos and cfg.MARITACA_ENABLED and cfg.MARITACA_API_KEY
    )
    groq_habilitado = bool(externos_permitidos and cfg.GROQ_API_KEY)
    ollama_habilitado = bool(getattr(cfg, "OLLAMA_ENABLED", False))

    prioridade = [
        p.strip().lower()
        for p in str(cfg.AI_PROVIDER_PRIORITY or "").split(",")
        if p.strip()
    ]
    ativos = {
        "anthropic": anthropic_habilitado,
        "maritaca": maritaca_habilitado,
        "groq": groq_habilitado,
        "ollama": ollama_habilitado,
    }
    elegiveis = [p for p in prioridade if ativos.get(p, False)]

    return {
        "provedores": {
            "anthropic": {
                "suportado": True,
                "habilitado_runtime": anthropic_habilitado,
                "configurado": bool(cfg.ANTHROPIC_API_KEY),
                "enabled": bool(cfg.ANTHROPIC_ENABLED),
                "modelo_complexo": cfg.ANTHROPIC_MODEL_COMPLEXO,
            },
            "maritaca": {
                "suportado": True,
                "habilitado_runtime": maritaca_habilitado,
                "configurado": bool(cfg.MARITACA_API_KEY),
                "enabled": bool(cfg.MARITACA_ENABLED),
                "modelo": cfg.MARITACA_MODEL,
            },
            "groq": {
                "suportado": True,
                "habilitado_runtime": groq_habilitado,
                "configurado": bool(cfg.GROQ_API_KEY),
                "modelo": cfg.GROQ_MODEL,
            },
            "ollama": {
                "suportado": True,
                "habilitado_runtime": ollama_habilitado,
                # compatibilidade com consumidores legados
                "habilitado": ollama_habilitado,
                "opt_in": True,
                "status": "habilitado" if ollama_habilitado else "desativado",
                "modelo_analise": getattr(cfg, "OLLAMA_MODEL_ANALISE", None),
            },
            "externos_permitidos": externos_permitidos,
            "prioridade_runtime": prioridade,
            "elegiveis_na_prioridade": elegiveis,
            "modo": (
                "externo"
                if any(ativos[p] for p in ("anthropic", "maritaca", "groq"))
                else "local"
                if ollama_habilitado
                else "indisponivel"
            ),
            "observacao": (
                "Provider suportado pelo código não significa provider ativo. "
                "Use habilitado_runtime/elegiveis_na_prioridade como estado operacional."
            ),
        },
        "rag": {
            "documentos": knowledge_docs,
            "chunks": knowledge_chunks,
            "chunks_com_embedding": chunks_embedding,
            "busca_semantica_ativa": semantic_ready,
            "embeddings_enabled": embeddings_enabled,
            "provider": embeddings_provider,
            "api_url_configurada": bool(cfg.EMBEDDINGS_API_URL),
            "fastembed_instalado_no_backend": fastembed_instalado,
        },
        "hitl": {
            "total_logs": total_logs,
            "por_status": status_map,
            "pendentes_revisao": status_map.get("gerado", 0),
        },
        "melhorias_recomendadas": [
            "Manter todas as chamadas de IA passando pelo ai_gateway e providers centralizados.",
            "Acompanhar cobertura/qualidade do RAG por fonte, área e vigência.",
            "Manter revisão HITL e citation gate antes de uso jurídico final.",
        ],
    }
