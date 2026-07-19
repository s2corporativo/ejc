# ── app/routers/dashboard.py ─────────────────────────────────────────────────
# Dashboard executivo — KPIs do escritório em uma chamada.
import logging
import time
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_roles
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

# Cache TTL em processo (sem Redis). A chave inclui o escopo financeiro do
# usuário (admin vê 'escritorio'; demais veem 'meus_casos' por uid), evitando
# vazamento de dados financeiros entre perfis. TTL curto: KPIs toleram defasagem.
# Compatível com uvicorn --workers 1 (cache global e consistente).
_DASHBOARD_TTL_S = 30.0
_dashboard_cache: dict[str, tuple[float, dict]] = {}


def _cache_get(chave: str) -> dict | None:
    item = _dashboard_cache.get(chave)
    if item and (time.monotonic() - item[0]) < _DASHBOARD_TTL_S:
        return item[1]
    return None


def _cache_set(chave: str, valor: dict) -> None:
    _dashboard_cache[chave] = (time.monotonic(), valor)


@router.get("/")
async def dashboard(
    db: AsyncSession = Depends(get_db),
    # Piso de staff: agregações globais do escritório não devem ser expostas fora
    # da equipe. Piso em `secretaria` (nível 2 = todo o staff) — a recepção tem
    # `dashboard_atendimento` e usa o painel; cliente_externo já é barrado pelo
    # AuthMiddleware. O escopo financeiro por uid abaixo permanece.
    cu: User = Depends(require_roles(["secretaria"])),
):
    from app.core.security import ROLE_LEVEL as _RL

    ve_total = _RL.get(cu.role.value, 0) >= _RL["admin"]
    cache_key = "escritorio" if ve_total else f"meus_casos:{cu.id}"
    _cached = _cache_get(cache_key)
    if _cached is not None:
        return _cached

    hoje = date.today()
    d3, d7 = hoje + timedelta(days=3), hoje + timedelta(days=7)

    casos_status: dict[str, int] = {}
    casos_area: list[dict] = []
    pv = pc = p7 = 0
    fin_pend = fin_atras = fin_mes = 0
    fin_escopo = "escritorio" if ve_total else "meus_casos"
    amb_criticas = 0
    clientes_ativos = 0
    pecas_hitl = 0

    try:
        r = await db.execute(text("""
            SELECT status, COUNT(*) FROM cases
            WHERE deleted_at IS NULL GROUP BY status
        """))
        casos_status = {row[0]: row[1] for row in r}
    except Exception:
        logger.warning("Dashboard: falha ao carregar casos por status", exc_info=True)

    try:
        r = await db.execute(text("""
            SELECT area, COUNT(*) FROM cases
            WHERE deleted_at IS NULL
            GROUP BY area ORDER BY COUNT(*) DESC
        """))
        casos_area = [{"area": row[0], "total": row[1]} for row in r]
    except Exception:
        logger.warning("Dashboard: falha ao carregar casos por área", exc_info=True)

    try:
        r = await db.execute(text("""
            SELECT
              COUNT(*) FILTER (WHERE data_prazo < :hoje) AS vencidos,
              COUNT(*) FILTER (WHERE data_prazo BETWEEN :hoje AND :d3) AS criticos,
              COUNT(*) FILTER (WHERE data_prazo BETWEEN :hoje AND :d7) AS proximos7
            FROM deadlines
            WHERE status='pendente' AND deleted_at IS NULL
        """), {"hoje": hoje, "d3": d3, "d7": d7})
        pv, pc, p7 = r.one()
    except Exception:
        logger.warning("Dashboard: falha ao carregar prazos", exc_info=True)

    try:
        if ve_total:
            r = await db.execute(text("""
                SELECT
                  COALESCE(SUM(valor) FILTER (WHERE status='pendente'),0),
                  COALESCE(SUM(valor) FILTER (WHERE status='atrasado'),0),
                  COALESCE(SUM(valor) FILTER (WHERE status='pago'
                    AND EXTRACT(MONTH FROM data_pagamento)=EXTRACT(MONTH FROM CURRENT_DATE)
                    AND EXTRACT(YEAR FROM data_pagamento)=EXTRACT(YEAR FROM CURRENT_DATE)),0)
                FROM fees WHERE deleted_at IS NULL
            """))
            fin_escopo = "escritorio"
        else:
            r = await db.execute(text("""
                SELECT
                  COALESCE(SUM(f.valor) FILTER (WHERE f.status='pendente'),0),
                  COALESCE(SUM(f.valor) FILTER (WHERE f.status='atrasado'),0),
                  COALESCE(SUM(f.valor) FILTER (WHERE f.status='pago'
                    AND EXTRACT(MONTH FROM f.data_pagamento)=EXTRACT(MONTH FROM CURRENT_DATE)
                    AND EXTRACT(YEAR FROM f.data_pagamento)=EXTRACT(YEAR FROM CURRENT_DATE)),0)
                FROM fees f
                JOIN cases c ON c.id = f.case_id
                WHERE f.deleted_at IS NULL AND c.deleted_at IS NULL
                  AND (c.advogado_responsavel_id = :uid OR c.advogado_auxiliar_id = :uid)
            """), {"uid": cu.id})
            fin_escopo = "meus_casos"
        fin_pend, fin_atras, fin_mes = r.one()
    except Exception:
        logger.warning("Dashboard: falha ao carregar financeiro", exc_info=True)

    try:
        r = await db.execute(text("""
            SELECT COUNT(*) FROM environmental_cases
            WHERE deleted_at IS NULL
              AND status_defesa IN ('prazo_correndo','elaborando')
              AND data_prazo_defesa <= :d7
        """), {"d7": d7})
        amb_criticas = r.scalar() or 0
    except Exception:
        logger.warning("Dashboard: falha ao carregar ambiental crítico", exc_info=True)

    try:
        r = await db.execute(text("""
            SELECT COUNT(*) FROM clients
            WHERE deleted_at IS NULL AND status='ativo'
        """))
        clientes_ativos = r.scalar() or 0
    except Exception:
        logger.warning("Dashboard: falha ao carregar clientes ativos", exc_info=True)

    try:
        r = await db.execute(text("""
            SELECT COUNT(*) FROM legal_docs
            WHERE deleted_at IS NULL AND ai_generated=true
              AND human_reviewed=false AND status NOT IN ('rascunho')
        """))
        pecas_hitl = r.scalar() or 0
    except Exception:
        logger.warning("Dashboard: falha ao carregar peças HITL", exc_info=True)

    resposta = {
        "casos": {
            "por_status": casos_status,
            "por_area": casos_area,
            "total": sum(casos_status.values()),
            "encerrados": casos_status.get("encerrado", 0),
            "ativos": sum(casos_status.values()) - casos_status.get("encerrado", 0),
        },
        "prazos": {"vencidos": pv, "criticos_3d": pc, "proximos_7d": p7},
        "financeiro": {
            "pendente": float(fin_pend or 0),
            "atrasado": float(fin_atras or 0),
            "recebido_mes": float(fin_mes or 0),
            "escopo": fin_escopo,
        },
        "ambiental_criticas": amb_criticas,
        "clientes_ativos": clientes_ativos,
        "pecas_aguardando_revisao": pecas_hitl,
    }
    _cache_set(cache_key, resposta)
    return resposta


