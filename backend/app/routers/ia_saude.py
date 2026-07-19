"""
ia_saude.py — Dashboard de saúde da IA (#91). Somente Admin/Sócio.
Agrega o AILog (uso, custo, aproveitamento HITL, modelos) — só leitura, sem schema novo.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
import os
import importlib.util

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.ai_log import AILog

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

    total = (await db.execute(
        select(sqlfunc.count()).select_from(AILog).where(w))).scalar() or 0
    custo = (await db.execute(
        select(sqlfunc.coalesce(sqlfunc.sum(AILog.custo_estimado), 0)).where(w))).scalar() or 0
    pii = (await db.execute(
        select(sqlfunc.count()).select_from(AILog).where(w, AILog.pii_removida.is_(True)))).scalar() or 0

    por_modelo = (await db.execute(
        select(AILog.modelo, sqlfunc.count()).where(w).group_by(AILog.modelo))).all()
    por_tipo = (await db.execute(
        select(AILog.tipo_uso, sqlfunc.count()).where(w).group_by(AILog.tipo_uso))).all()
    por_status = (await db.execute(
        select(AILog.status_hitl, sqlfunc.count()).where(w).group_by(AILog.status_hitl))).all()

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

    def _bool_env(name: str) -> bool:
        return os.getenv(name, "").lower() in ("1", "true", "yes", "on")

    total_docs = (await db.execute(select(sqlfunc.count()).select_from(AILog))).scalar() or 0
    try:
        from sqlalchemy import text as _t
        knowledge_docs = (await db.execute(_t("select count(*) from knowledge_docs where deleted_at is null"))).scalar() or 0
        knowledge_chunks = (await db.execute(_t("select count(*) from knowledge_chunks"))).scalar() or 0
        chunks_embedding = (await db.execute(_t("select count(*) from knowledge_chunks where embedding is not null"))).scalar() or 0
    except Exception:
        knowledge_docs = knowledge_chunks = chunks_embedding = 0

    por_status = (await db.execute(
        select(AILog.status_hitl, sqlfunc.count()).group_by(AILog.status_hitl)
    )).all()
    status_map = {_v(s): c for s, c in por_status}

    embeddings_provider = (os.getenv("EMBEDDINGS_PROVIDER") or "local").lower()
    fastembed_instalado = importlib.util.find_spec("fastembed") is not None
    semantic_ready = _bool_env("EMBEDDINGS_ENABLED") and (
        embeddings_provider == "http" or fastembed_instalado
    )
    return {
        "provedores": {
            "groq": {"configurado": bool(os.getenv("GROQ_API_KEY")), "modelo": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")},
            "anthropic": {"configurado": bool(os.getenv("ANTHROPIC_API_KEY"))},
            "ollama": {"habilitado": _bool_env("OLLAMA_ENABLED"), "modelo_analise": os.getenv("OLLAMA_MODEL_ANALISE") or None},
            "modo": os.getenv("AI_PROVIDER") or "auto/padrao",
        },
        "rag": {
            "documentos": knowledge_docs,
            "chunks": knowledge_chunks,
            "chunks_com_embedding": chunks_embedding,
            "busca_semantica_ativa": semantic_ready,
            "embeddings_enabled": _bool_env("EMBEDDINGS_ENABLED"),
            "provider": embeddings_provider,
            "api_url_configurada": bool(os.getenv("EMBEDDINGS_API_URL")),
            "fastembed_instalado_no_backend": fastembed_instalado,
        },
        "hitl": {
            "total_logs": total_docs,
            "por_status": status_map,
            "pendentes_revisao": status_map.get("gerado", 0),
        },
        "melhorias_recomendadas": [
            "Manter todas as novas chamadas de IA passando pelo ai_gateway e pelos providers centralizados.",
            "Ativar worker separado de embeddings para busca semantica sem engordar o backend principal.",
            "Criar rotina obrigatoria de revisao HITL para reduzir logs em status gerado.",
            "Adicionar validador antialucinacao para artigos, jurisprudencia e fontes antes de gerar peca final.",
        ],
    }
