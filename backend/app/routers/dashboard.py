# ── app/routers/dashboard.py ─────────────────────────────────────────────────
# Dashboard executivo — KPIs do escritório em uma chamada.
import time
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User

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
    cu: User = Depends(get_current_user),
):
    from app.core.security import ROLE_LEVEL as _RLk
    ve_total_k = _RLk.get(cu.role.value, 0) >= _RLk["admin"]
    # Escopo financeiro determina a chave de cache (sem vazar entre perfis).
    cache_key = "escritorio" if ve_total_k else f"meus_casos:{cu.id}"
    _cached = _cache_get(cache_key)
    if _cached is not None:
        return _cached

    hoje = date.today()
    d3, d7 = hoje + timedelta(days=3), hoje + timedelta(days=7)

    # Casos por status
    r = await db.execute(text("""
        SELECT status, COUNT(*) FROM cases
        WHERE deleted_at IS NULL GROUP BY status
    """))
    casos_status = {row[0]: row[1] for row in r}

    # Casos por área (BUG-06/BUG-10): MESMO conjunto das demais contagens —
    # todos os casos não-deletados, sem excluir status. Antes excluía
    # 'encerrado'/'arquivado', o que fazia áreas (ex.: trabalhista) sumirem do
    # gráfico e divergir do total do header. deleted_at IS NULL é o único filtro.
    r = await db.execute(text("""
        SELECT area, COUNT(*) FROM cases
        WHERE deleted_at IS NULL
        GROUP BY area ORDER BY COUNT(*) DESC
    """))
    casos_area = [{"area": row[0], "total": row[1]} for row in r]

    # Prazos
    r = await db.execute(text("""
        SELECT
          COUNT(*) FILTER (WHERE data_prazo < :hoje) AS vencidos,
          COUNT(*) FILTER (WHERE data_prazo BETWEEN :hoje AND :d3) AS criticos,
          COUNT(*) FILTER (WHERE data_prazo BETWEEN :hoje AND :d7) AS proximos7
        FROM deadlines
        WHERE status='pendente' AND deleted_at IS NULL
    """), {"hoje": hoje, "d3": d3, "d7": d7})
    pv, pc, p7 = r.one()

    # Financeiro — consolidado do escritório é EXCLUSIVO do admin.
    # Sócio/advogado/auxiliar recebem apenas o financeiro dos próprios casos.
    from app.core.security import ROLE_LEVEL as _RL
    ve_total = _RL.get(cu.role.value, 0) >= _RL["admin"]
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
        # Escopo: honorários vinculados a casos onde o usuário é responsável/auxiliar
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

    # Ambiental crítico
    r = await db.execute(text("""
        SELECT COUNT(*) FROM environmental_cases
        WHERE deleted_at IS NULL
          AND status_defesa IN ('prazo_correndo','elaborando')
          AND data_prazo_defesa <= :d7
    """), {"d7": d7})
    amb_criticas = r.scalar() or 0

    # Clientes ativos
    r = await db.execute(text("""
        SELECT COUNT(*) FROM clients
        WHERE deleted_at IS NULL AND status='ativo'
    """))
    clientes_ativos = r.scalar() or 0

    # Peças aguardando revisão HITL
    r = await db.execute(text("""
        SELECT COUNT(*) FROM legal_docs
        WHERE deleted_at IS NULL AND ai_generated=true
          AND human_reviewed=false AND status NOT IN ('rascunho')
    """))
    pecas_hitl = r.scalar() or 0

    resposta = {
        "casos": {
            "por_status": casos_status,
            "por_area": casos_area,
            # BUG-06/BUG-10: definição canônica única (== GET /cases/stats):
            # total não-deletado, ativos = tudo que não é 'encerrado'.
            "total": sum(casos_status.values()),
            "encerrados": casos_status.get("encerrado", 0),
            "ativos": sum(casos_status.values()) - casos_status.get("encerrado", 0),
        },
        "prazos": {"vencidos": pv, "criticos_3d": pc, "proximos_7d": p7},
        "financeiro": {
            "pendente": float(fin_pend), "atrasado": float(fin_atras),
            "recebido_mes": float(fin_mes),
            "escopo": fin_escopo,   # 'escritorio' (admin) | 'meus_casos' (demais)
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


async def _coletar_dados_mes(db, mes: int, ano: int) -> dict:
    """Coleta consolidada — reutilizada pelo endpoint e pelo scheduler."""
    r = await db.execute(text("""
        SELECT
          COUNT(*) FILTER (WHERE EXTRACT(MONTH FROM created_at)=:m
                             AND EXTRACT(YEAR  FROM created_at)=:a) AS abertos,
          COUNT(*) FILTER (WHERE EXTRACT(MONTH FROM data_encerramento)=:m
                             AND EXTRACT(YEAR  FROM data_encerramento)=:a) AS encerrados
        FROM cases WHERE deleted_at IS NULL
    """), {"m": mes, "a": ano})
    abertos, encerrados = r.one()

    r = await db.execute(text("""
        SELECT
          COUNT(*) FILTER (WHERE status='concluido'
                             AND EXTRACT(MONTH FROM data_conclusao)=:m
                             AND EXTRACT(YEAR  FROM data_conclusao)=:a) AS cumpridos,
          COUNT(*) FILTER (WHERE status='pendente' AND data_prazo < CURRENT_DATE) AS vencidos
        FROM deadlines WHERE deleted_at IS NULL
    """), {"m": mes, "a": ano})
    cumpridos, vencidos = r.one()

    r = await db.execute(text("""
        SELECT
          COALESCE(SUM(valor) FILTER (WHERE status='pago'
            AND EXTRACT(MONTH FROM data_pagamento)=:m
            AND EXTRACT(YEAR FROM data_pagamento)=:a),0),
          COALESCE(SUM(valor) FILTER (WHERE status='pendente'),0),
          COALESCE(SUM(valor) FILTER (WHERE status='atrasado'),0)
        FROM fees WHERE deleted_at IS NULL
    """), {"m": mes, "a": ano})
    recebido, pendente, atrasado = r.one()

    r = await db.execute(text("""
        SELECT u.full_name,
          COUNT(DISTINCT c.id) FILTER (WHERE c.status IN ('ativo','triagem')) AS casos,
          COUNT(DISTINCT d.id) FILTER (WHERE EXTRACT(MONTH FROM d.data_prazo)=:m
                                         AND EXTRACT(YEAR FROM d.data_prazo)=:a) AS prazos,
          COUNT(DISTINCT d.id) FILTER (WHERE d.status='concluido'
                                         AND EXTRACT(MONTH FROM d.data_conclusao)=:m
                                         AND EXTRACT(YEAR FROM d.data_conclusao)=:a) AS cumpridos
        FROM users u
        LEFT JOIN cases c ON c.advogado_responsavel_id=u.id AND c.deleted_at IS NULL
        LEFT JOIN deadlines d ON d.responsavel_id=u.id AND d.deleted_at IS NULL
        WHERE u.role IN ('socio','advogado','advogado_auxiliar')
          AND u.is_active=true AND u.deleted_at IS NULL
        GROUP BY u.full_name ORDER BY u.full_name
    """), {"m": mes, "a": ano})
    advogados = [{"nome": x[0], "casos": x[1], "prazos": x[2], "cumpridos": x[3]}
                 for x in r]

    r = await db.execute(text("""
        SELECT area, COUNT(*) FROM cases
        WHERE deleted_at IS NULL AND status NOT IN ('encerrado','arquivado')
        GROUP BY area ORDER BY COUNT(*) DESC
    """))
    por_area = [{"area": x[0], "total": x[1]} for x in r]

    r = await db.execute(text("""
        SELECT COUNT(*) FROM legal_docs
        WHERE deleted_at IS NULL AND ai_generated=true AND human_reviewed=false
    """))
    pecas_hitl = r.scalar() or 0

    return {
        "casos_abertos": abertos, "casos_encerrados": encerrados,
        "prazos_cumpridos": cumpridos, "prazos_vencidos": vencidos,
        "fin_recebido": float(recebido), "fin_pendente": float(pendente),
        "fin_atrasado": float(atrasado),
        "advogados": advogados, "por_area": por_area,
        "pecas_hitl": pecas_hitl,
    }


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
    except RuntimeError as e:
        raise _HTTPExc(status_code=503, detail=str(e))
    return _R(content=pdf, media_type="application/pdf",
              headers={"Content-Disposition":
                       f'attachment; filename="relatorio_{ano}_{mes:02d}.pdf"'})
