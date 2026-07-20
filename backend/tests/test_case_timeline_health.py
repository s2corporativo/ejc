from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from app.services.case_activity_utils import bounded, event
from app.services.case_health_rules import assess_operational_health


def _metrics(**overrides: int) -> dict[str, int]:
    base = {
        "active_processes": 1,
        "actionable_tasks": 1,
        "overdue_deadlines": 0,
        "deadlines_next_3_days": 0,
        "overdue_client_requests": 0,
        "unreviewed_ai_documents": 0,
        "documents_in_review": 0,
    }
    base.update(overrides)
    return base


def test_bounded_only_marks_real_overflow():
    assert bounded([1, 2], 2) == ([1, 2], False)
    assert bounded([1, 2, 3], 2) == ([1, 2], True)


def test_event_normalizes_date_and_keeps_sort_key_internal():
    item = event(
        event_id="1",
        kind="deadline",
        title="Prazo",
        occurred_at=date(2026, 7, 19),
        source="deadlines",
    )
    assert item["occurred_at"] == "2026-07-19T00:00:00+00:00"
    assert item["_sort_at"] == datetime(2026, 7, 19, tzinfo=timezone.utc)


def test_health_prioritizes_overdue_deadline_and_missing_process():
    result = assess_operational_health(
        case_status="ativo",
        has_judicial_process=True,
        inactive_days=45,
        stale_days=30,
        metrics=_metrics(
            active_processes=0,
            actionable_tasks=0,
            overdue_deadlines=2,
        ),
    )
    codes = [item["code"] for item in result["indicators"]]
    assert codes[0] == "OVERDUE_DEADLINES"
    assert "CASE_INACTIVE" in codes
    assert "NO_ACTIONABLE_TASK" in codes
    assert "MISSING_ACTIVE_PROCESS" in codes
    assert result["level"] in {"risk", "critical"}
    assert result["next_recommended_action"] == result["indicators"][0][
        "recommended_action"
    ]


def test_closed_case_does_not_generate_inactivity_or_next_task_warning():
    result = assess_operational_health(
        case_status="encerrado",
        has_judicial_process=True,
        inactive_days=900,
        stale_days=30,
        metrics=_metrics(active_processes=0, actionable_tasks=0),
    )
    codes = {item["code"] for item in result["indicators"]}
    assert "CASE_INACTIVE" not in codes
    assert "NO_ACTIONABLE_TASK" not in codes
    assert "MISSING_ACTIVE_PROCESS" not in codes
    assert result["score"] == 100


def test_timeline_uses_physical_filename_and_limit_plus_one():
    root = Path(__file__).parents[1] / "app/services"
    core = (root / "case_timeline_sources_core.py").read_text(encoding="utf-8")
    assert "description=row.filename" in core
    assert "row.nome_arquivo" not in core
    assert ".limit(limit + 1)" in core


def test_routes_apply_ownership_before_service_call():
    source = (
        Path(__file__).parents[1] / "app/routers/case_timeline.py"
    ).read_text(encoding="utf-8")
    assert source.count("await verificar_acesso_caso") == 2
    assert '@router.get("/timeline")' in source
    assert '@router.get("/operational-health")' in source
