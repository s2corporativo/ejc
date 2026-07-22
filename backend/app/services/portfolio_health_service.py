"""Diagnóstico agregado de casos ativos para o Dashboard operacional."""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def portfolio_health(
    db: AsyncSession,
    *,
    user_id: str,
    scope_all: bool,
    stale_days: int = 30,
    limit: int = 30,
) -> dict[str, Any]:
    """Calcula risco de carteira em uma consulta, sem N+1 por caso."""
    scope_clause = "" if scope_all else """
        AND (
            c.advogado_responsavel_id = :user_id
            OR c.advogado_auxiliar_id = :user_id
        )
    """
    query = text(
        f"""
        WITH movement_activity AS (
            SELECT case_id, MAX(COALESCE(data_evento, created_at)) AS last_at
            FROM case_movimentos GROUP BY case_id
        ),
        document_activity AS (
            SELECT case_id, MAX(created_at) AS last_at
            FROM documents
            WHERE deleted_at IS NULL AND case_id IS NOT NULL
            GROUP BY case_id
        ),
        attendance_activity AS (
            SELECT
                case_id,
                MAX(data_atendimento) AS last_at,
                COUNT(*) FILTER (
                    WHERE solicitacao_atendida = false
                      AND solicitacao_prazo IS NOT NULL
                      AND solicitacao_prazo < now()
                ) AS overdue_requests
            FROM atendimentos
            WHERE case_id IS NOT NULL
            GROUP BY case_id
        ),
        task_activity AS (
            SELECT
                case_id,
                MAX(updated_at) AS last_at,
                COUNT(*) FILTER (WHERE status::text <> 'concluida') AS pending_tasks
            FROM tasks
            WHERE deleted_at IS NULL AND case_id IS NOT NULL
            GROUP BY case_id
        ),
        deadline_risk AS (
            SELECT
                case_id,
                COUNT(*) FILTER (
                    WHERE status::text NOT IN ('concluido', 'cancelado')
                      AND data_prazo < current_date
                ) AS overdue_deadlines,
                COUNT(*) FILTER (
                    WHERE status::text NOT IN ('concluido', 'cancelado')
                      AND data_prazo BETWEEN current_date AND current_date + 3
                ) AS deadlines_next_3_days
            FROM deadlines
            WHERE deleted_at IS NULL AND case_id IS NOT NULL
            GROUP BY case_id
        ),
        process_state AS (
            SELECT
                case_id,
                COUNT(*) FILTER (WHERE status <> 'arquivado') AS active_processes
            FROM processes
            WHERE deleted_at IS NULL
            GROUP BY case_id
        ),
        document_risk AS (
            SELECT
                case_id,
                COUNT(*) FILTER (
                    WHERE ai_generated = true AND human_reviewed = false
                ) AS unreviewed_ai_documents,
                COUNT(*) FILTER (
                    WHERE status::text IN ('rascunho', 'em_revisao')
                ) AS documents_in_review
            FROM legal_docs
            WHERE deleted_at IS NULL
            GROUP BY case_id
        ),
        calculated AS (
            SELECT
                c.id,
                c.numero_interno,
                c.titulo,
                c.area::text AS area,
                c.status::text AS status,
                c.prioridade::text AS prioridade,
                c.risco,
                c.has_judicial_process,
                c.advogado_responsavel_id,
                u.full_name AS advogado_responsavel,
                GREATEST(
                    COALESCE(c.updated_at, c.created_at),
                    COALESCE(m.last_at, c.created_at),
                    COALESCE(d.last_at, c.created_at),
                    COALESCE(a.last_at, c.created_at),
                    COALESCE(t.last_at, c.created_at)
                ) AS last_activity_at,
                COALESCE(t.pending_tasks, 0)::int AS pending_tasks,
                COALESCE(dl.overdue_deadlines, 0)::int AS overdue_deadlines,
                COALESCE(dl.deadlines_next_3_days, 0)::int AS deadlines_next_3_days,
                COALESCE(a.overdue_requests, 0)::int AS overdue_client_requests,
                COALESCE(p.active_processes, 0)::int AS active_processes,
                COALESCE(ld.unreviewed_ai_documents, 0)::int AS unreviewed_ai_documents,
                COALESCE(ld.documents_in_review, 0)::int AS documents_in_review
            FROM cases c
            LEFT JOIN users u ON u.id = c.advogado_responsavel_id
            LEFT JOIN movement_activity m ON m.case_id = c.id
            LEFT JOIN document_activity d ON d.case_id = c.id
            LEFT JOIN attendance_activity a ON a.case_id = c.id
            LEFT JOIN task_activity t ON t.case_id = c.id
            LEFT JOIN deadline_risk dl ON dl.case_id = c.id
            LEFT JOIN process_state p ON p.case_id = c.id
            LEFT JOIN document_risk ld ON ld.case_id = c.id
            WHERE c.deleted_at IS NULL
              AND c.status::text NOT IN ('encerrado', 'arquivado')
              {scope_clause}
        ),
        scored AS (
            SELECT
                calculated.*,
                GREATEST(
                    0,
                    100
                    - LEAST(45, CASE WHEN overdue_deadlines > 0
                        THEN 20 + overdue_deadlines * 5 ELSE 0 END)
                    - LEAST(20, CASE WHEN deadlines_next_3_days > 0
                        THEN 5 + deadlines_next_3_days * 3 ELSE 0 END)
                    - CASE WHEN current_date - last_activity_at::date > :stale_days
                        THEN 20 ELSE 0 END
                    - CASE WHEN pending_tasks = 0 THEN 10 ELSE 0 END
                    - CASE WHEN has_judicial_process = true AND active_processes = 0
                        THEN 20 ELSE 0 END
                    - LEAST(20, CASE WHEN overdue_client_requests > 0
                        THEN 8 + overdue_client_requests * 3 ELSE 0 END)
                    - LEAST(15, CASE WHEN unreviewed_ai_documents > 0
                        THEN 5 + unreviewed_ai_documents * 2 ELSE 0 END)
                    - LEAST(8, documents_in_review)
                )::int AS health_score,
                GREATEST(0, current_date - last_activity_at::date)::int AS inactive_days
            FROM calculated
        )
        SELECT
            *,
            CASE
                WHEN health_score >= 85 THEN 'healthy'
                WHEN health_score >= 65 THEN 'attention'
                WHEN health_score >= 40 THEN 'risk'
                ELSE 'critical'
            END AS health_level
        FROM scored
        ORDER BY
            health_score ASC,
            overdue_deadlines DESC,
            deadlines_next_3_days DESC,
            last_activity_at ASC
        LIMIT :limit
        """
    )
    rows = (
        await db.execute(
            query,
            {
                "user_id": user_id,
                "stale_days": stale_days,
                "limit": limit,
            },
        )
    ).mappings().all()
    items = []
    totals = {"critical": 0, "risk": 0, "attention": 0, "healthy": 0}
    for row in rows:
        item = dict(row)
        if item.get("last_activity_at"):
            item["last_activity_at"] = item["last_activity_at"].isoformat()
        level = str(item["health_level"])
        totals[level] = totals.get(level, 0) + 1
        item["route"] = f"/casos/{item['id']}"
        items.append(item)
    return {
        "scope": "office" if scope_all else "assigned",
        "stale_days": stale_days,
        "limit": limit,
        "returned": len(items),
        "totals_in_result": totals,
        "items": items,
    }
