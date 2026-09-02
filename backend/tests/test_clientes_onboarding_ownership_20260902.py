"""Regressões de RBAC/ownership do onboarding de Clientes.

O onboarding já existia antes da auditoria, mas possuía matriz própria:
- analytics usava `_EQUIPE` (incluía auxiliar/estagiário e excluía secretaria);
- service filtrava não-admin apenas por `Client.responsavel_id`.

Isso divergia do domínio canônico de Clientes, no qual gestão/secretaria têm
visão total e advogado vê cliente por responsabilidade direta OU vínculo em
caso. Estes testes evitam que a implementação paralela volte.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from app.core.client_ownership import visao_total_clientes
from app.routers import analytics
from app.services import onboarding


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
    return SimpleNamespace(role=SimpleNamespace(value=role), id="u-test")


def test_analytics_onboarding_usa_allowlist_exata_de_clientes():
    assert set(analytics._CLIENTES) == {
        "superadmin", "admin", "socio", "advogado", "secretaria",
    }
    assert "advogado_auxiliar" not in analytics._CLIENTES
    assert "estagiario" not in analytics._CLIENTES
    assert "financeiro" not in analytics._CLIENTES


@pytest.mark.parametrize("role", sorted(TODOS))
def test_onboarding_visao_total_delega_ao_gate_canonico(role: str):
    user = _user(role)
    assert onboarding.pode_ver_todos(user) is visao_total_clientes(user)


def test_onboarding_pendencias_filtra_por_ids_clientes_visiveis():
    fonte = inspect.getsource(onboarding.pendencias)
    assert "visao_total_clientes(user)" in fonte
    assert "ids_clientes_visiveis(user)" in fonte
    assert "Client.id.in_(ids_clientes_visiveis(user))" in fonte
    # Regressão principal: não voltar ao filtro local que ignora vínculo por caso.
    assert "Client.responsavel_id == user.id" not in fonte


def test_onboarding_detalhe_usa_obter_cliente_autorizado():
    fonte = inspect.getsource(analytics.onboarding_cliente)
    assert "obter_cliente_autorizado(db, cu, client_id)" in fonte
    assert "client.responsavel_id" not in fonte
