from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_portfolio_health_uses_one_query_and_shared_score_rules():
    source = (ROOT / "app/services/portfolio_health_service.py").read_text(
        encoding="utf-8"
    )
    assert "WITH movement_activity AS" in source
    assert "deadline_risk AS" in source
    assert "process_state AS" in source
    assert "legal_doc_state AS" in source
    assert source.count("await db.execute") == 1
    assert "assess_operational_health(" in source
    assert "WHEN health_score" not in source


def test_portfolio_health_matches_individual_activity_sources():
    portfolio = (ROOT / "app/services/portfolio_health_service.py").read_text(
        encoding="utf-8"
    )
    individual = (ROOT / "app/services/case_health_service.py").read_text(
        encoding="utf-8"
    )
    assert "MAX(COALESCE(data_evento, created_at)) AS last_at" in portfolio
    assert "CaseMovimento.data_evento" in individual
    assert "CaseMovimento.created_at" in individual
    assert "func.coalesce" in individual
    assert "MAX(COALESCE(updated_at, created_at)) AS last_at" in portfolio
    assert "COALESCE(p.last_at, c.created_at)" in portfolio
    assert "COALESCE(ld.last_at, c.created_at)" in portfolio
    assert "status::text IN ('a_fazer', 'fazendo')" in portfolio
    assert "TaskStatus.a_fazer" in individual
    assert "TaskStatus.fazendo" in individual


def test_portfolio_health_preserves_assignment_scope_without_sql_injection():
    source = (ROOT / "app/services/portfolio_health_service.py").read_text(
        encoding="utf-8"
    )
    assert "c.advogado_responsavel_id = :user_id" in source
    assert "c.advogado_auxiliar_id = :user_id" in source
    assert "CAST(:scope_all AS boolean)" in source
    assert "scope_clause" not in source
    assert '"scope": "office" if scope_all else "assigned"' in source


def test_dashboard_endpoint_has_explicit_allowed_roles():
    source = (ROOT / "app/routers/dashboard_operational.py").read_text(
        encoding="utf-8"
    )
    assert '"financeiro"' not in source
    assert '"cliente_externo"' not in source
    assert '"secretaria"' in source
    assert '"socio"' in source
    assert '@router.get("/operational-health")' in source


def test_dashboard_router_includes_operational_subrouter_once():
    source = (ROOT / "app/routers/__init__.py").read_text(encoding="utf-8")
    assert source.count(
        "dashboard.router.include_router(dashboard_operational.router)"
    ) == 1
