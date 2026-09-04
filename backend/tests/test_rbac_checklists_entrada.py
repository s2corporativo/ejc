"""Regressões de RBAC para Checklists e Entrada Universal (Issue #694)."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.user import UserRole
from app.routers import checklists, entrada_universal


def _u(role: UserRole):
    return SimpleNamespace(role=role)


@pytest.mark.parametrize(
    "role",
    [
        UserRole.superadmin,
        UserRole.admin,
        UserRole.socio,
        UserRole.advogado,
        UserRole.advogado_auxiliar,
        UserRole.estagiario,
    ],
)
def test_checklists_preserva_equipe_juridica(role):
    assert checklists._pode_editar(_u(role)) is True


@pytest.mark.parametrize(
    "role",
    [UserRole.financeiro, UserRole.secretaria, UserRole.cliente_externo],
)
def test_checklists_barra_papeis_fora_da_equipe(role):
    assert checklists._pode_editar(_u(role)) is False


def test_entrada_universal_meta_barra_financeiro_e_preserva_estagiario():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(entrada_universal.meta(cu=_u(UserRole.financeiro)))
    assert exc.value.status_code == 403

    resposta = asyncio.run(entrada_universal.meta(cu=_u(UserRole.estagiario)))
    assert resposta["multiplos_arquivos"] is True


def test_entrada_universal_processar_barra_financeiro_antes_de_validar_payload():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            entrada_universal.processar(
                files=[],
                texto="",
                db=None,
                cu=_u(UserRole.financeiro),
            )
        )
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException) as exc_legal:
        asyncio.run(
            entrada_universal.processar(
                files=[],
                texto="",
                db=None,
                cu=_u(UserRole.estagiario),
            )
        )
    assert exc_legal.value.status_code == 422
