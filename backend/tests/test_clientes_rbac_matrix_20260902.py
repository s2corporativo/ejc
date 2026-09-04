"""Matriz RBAC explícita do módulo Clientes.

Trava os papéis de entrada do CRUD/consulta e do relatório financeiro sem
substituir os gates row-level/ownership, que possuem testes DB-level próprios.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers.clients import _req_clientes, _req_clientes_leitura
from app.routers.relatorio_cliente import _req_fin_adv


TODOS = {
    "superadmin",
    "admin",
    "socio",
    "advogado",
    "advogado_auxiliar",
    "financeiro",
    "estagiario",
    "secretaria",
    "cliente_externo",
}


def _user(role: str):
    return SimpleNamespace(role=SimpleNamespace(value=role))


@pytest.mark.parametrize("role", sorted(TODOS))
def test_crud_clientes_allowlist_exata(role: str):
    permitidos = {"superadmin", "admin", "socio", "advogado", "secretaria"}
    if role in permitidos:
        assert _req_clientes(_user(role)).role.value == role
    else:
        with pytest.raises(HTTPException) as exc:
            _req_clientes(_user(role))
        assert exc.value.status_code == 403


@pytest.mark.parametrize("role", sorted(TODOS))
def test_leitura_clientes_allowlist_exata(role: str):
    permitidos = {"superadmin", "admin", "socio", "advogado", "secretaria"}
    if role in permitidos:
        assert _req_clientes_leitura(_user(role)).role.value == role
    else:
        with pytest.raises(HTTPException) as exc:
            _req_clientes_leitura(_user(role))
        assert exc.value.status_code == 403


@pytest.mark.parametrize("role", sorted(TODOS))
def test_relatorio_financeiro_allowlist_exata(role: str):
    permitidos = {
        "superadmin", "admin", "socio", "advogado", "secretaria", "financeiro",
    }
    if role in permitidos:
        assert _req_fin_adv(_user(role)).role.value == role
    else:
        with pytest.raises(HTTPException) as exc:
            _req_fin_adv(_user(role))
        assert exc.value.status_code == 403
