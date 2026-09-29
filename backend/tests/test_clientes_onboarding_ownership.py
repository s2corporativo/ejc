"""Regressões de RBAC/ownership e desempenho do onboarding de Clientes.

O onboarding já existia antes da auditoria, mas possuía matriz própria:
- analytics usava `_EQUIPE` (incluía auxiliar/estagiário e excluía secretaria);
- service filtrava não-admin apenas por `Client.responsavel_id`;
- o checklist executava quatro consultas por cliente, criando N+1 na visão global.

Os testes abaixo preservam a fonte canônica de ownership e impedem a volta do
carregamento cliente-a-cliente.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from app.core.client_ownership import visao_total_clientes
from app.models.client import ClientTipo
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


def test_onboarding_pendencias_carrega_fatos_em_lote():
    fonte = inspect.getsource(onboarding.pendencias)
    assert fonte.count("_carregar_fatos_em_lote(") == 1
    assert "_montar_checklist(cliente" in fonte
    assert "await _checklist" not in fonte

    fonte_lote = inspect.getsource(onboarding._carregar_fatos_em_lote)
    # Uma consulta agregada para procurações, uma para documentos e uma para
    # honorários, independentemente da quantidade de clientes carregados.
    assert fonte_lote.count("await db.execute(") == 3
    assert ".group_by(Procuracao.client_id)" in fonte_lote
    assert ".group_by(Document.client_id)" in fonte_lote
    assert ".group_by(Fee.client_id)" in fonte_lote


def test_onboarding_checklist_preserva_semantica_objetiva_sem_io():
    client = SimpleNamespace(
        id="c-1",
        tipo=ClientTipo.PJ,
        razao_social="Empresa Teste",
        nome=None,
        cnpj_enc="ciphertext",
        cpf_enc=None,
        email="contato@example.com",
        telefone=None,
        whatsapp=None,
        status=SimpleNamespace(value="ativo"),
    )
    fatos = {
        "procuracoes_ativas": 1,
        "documentos_total": 2,
        "contratos_documento": 0,
        "honorarios": 1,
    }

    checklist = onboarding._montar_checklist(client, fatos)

    assert checklist["client_id"] == "c-1"
    assert checklist["onboarding_completo"] is True
    assert checklist["percentual_completo"] == 100
    assert checklist["pendencias"] == []
    assert [item["item"] for item in checklist["itens"]] == [
        "Cadastro básico",
        "Contato (e-mail/telefone)",
        "Procuração ativa",
        "Contrato de honorários",
        "Documentos anexados",
    ]
