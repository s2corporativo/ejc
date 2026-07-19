from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_portfolio_health_uses_single_aggregated_query():
    source = (ROOT / "app/services/portfolio_health_service.py").read_text(
        encoding="utf-8"
    )
    assert "WITH movement_activity AS" in source
    assert "deadline_risk AS" in source
    assert "process_state AS" in source
    assert "document_risk AS" in source
    assert source.count("await db.execute") == 1
    assert "for case" not in source.lower()


def test_portfolio_health_preserves_assignment_scope():
    source = (ROOT / "app/services/portfolio_health_service.py").read_text(
        encoding="utf-8"
    )
    assert "c.advogado_responsavel_id = :user_id" in source
    assert "c.advogado_auxiliar_id = :user_id" in source
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
