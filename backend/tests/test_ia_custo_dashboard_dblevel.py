"""Governança de custo de IA — o painel expõe o bloco `custo` (ROW-LEVEL).

O custo já era rastreado por chamada (AILog.custo_estimado); esta melhoria dá
VISIBILIDADE no painel de Governança da IA. O teste chama o handler real do
dashboard contra Postgres e confirma o contrato do novo bloco `custo` (total,
projeção, tokens, por-modelo, alerta de orçamento).

Mesmo gate de CI dos demais *_dblevel.py (RUN_DB_TESTS=1). Sem Postgres, pula.
Usa engine dedicado com NullPool (descartado) para não contaminar o pool async
compartilhado.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def test_dashboard_governanca_expoe_bloco_custo():
    from app.core.config import get_settings
    from app.models.user import User, UserRole
    from app.routers.ia_governanca import dashboard_governanca

    engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as db:
            # _require_admin_socio só olha o role; o handler não usa cu.id nas
            # leituras, então não precisa existir no banco.
            cu = User(id="gov-custo-test", role=UserRole.socio)
            resp = await dashboard_governanca(dias=30, db=db, cu=cu)

            assert "custo" in resp
            c = resp["custo"]
            # Contrato do bloco de custo (robusto a haver ou não chamadas no período).
            assert isinstance(c["total_brl"], (int, float))
            assert isinstance(c["projecao_mensal_brl"], (int, float))
            assert isinstance(c["tokens_input"], int)
            assert isinstance(c["tokens_output"], int)
            assert isinstance(c["por_modelo"], list)
            for linha in c["por_modelo"]:
                assert {"modelo", "chamadas", "custo_brl"} <= set(linha)
            # Sem AI_BUDGET_ALERTA_BRL (default 0) → sem alerta.
            assert c["acima_do_alerta"] is False
            assert c["orcamento_alerta_brl"] is None
    finally:
        await engine.dispose()
