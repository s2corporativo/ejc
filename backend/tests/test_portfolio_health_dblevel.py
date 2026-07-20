"""Escopo e paridade do score agregado com Postgres real."""
from __future__ import annotations

import os
import pytest

from tests.portfolio_health_fixtures import cleanup_portfolio, portfolio_fixtures

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


async def test_portfolio_scope_and_score_match_individual_diagnosis():
    from app.core.database import AsyncSessionLocal
    from app.services.case_health_service import operational_health
    from app.services.portfolio_health_service import portfolio_health

    async with AsyncSessionLocal() as db:
        ids = await portfolio_fixtures(db)
        try:
            assigned = await portfolio_health(
                db, user_id=ids["user_a"], scope_all=False,
                stale_days=30, limit=10,
            )
            assert assigned["scope"] == "assigned"
            assert assigned["portfolio_total"] == 1
            assert [item["id"] for item in assigned["items"]] == [ids["case_a"]]

            individual = await operational_health(db, ids["case_a"], stale_days=30)
            aggregated = assigned["items"][0]
            assert aggregated["score"] == individual["score"]
            assert aggregated["level"] == individual["level"]
            assert aggregated["metrics"] == individual["metrics"]
            assert aggregated["next_recommended_action"] == individual[
                "next_recommended_action"
            ]

            office = await portfolio_health(
                db, user_id=ids["user_a"], scope_all=True,
                stale_days=30, limit=10,
            )
            assert office["scope"] == "office"
            assert office["portfolio_total"] == 2
            assert {item["id"] for item in office["items"]} == {
                ids["case_a"], ids["case_b"]
            }
            assert office["items"][0]["id"] == ids["case_a"]
        finally:
            await cleanup_portfolio(db, ids)
