"""Saúde agregada dos casos ativos para o Dashboard operacional."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.case_activity_utils import enum_value
from app.services.case_health_rules import assess_operational_health


async def portfolio_health(
    db: AsyncSession,
    *,
    user_id: str,
    scope_all: bool,
    stale_days: int = 30,
    limit: int = 30,
) -> dict[str, Any]:
    """Calcula a carteira em uma única consulta, sem N+1 por caso.

    A CTE coleta apenas fatos e métricas. Score, nível e indicadores usam a
    mesma função pura do diagnóstico individual, eliminando fórmulas paralelas.
    """
    query = text(
        """
        WITH movement_activity AS (
            SELECT case_id, MAX(COALESCE(data_evento, created_at)) AS last_at
            FROM case_movimentos GROUP BY case_id
        ),
        document_activity AS (
            SELECT case_id, MAX(COALESCE(updated_at, created_at)) AS last_at
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
                MAX(COALESCE(updated_at, created_at)) AS last_at,
                COUNT(*) FILTER (
                    WHERE status::text IN ('a_fazer', 'fazendo')
                ) AS actionable_tasks
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
                MAX(COALESCE(updated_at, created_at)) AS last_at,
                COUNT(*) FILTER (WHERE status <> 'arquivado') AS active_processes
            FROM processes
            WHERE deleted_at IS NULL
            GROUP BY case_id
        ),
        legal_doc_state AS (
            SELECT
                case_id,
                MAX(COALESCE(updated_at, created_at)) AS last_at,
                COUNT(*) FILTER (
                    WHERE ai_generated = true AND human_reviewed = false
                ) AS unreviewed_ai_documents,
                COUNT(*) FILTER (
                    WHERE status::text IN ('rascunho', 'em_revisao')
                ) AS documents_in_review
            FROM legal_docs
            WHERE deleted_at IS NULL AND case_id IS NOT NULL
            GROUP BY case_id
        )
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
                COALESCE(t.last_at, c.created_at),
                COALESCE(p.last_at, c.created_at),
                COALESCE(ld.last_at, c.created_at)
            ) AS last_activity_at,
            COALESCE(t.actionable_tasks, 0)::int AS actionable_tasks,
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
        LEFT JOIN legal_doc_state ld ON ld.case_id = c.id
        WHERE c.deleted_at IS NULL
          AND c.status::text NOT IN ('encerrado', 'arquivado')
          AND (
              CAST(:scope_all AS boolean) = true
              OR c.advogado_responsavel_id = :user_id
              OR c.advogado_auxiliar_id = :user_id
          )
        """
    )
    rows = (
        await db.execute(
            query,
            {"user_id": user_id, "scope_all": scope_all},
        )
    ).mappings().all()

    now = datetime.now(timezone.utc)
    all_items: list[dict[str, Any]] = []
    totals = {"critical": 0, "risk": 0, "attention": 0, "healthy": 0}
    for row in rows:
        item = dict(row)
        last_activity = item.get("last_activity_at")
        if last_activity is not None and last_activity.tzinfo is None:
            last_activity = last_activity.replace(tzinfo=timezone.utc)
        inactive_days = max(0, (now - last_activity).days) if last_activity else 0
        metrics = {
            "active_processes": int(item.pop("active_processes") or 0),
            "actionable_tasks": int(item.pop("actionable_tasks") or 0),
            "overdue_deadlines": int(item.pop("overdue_deadlines") or 0),
            "deadlines_next_3_days": int(item.pop("deadlines_next_3_days") or 0),
            "overdue_client_requests": int(
                item.pop("overdue_client_requests") or 0
            ),
            "unreviewed_ai_documents": int(
                item.pop("unreviewed_ai_documents") or 0
            ),
            "documents_in_review": int(item.pop("documents_in_review") or 0),
        }
        assessment = assess_operational_health(
            case_status=str(enum_value(item["status"])),
            has_judicial_process=bool(item["has_judicial_process"]),
            inactive_days=inactive_days,
            stale_days=stale_days,
            metrics=metrics,
        )
        level = assessment["level"]
        totals[level] = totals.get(level, 0) + 1
        all_items.append(
            {
                **item,
                **assessment,
                "metrics": metrics,
                "inactive_days": inactive_days,
                "last_activity_at": (
                    last_activity.isoformat() if last_activity else None
                ),
                "route": f"/casos/{item['id']}",
            }
        )

    all_items.sort(
        key=lambda item: (
            item["score"],
            -item["metrics"]["overdue_deadlines"],
            -item["metrics"]["deadlines_next_3_days"],
            -item["inactive_days"],
            item.get("titulo") or "",
        )
    )
    selected = all_items[:limit]
    return {
        "scope": "office" if scope_all else "assigned",
        "stale_days": stale_days,
        "limit": limit,
        "portfolio_total": len(all_items),
        "returned": len(selected),
        "totals": totals,
        "has_more": len(all_items) > limit,
        "items": selected,
    }
