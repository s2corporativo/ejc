"""Relatório mensal consolidado — GET /api/relatorio/mensal?mes=YYYY-MM.

Honorários recebidos usam exclusivamente o subledger canônico ``fee_payments``;
saídas de caixa usam ``office_expenses.pago_em`` e competência permanece separada.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.status_caso import STATUS_ABERTOS
from app.models.user import User
from app.services.fee_ledger import LEDGER_CTES
from app.services.finance_monthly_package import gerar_pacote_financeiro_mensal

_ABERTOS_SQL = ",".join(f"'{s.value}'" for s in STATUS_ABERTOS)
router = APIRouter(prefix="/relatorio", tags=["Relatório"])
_GESTOR_FIN = {"superadmin", "admin", "socio", "financeiro"}


@router.get("/mensal")
async def relatorio_mensal(
    mes: Optional[str] = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Resumo gerencial mensal com caixa real e compatibilidade histórica explícita."""
    if cu.role.value not in _GESTOR_FIN:
        raise HTTPException(403, "Acesso restrito a gestão/financeiro")
    if not mes:
        today = date.today()
        mes = f"{today.year}-{today.month:02d}"

    ano, m = mes.split("-")
    mes_str = f"{int(m):02d}/{ano}"
    mes_ref = date.fromisoformat(f"{mes}-01")

    hon = await db.execute(
        # SQL literal com bind params; a regra marca todo text(), sem olhar
        # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        text(
            f"""
            WITH {LEDGER_CTES},
            saldos AS (
                SELECT
                    f.id,
                    CAST(f.status AS text) AS status,
                    GREATEST(
                        COALESCE(f.valor, 0) - COALESCE(pe.total_pago, 0),
                        0
                    ) AS saldo
                FROM fees f
                LEFT JOIN pagamentos_efetivos pe ON pe.fee_id = f.id
                WHERE f.deleted_at IS NULL
            ),
            recebimentos_mes AS (
                SELECT fee_id, valor
                FROM recebimentos_efetivos
                WHERE date_trunc('month', data_pagamento)
                      = date_trunc('month', CAST(:mes AS date))
            )
            SELECT
                COUNT(*) FILTER (
                    WHERE status IN ('pendente','atrasado') AND saldo > 0
                ) AS qtd_pendentes,
                (SELECT COUNT(DISTINCT fee_id) FROM recebimentos_mes) AS qtd_recebidos_mes,
                COALESCE(SUM(saldo) FILTER (
                    WHERE status IN ('pendente','atrasado')
                ), 0) AS total_pendente,
                COALESCE(SUM(saldo) FILTER (WHERE status='atrasado'), 0) AS total_atrasado,
                (SELECT COALESCE(SUM(valor), 0) FROM recebimentos_mes) AS recebido_mes
            FROM saldos
            """
        ),
        {"mes": mes_ref},
    )
    hon_data = dict(hon.mappings().first() or {})

    # Obrigações da competência selecionada.
    desp = await db.execute(
        text(
            """
            SELECT
                COUNT(*) FILTER (WHERE status != 'cancelado') AS qtd_total,
                COUNT(*) FILTER (WHERE status = 'pago') AS qtd_pagas,
                COALESCE(SUM(valor) FILTER (WHERE status = 'pago'), 0) AS total_pago_competencia,
                COALESCE(SUM(valor) FILTER (WHERE status = 'pendente'), 0) AS total_pendente,
                COALESCE(SUM(valor) FILTER (WHERE status != 'cancelado'), 0) AS total_geral
            FROM office_expenses
            WHERE deleted_at IS NULL AND competencia = :mes
            """
        ),
        {"mes": mes},
    )
    desp_data = dict(desp.mappings().first() or {})

    # Caixa real: baixa pertence ao mês de pago_em, ainda que a competência seja outra.
    saidas_caixa = await db.execute(
        text(
            """
            SELECT COALESCE(SUM(valor), 0)
            FROM office_expenses
            WHERE deleted_at IS NULL
              AND status = 'pago'
              AND pago_em IS NOT NULL
              AND date_trunc('month', pago_em)
                  = date_trunc('month', CAST(:mes AS date))
            """
        ),
        {"mes": mes_ref},
    )

    casos = await db.execute(
        # SQL literal com bind params; a regra marca todo text(), sem olhar
        # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        text(
            f"""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status IN ({_ABERTOS_SQL})) AS ativos,
                COUNT(*) FILTER (
                    WHERE status = 'encerrado'
                      AND date_trunc('month', updated_at)
                          = date_trunc('month', CAST(:mes AS date))
                ) AS encerrados_mes,
                COUNT(*) FILTER (
                    WHERE date_trunc('month', created_at)
                          = date_trunc('month', CAST(:mes AS date))
                ) AS novos_mes
            FROM cases WHERE deleted_at IS NULL
            """
        ),
        {"mes": mes_ref},
    )
    casos_data = dict(casos.mappings().first() or {})

    prazos = await db.execute(
        text(
            """
            SELECT COUNT(*) AS vencidos_abertos
            FROM deadlines
            WHERE deleted_at IS NULL
              AND status NOT IN ('concluido','cancelado')
              AND data_prazo < CURRENT_DATE
            """
        )
    )
    prazos_data = dict(prazos.mappings().first() or {})

    por_tipo = await db.execute(
        # SQL literal com bind params; a regra marca todo text(), sem olhar
        # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
        text(
            f"""
            WITH {LEDGER_CTES}
            SELECT CAST(f.tipo AS text) AS tipo,
                   COUNT(DISTINCT re.fee_id) AS qtd,
                   COALESCE(SUM(re.valor), 0) AS total
            FROM recebimentos_efetivos re
            JOIN fees f ON f.id = re.fee_id
            WHERE date_trunc('month', re.data_pagamento)
                  = date_trunc('month', CAST(:mes AS date))
            GROUP BY CAST(f.tipo AS text)
            ORDER BY total DESC
            """
        ),
        {"mes": mes_ref},
    )

    por_cat = await db.execute(
        text(
            """
            SELECT categoria, COALESCE(SUM(valor), 0) AS total
            FROM office_expenses
            WHERE deleted_at IS NULL
              AND status != 'cancelado'
              AND competencia = :mes
            GROUP BY categoria ORDER BY total DESC
            """
        ),
        {"mes": mes},
    )

    recebido = float(hon_data.get("recebido_mes") or 0)
    despesas_pagas_caixa = float(saidas_caixa.scalar() or 0)
    despesas_pagas_competencia = float(desp_data.get("total_pago_competencia") or 0)
    resultado = recebido - despesas_pagas_caixa

    return {
        "mes": mes,
        "mes_label": mes_str,
        "gerado_em": date.today().isoformat(),
        "natureza": "gerencial_nao_contabil",
        "financeiro": {
            "recebido_mes": recebido,
            "pendente": float(hon_data.get("total_pendente") or 0),
            "atrasado": float(hon_data.get("total_atrasado") or 0),
            "qtd_pendentes": int(hon_data.get("qtd_pendentes") or 0),
            "qtd_recebidos_mes": int(hon_data.get("qtd_recebidos_mes") or 0),
            "qtd_pagos_mes": int(hon_data.get("qtd_recebidos_mes") or 0),
            "despesas_pagas": despesas_pagas_caixa,
            "despesas_pagas_competencia": despesas_pagas_competencia,
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
            {
                "tipo": r["tipo"],
                "qtd": int(r["qtd"]),
                "total": float(r["total"]),
            }
            for r in por_tipo.mappings().all()
        ],
        "por_categoria_despesa": [
            {"categoria": r["categoria"], "total": float(r["total"])}
            for r in por_cat.mappings().all()
        ],
        "aviso": (
            "Relatório gerencial do EJC. Entradas e saídas de caixa derivam de "
            "pagamentos e baixas efetivamente registrados no ledger canônico. Não "
            "substitui escrituração ou validação contábil."
        ),
    }


@router.get("/mensal/{mes}/pacote")
async def pacote_financeiro_mensal(
    mes: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Baixa o dossiê mensal único: PDF + JSON + CSVs + trilha de auditoria."""
    if cu.role.value not in _GESTOR_FIN:
        raise HTTPException(403, "Acesso restrito a gestão/financeiro")
    import re
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", mes):
        raise HTTPException(422, "mes inválido: use AAAA-MM")
    resumo = await relatorio_mensal(mes=mes, db=db, cu=cu)
    conteudo = await gerar_pacote_financeiro_mensal(db, mes, resumo)
    return Response(
        content=conteudo,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="financeiro-{mes}.zip"',
            "Cache-Control": "no-store",
        },
    )
