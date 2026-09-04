"""`GET /pecas/meta` declara as capacidades que estão atrás de flag.

POR QUE: até 04/09/2026 o frontend não tinha como saber que
`PECAS_DEMONSTRATIVO_CALCULADORA_ENABLED` estava desligada (default OFF, por
não homologação das regras de cálculo). O botão "Gerar demonstrativo" ficava
HABILITADO em toda calculadora homologada e o advogado só descobria a trava no
403 — depois de montar o cálculo inteiro. Botão que só falha ao clicar é
exatamente o defeito que este contrato existe para impedir.

O que se trava aqui é o CONTRATO (a chave existe e espelha a flag), nunca o
VALOR da flag: ligá-la é decisão jurídica do escritório, não do código.

Mesma abordagem do vizinho `test_pecas_meta_endpoint.py`: app mínimo com o
router real e `get_current_user` substituído. `/meta` é catálogo puro, sem DB.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import get_current_user
from app.models.user import UserRole
from app.routers import peca_geracao as peca_router


class _FakeUser:
    def __init__(self, role: UserRole):
        self.id = "u-teste"
        self.role = role
        self.full_name = "Fulano Teste"


def _montar(role: UserRole = UserRole.advogado):
    app = FastAPI()
    app.include_router(peca_router.router)
    app.dependency_overrides[get_current_user] = lambda: _FakeUser(role)
    return TestClient(app)


def _meta(client):
    r = client.get("/pecas/meta")
    assert r.status_code == 200, r.text
    return r.json()


def test_meta_declara_bloco_de_capacidades():
    corpo = _meta(_montar())
    assert "capacidades" in corpo, (
        "sem este bloco o frontend volta a entregar botão que só falha ao clicar"
    )
    assert isinstance(corpo["capacidades"], dict)
    assert isinstance(corpo["capacidades"].get("demonstrativo_calculadora"), bool)


@pytest.mark.parametrize("ligada", [True, False])
def test_capacidade_espelha_a_flag(monkeypatch, ligada):
    """Espelho fiel nos DOIS sentidos — não é constante disfarçada de capacidade."""
    monkeypatch.setattr(
        get_settings(), "PECAS_DEMONSTRATIVO_CALCULADORA_ENABLED", ligada,
        raising=False,
    )
    corpo = _meta(_montar())
    assert corpo["capacidades"]["demonstrativo_calculadora"] is ligada


def test_capacidade_lida_por_chamada_e_nao_no_import(monkeypatch):
    """O overlay do Cofre muta o singleton de Settings in-place DEPOIS do import.

    Se a capacidade fosse capturada em tempo de import, o valor devolvido
    congelaria no do `.env` e a mudança pelo Cofre nunca chegaria à tela.
    """
    client = _montar()
    monkeypatch.setattr(
        get_settings(), "PECAS_DEMONSTRATIVO_CALCULADORA_ENABLED", True, raising=False,
    )
    assert _meta(client)["capacidades"]["demonstrativo_calculadora"] is True
    # Mesma instância de client, valor trocado no singleton entre as chamadas.
    monkeypatch.setattr(
        get_settings(), "PECAS_DEMONSTRATIVO_CALCULADORA_ENABLED", False, raising=False,
    )
    assert _meta(client)["capacidades"]["demonstrativo_calculadora"] is False


def test_meta_preserva_o_catalogo_anterior():
    """Acréscimo, não substituição: o formulário de geração depende destes."""
    corpo = _meta(_montar())
    for chave in ("tipos", "areas", "niveis_complexidade"):
        assert chave in corpo and corpo[chave], f"{chave} sumiu de /pecas/meta"
