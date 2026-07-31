"""Regressão dos erros de autorização da gestão societária."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Awaitable, Callable

import pytest
from fastapi import HTTPException

from app.routers.gestao_societaria import (
    aprovar_distribuicao,
    atualizar_socio,
    calcular_distribuicao,
    listar_distribuicoes,
)


def _user(role: str):
    return SimpleNamespace(id=f"user-{role}", role=SimpleNamespace(value=role))


CallFactory = Callable[[object], Awaitable[object]]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("call", "role", "detail"),
    [
        (
            lambda user: atualizar_socio(
                "socio-1",
                None,
                db=None,
                cu=user,
            ),
            "advogado",
            "Acesso restrito a sócios",
        ),
        (
            lambda user: calcular_distribuicao(
                None,
                db=None,
                cu=user,
            ),
            "advogado",
            "Acesso restrito a sócios",
        ),
        (
            lambda user: listar_distribuicoes(
                page=1,
                per_page=12,
                db=None,
                cu=user,
            ),
            "advogado",
            "Acesso restrito a sócios",
        ),
        (
            lambda user: aprovar_distribuicao(
                "dist-1",
                db=None,
                cu=user,
            ),
            "socio",
            "Apenas administradores podem aprovar distribuições",
        ),
    ],
)
async def test_erros_403_explicam_o_perfil_necessario(
    call: CallFactory,
    role: str,
    detail: str,
):
    with pytest.raises(HTTPException) as exc:
        await call(_user(role))

    assert exc.value.status_code == 403
    assert exc.value.detail == detail