# ═══ Relatório Gerencial Mensal (PDF) ═══
from fastapi import Query as _Q, HTTPException as _HTTPExc
from fastapi.responses import Response as _R
from datetime import date as _date
from app.services.pdf_service import relatorio_mensal_pdf_async
from app.core.security import require_roles as _rr


# Coleta movida para services/dashboard_service.py (correção de camada
# domain→api). Mantido como alias para compatibilidade de imports existentes.
from app.services.dashboard_service import coletar_dados_mes as _coletar_dados_mes


@router.get("/relatorio-mensal")
async def relatorio_mensal(
    mes: int = _Q(None, ge=1, le=12),
    ano: int = _Q(None, ge=2026, le=2100),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_rr(["superadmin", "admin", "socio"])),
):
    """PDF gerencial do mês (default: mês corrente)."""
    hoje = _date.today()
    mes, ano = mes or hoje.month, ano or hoje.year
    dados = await _coletar_dados_mes(db, mes, ano)
    try:
        pdf = await relatorio_mensal_pdf_async(mes, ano, dados)
    except RuntimeError:
        logger.warning("Geração do relatório mensal em PDF indisponível", exc_info=True)
        raise _HTTPExc(status_code=503, detail="Geração de PDF indisponível no momento")
    return _R(content=pdf, media_type="application/pdf",
              headers={"Content-Disposition":
                       f'attachment; filename="relatorio_{ano}_{mes:02d}.pdf"'})
