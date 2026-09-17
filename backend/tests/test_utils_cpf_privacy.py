"""Regressão LGPD do validador de CPF: não ecoar o identificador no payload."""

import pytest

from app.routers.utils import cpf_check


@pytest.mark.asyncio
async def test_cpf_check_nao_ecoa_cpf_no_payload() -> None:
    out = await cpf_check("00000000000", cu=None)
    assert out == {"valido": False}
    assert "cpf" not in out
