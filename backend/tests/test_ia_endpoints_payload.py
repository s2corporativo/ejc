"""Superfície real do router diplomacia-v3 após a remoção do Bloco 4.

Este arquivo nasceu no follow-up do PR #308 para travar a validação de payload
de `/diplomacia-v3/analisar-magistrado` — entrada malformada devia virar 422, e
não 500. O endpoint foi REMOVIDO por decisão do escritório (Bloco 4 do plano de
lançamento): "dossiê de pressão" e "análise de magistrado" num sistema de
advocacia são risco reputacional e disciplinar indefensável se expostos numa
perícia ou numa representação.

Com o endpoint fora, o teste de payload perdeu o objeto. Em vez de apagar o
arquivo, ele passa a exercer o que de fato importa agora, contra o router real:
as duas rotas não respondem mais, e a que ficou continua respondendo.

Um teste que roda o router de verdade pega o que a inspeção de fonte não pega —
por exemplo, alguém reintroduzir o endpoint por outro caminho de registro.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import UserRole
from app.routers import diplomacia_v3


class _FakeUser:
    id = "u-teste-payload"
    role = UserRole.advogado
    full_name = "Advogado Teste"


async def _fake_db():
    yield None  # nenhum cenário abaixo chega a tocar o banco


@pytest.fixture()
def cli_diplomacia() -> TestClient:
    app = FastAPI()
    app.include_router(diplomacia_v3.router)
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    app.dependency_overrides[get_db] = _fake_db
    return TestClient(app)


@pytest.mark.parametrize(
    "rota",
    ["/diplomacia-v3/analisar-magistrado", "/diplomacia-v3/dossie-pressao"],
)
def test_endpoints_removidos_nao_respondem_mais(cli_diplomacia, rota):
    """404, não 422: a rota não existe — não é entrada inválida."""
    r = cli_diplomacia.post(rota, json={"decisoes": ["qualquer coisa"]})
    assert r.status_code == 404, r.text


def test_calculadora_de_acordo_continua_respondendo(cli_diplomacia):
    """A remoção não podia levar junto o que está em uso.

    `selic_anual` vai no payload de propósito: com ela, `_resolver_selic`
    curto-circuita e o teste não faz chamada de rede ao BCB.
    """
    r = cli_diplomacia.post(
        "/diplomacia-v3/calcular-acordo",
        json={
            "valor_causa": 50000,
            "prob_exito": 0.6,
            "tempo_anos": 3,
            "selic_anual": 10.75,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["selic_fonte"] == "informada"


def test_calculadora_recusa_dados_insuficientes(cli_diplomacia):
    r = cli_diplomacia.post("/diplomacia-v3/calcular-acordo", json={"valor_causa": 1})
    assert r.status_code == 400, r.text


def test_o_router_expoe_exatamente_uma_rota(cli_diplomacia):
    """Trava de superfície: qualquer rota nova aqui é decisão, não acidente."""
    caminhos = {
        r.path for r in diplomacia_v3.router.routes if hasattr(r, "path")
    }
    assert caminhos == {"/diplomacia-v3/calcular-acordo"}
