from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_endpoint_integridade_delega_ao_servico(monkeypatch):
    from app.routers import diagnostico

    esperado = {
        "somente_leitura": True,
        "achados": [],
        "resumo": {"integro": True},
    }
    executar = AsyncMock(return_value=esperado)
    monkeypatch.setattr(
        diagnostico,
        "get_settings",
        lambda: SimpleNamespace(DIAGNOSTICO_ENABLED=True),
    )
    monkeypatch.setattr(
        diagnostico.integridade_service,
        "diagnosticar_integridade",
        executar,
    )

    db = object()
    resposta = await diagnostico.integridade_diagnostico(db=db, cu=object())

    assert resposta == esperado
    executar.assert_awaited_once_with(db)


@pytest.mark.asyncio
async def test_endpoint_integridade_respeita_feature_flag(monkeypatch):
    from app.routers import diagnostico

    monkeypatch.setattr(
        diagnostico,
        "get_settings",
        lambda: SimpleNamespace(DIAGNOSTICO_ENABLED=False),
    )

    with pytest.raises(HTTPException) as exc:
        await diagnostico.integridade_diagnostico(db=object(), cu=object())

    assert exc.value.status_code == 503
    assert "DIAGNOSTICO_ENABLED=false" in str(exc.value.detail)
