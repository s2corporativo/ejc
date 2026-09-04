"""Regressão do contador `resumo.casos_ativos` em `GET /clients/{id}/dossie`.

Achado da simulação A0 / plano-mestre (item V2-1.2): desde a migration 126 o
enum persistido em `cases.status` não tem mais os valores `ativo`/`triagem`
(vocabulário pré-migration). O código antigo filtrava
`c["status"] in ("ativo", "triagem")` — como nenhum caso real jamais tem esse
literal, `casos_ativos` ficava sempre em 0, mesmo com casos abertos.
`app/routers/dossie_cliente.py::_resumo_casos` agora usa
`app/core/status_caso.py::STATUS_ABERTOS`/`STATUS_FECHADOS` — a mesma fonte
única já usada pelo Dashboard e por `/cases`.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.routers import dossie_cliente

_CLIENTE = {
    "id": "cli-1", "nome": "Fulano", "email": None, "telefone": None,
    "whatsapp": None, "tipo": "pf", "created_at": None,
    "cpf_enc": None, "cnpj_enc": None,
}


def _caso(id_: str, status: str) -> dict:
    return {
        "id": id_, "numero_interno": id_, "titulo": f"Caso {id_}",
        "area": "civel", "status": status, "fase": "inicial",
        "created_at": None, "updated_at": None,
    }


class _Resultado:
    def __init__(self, linhas):
        self._linhas = linhas

    def mappings(self):
        return self

    def first(self):
        return self._linhas[0] if self._linhas else None

    def all(self):
        return self._linhas

    def scalar(self):
        return self._linhas[0] if self._linhas else 0


class _DB:
    """Sessão fake: 1 caso em cada um dos 6 status reais do enum pós-126 --
    4 abertos (`aberto`, `em_instrucao`, `em_producao`, `protocolado`) e 2
    fechados (`encerrado`, `arquivado`)."""

    def __init__(self):
        self.casos = [
            _caso("c-aberto", "aberto"),
            _caso("c-instrucao", "em_instrucao"),
            _caso("c-producao", "em_producao"),
            _caso("c-protocolado", "protocolado"),
            _caso("c-encerrado", "encerrado"),
            _caso("c-arquivado", "arquivado"),
        ]

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "FROM clients" in sql:
            return _Resultado([_CLIENTE])
        if "FROM cases" in sql:
            return _Resultado(self.casos)
        if "COUNT(*)" in sql:
            return _Resultado([0])
        return _Resultado([])

    async def rollback(self):
        pass


def _http(db) -> TestClient:
    app = FastAPI()
    app.include_router(dossie_cliente.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: User(
        id="u1", email="socio@ejc.test", full_name="Sócio", role="socio"
    )
    return TestClient(app)


def test_casos_ativos_conta_os_quatro_estados_de_trabalho():
    r = _http(_DB()).get("/clients/cli-1/dossie")
    assert r.status_code == 200
    resumo = r.json()["resumo"]
    assert resumo["casos_ativos"] == 4
    assert resumo["casos_encerrados"] == 2
    assert resumo["total_casos"] == 6


def test_casos_ativos_nao_conta_zero_com_casos_abertos_reais():
    """Regressão direta do bug: um único caso `aberto` (status real, não o
    literal legado "ativo") precisa contar como ativo -- o defeito original
    fazia isso sempre dar 0."""
    db = _DB()
    db.casos = [_caso("c1", "aberto")]
    r = _http(db).get("/clients/cli-1/dossie")
    assert r.json()["resumo"]["casos_ativos"] == 1


@pytest.mark.parametrize("literal_legado", ["ativo", "triagem"])
def test_literais_legados_nao_contam_mais_como_ativo(literal_legado):
    """`ativo`/`triagem` não existem no enum pós-126 (nenhum caso real tem
    esse valor) -- mas se algum dado residual tiver, não deve ser contado
    como aberto nem como encerrado: cai fora dos dois agregados."""
    db = _DB()
    db.casos = [_caso("c1", literal_legado)]
    r = _http(db).get("/clients/cli-1/dossie")
    resumo = r.json()["resumo"]
    assert resumo["casos_ativos"] == 0
    assert resumo["casos_encerrados"] == 0
    assert resumo["total_casos"] == 1
