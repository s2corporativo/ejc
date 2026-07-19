from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from app.services.case_timeline_service import _datetime, _event, _indicator


ROOT = Path(__file__).parents[1]


def test_event_has_stable_normalized_contract():
    item = _event(
        event_id="abc",
        kind="task",
        title="Revisar peça",
        description="Conferir pedidos",
        occurred_at=date(2026, 7, 19),
        status="pendente",
        source="tasks",
        metadata={"prioridade": "alta"},
    )
    assert item["id"] == "tasks:abc"
    assert item["occurred_at"] == "2026-07-19T00:00:00+00:00"
    assert item["metadata"] == {"prioridade": "alta"}
    assert item["_sort_at"].tzinfo is not None


def test_datetime_normalizes_naive_values_to_utc():
    result = _datetime(datetime(2026, 7, 19, 10, 30))
    assert result.tzinfo == timezone.utc


def test_indicator_contract_is_actionable():
    item = _indicator(
        "OVERDUE_DEADLINES",
        "critical",
        "Há prazos vencidos.",
        "Regularizar imediatamente.",
        count=2,
    )
    assert item["code"] == "OVERDUE_DEADLINES"
    assert item["recommended_action"]
    assert item["count"] == 2


def test_timeline_uses_existing_domain_tables_only():
    source = (ROOT / "app/services/case_timeline_service.py").read_text(
        encoding="utf-8"
    )
    for model in [
        "CaseMovimento",
        "Process",
        "Document",
        "Deadline",
        "Task",
        "Atendimento",
        "LegalDoc",
    ]:
        assert f"select({model})" in source
    assert "CREATE TABLE" not in source.upper()
    assert "INSERT INTO" not in source.upper()


def test_operational_health_has_explicit_risk_criteria():
    source = (ROOT / "app/services/case_timeline_service.py").read_text(
        encoding="utf-8"
    )
    for code in [
        "OVERDUE_DEADLINES",
        "DEADLINES_NEXT_3_DAYS",
        "CASE_INACTIVE",
        "NO_PENDING_TASK",
        "MISSING_ACTIVE_PROCESS",
        "CLIENT_REQUEST_OVERDUE",
        "AI_DOCUMENTS_UNREVIEWED",
        "DOCUMENTS_IN_REVIEW",
    ]:
        assert code in source
    assert 'level = "healthy"' in source
    assert 'level = "critical"' in source


def test_router_enforces_case_ownership_and_canonical_paths():
    source = (ROOT / "app/routers/case_timeline.py").read_text(encoding="utf-8")
    assert 'router = APIRouter(prefix="/{case_id}"' in source
    assert '@router.get("/timeline")' in source
    assert '@router.get("/operational-health")' in source
    assert source.count("await verificar_acesso_caso(db, cu, case_id)") == 2


def test_router_is_attached_to_cases_once():
    source = (ROOT / "app/routers/__init__.py").read_text(encoding="utf-8")
    assert source.count("cases.router.include_router(case_timeline.router)") == 1


def test_document_semantic_alias_does_not_duplicate_persistence():
    source = (ROOT / "app/models/document.py").read_text(encoding="utf-8")
    assert "def nome_arquivo" in source
    assert "return self.filename" in source
    assert 'Column(String(255), nullable=False)' in source
    assert "nome_arquivo = Column" not in source
