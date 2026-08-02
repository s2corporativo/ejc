"""Relatório mensal consolidado — endpoint GET /api/v1/relatorio/mensal?mes=YYYY-MM"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL
from app.core.status_caso import STATUS_ABERTOS
from app.models.user import User

# "Ativos" é AGREGADO dos status abertos (migration 126) — nenhum status se
# chama `ativo`. Interpolado porque a lista é constante do código, nunca
# entrada de usuário.
_ABERTOS_SQL = ",".join(f"'{s.value}'" for s in STATUS_ABERTOS)
from typing import Optional

router = APIRouter(prefix="/relatorio", tags=["Relatório"])

# Least-privilege: relatório financeiro do escritório só p/ gestão/financeiro
# (corrige _is_gestor definido-mas-nunca-usado, ampliando p/ incluir financeiro).
_GESTOR_FIN = {"superadmin", "admin", "socio", "financeiro"}


def _is_gestor(u: User) -> bool:
    return ROLE_LEVEL.get(u.role.value, 0) >= ROLE_LEVEL["socio"]


@router.get("/mensal")
async def relatorio_mensal(
    mes: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Retorna resumo financeiro + operacional do mês para relatório gerencial."""
    if cu.role.value not in _GESTOR_FIN:
        raise HTTPException(403, "Acesso restrito a gestão/financeiro")
    from datetime import date
    if not mes:
        today = date.today()
        mes = f"{today.year}-{today.month:02d}"

    ano, m = mes.split("-")
    mes_str = f"{int(m):02d}/{ano}"

    # Honorários
    hon = await db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE status NOT IN ('cancelado','pago')) AS qtd_pendentes,
            COUNT(*) FILTER (WHERE status = 'pago' AND date_trunc('month', updated_at) = date_trunc('month', CAST(:mes AS date))) AS qtd_pagos_mes,
            COALESCE(SUM(valor) FILTER (WHERE status NOT IN ('cancelado','pago')), 0) AS total_pendente,
            COALESCE(SUM(valor) FILTER (WHERE status = 'atrasado'), 0) AS total_atrasado,
            COALESCE(SUM(valor) FILTER (
                WHERE status = 'pago' AND date_trunc('month', updated_at) = date_trunc('month', CAST(:mes AS date))
            ), 0) AS recebido_mes
        FROM fees WHERE deleted_at IS NULL
    """), {"mes": date.fromisoformat(f"{mes}-01")})
    hon_data = dict(hon.mappings().first() or {})

    # Despesas
    desp = await db.execute(text("""
        SELECT
            COUNT(*) AS qtd_total,
            COUNT(*) FILTER (WHERE status = 'pago') AS qtd_pagas,
            COALESCE(SUM(valor) FILTER (WHERE status = 'pago'), 0) AS total_pago,
            COALESCE(SUM(valor) FILTER (WHERE status != 'pago'), 0) AS total_pendente,
            COALESCE(SUM(valor), 0) AS total_geral
        FROM office_expenses WHERE deleted_at IS NULL
          AND competencia = :mes
    """), {"mes": mes})
    desp_data = dict(desp.mappings().first() or {})

    # Casos
    casos = await db.execute(text(f"""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE status IN ({_ABERTOS_SQL})) AS ativos,
            COUNT(*) FILTER (WHERE status = 'encerrado' AND date_trunc('month', updated_at) = date_trunc('month', CAST(:mes AS date))) AS encerrados_mes,
            COUNT(*) FILTER (WHERE date_trunc('month', created_at) = date_trunc('month', CAST(:mes AS date))) AS novos_mes
        FROM cases WHERE deleted_at IS NULL
    """), {"mes": date.fromisoformat(f"{mes}-01")})
    casos_data = dict(casos.mappings().first() or {})

    # Prazos vencidos sem conclusão
    prazos = await db.execute(text("""
        SELECT COUNT(*) AS vencidos_abertos
        FROM deadlines WHERE deleted_at IS NULL
          AND status NOT IN ('concluido','cancelado')
          AND data_prazo < CURRENT_DATE
    """))
    prazos_data = dict(prazos.mappings().first() or {})

    # Honorários por tipo
    por_tipo = await db.execute(text("""
        SELECT tipo, COUNT(*) AS qtd, COALESCE(SUM(valor), 0) AS total
        FROM fees WHERE deleted_at IS NULL AND status NOT IN ('cancelado')
        GROUP BY tipo ORDER BY total DESC
    """))

    # Despesas por categoria
    por_cat = await db.execute(text("""
        SELECT categoria, COALESCE(SUM(valor), 0) AS total
        FROM office_expenses WHERE deleted_at IS NULL AND competencia = :mes
        GROUP BY categoria ORDER BY total DESC
    """), {"mes": mes})

    recebido = float(hon_data.get("recebido_mes") or 0)
    despesas_pagas = float(desp_data.get("total_pago") or 0)
    resultado = recebido - despesas_pagas

    return {
        "mes": mes,
        "mes_label": mes_str,
        "gerado_em": date.today().isoformat(),
        "financeiro": {
            "recebido_mes": recebido,
            "pendente": float(hon_data.get("total_pendente") or 0),
            "atrasado": float(hon_data.get("total_atrasado") or 0),
            "qtd_pendentes": int(hon_data.get("qtd_pendentes") or 0),
            "qtd_pagos_mes": int(hon_data.get("qtd_pagos_mes") or 0),
            "despesas_pagas": despesas_pagas,
            "despesas_pendentes": float(desp_data.get("total_pendente") or 0),
            "resultado_mes": resultado,
            "margem_pct": round((resultado / recebido * 100) if recebido else 0, 1),
        },
        "casos": {
            "total": int(casos_data.get("total") or 0),
            "ativos": int(casos_data.get("ativos") or 0),
            "novos_mes": int(casos_data.get("novos_mes") or 0),
            "encerrados_mes": int(casos_data.get("encerrados_mes") or 0),
        },
        "prazos": {
            "vencidos_abertos": int(prazos_data.get("vencidos_abertos") or 0),
        },
        "por_tipo_honorario": [
            {"tipo": r["tipo"], "qtd": int(r["qtd"]), "total": float(r["total"])}
            for r in por_tipo.mappings().all()
        ],
        "por_categoria_despesa": [
            {"categoria": r["categoria"], "total": float(r["total"])}
            for r in por_cat.mappings().all()
        ],
    }
