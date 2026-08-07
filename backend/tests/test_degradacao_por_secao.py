"""Degradação POR SEÇÃO em respostas agregadas (Onda 1 da refatoração).

A auditoria de julho/2026 reproduziu 500 em `/clients/{id}/dossie` e em
`/clients/{id}/relatorio-financeiro`: UMA agregação com problema derrubava a
resposta inteira e a ficha do cliente não abria.

Regra travada aqui: seção que falha vira valor neutro + nome em
`secoes_indisponiveis`; as demais seções continuam preenchidas e a resposta é
200. E, porque o PostgreSQL aborta a transação inteira no primeiro erro, a
falha de uma seção precisa rolar a sessão de volta — sem isso o isolamento
seria só aparente e a seção seguinte falharia em cascata.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.degradacao import ColetorDeSecoes, executar_secao
from app.core.security import get_current_user
from app.models.user import User
from app.routers import dossie_cliente


# ── Unidade: o coletor ────────────────────────────────────────────────────────

async def _ok(valor):
    return valor


async def _explode():
    raise RuntimeError("consulta quebrada")


@pytest.mark.asyncio
async def test_secao_saudavel_nao_entra_em_indisponiveis():
    secoes = ColetorDeSecoes("teste")
    assert await secoes.tentar("casos", _ok([1, 2]), padrao=[]) == [1, 2]
    assert secoes.rodape() == {"secoes_indisponiveis": []}


@pytest.mark.asyncio
async def test_secao_que_falha_devolve_padrao_e_e_nomeada():
    secoes = ColetorDeSecoes("teste")
    assert await secoes.tentar("prazos", _explode(), padrao=[]) == []
    assert await secoes.tentar("casos", _ok(["c1"]), padrao=[]) == ["c1"]
    assert secoes.rodape() == {"secoes_indisponiveis": ["prazos"]}


@pytest.mark.asyncio
async def test_falha_de_secao_rola_a_sessao_de_volta():
    """Sem o rollback, a transação abortada faria TODA seção seguinte falhar."""
    class _DBFake:
        def __init__(self):
            self.rollbacks = 0

        async def rollback(self):
            self.rollbacks += 1

    db = _DBFake()
    secoes = ColetorDeSecoes("teste", db)
    await secoes.tentar("a", _explode(), padrao=None)
    await secoes.tentar("b", _ok(1), padrao=None)
    assert db.rollbacks == 1  # só a seção que falhou dispara rollback


@pytest.mark.asyncio
async def test_rollback_que_falha_nao_derruba_a_degradacao():
    class _DBQuebrado:
        async def rollback(self):
            raise RuntimeError("sessão perdida")

    secoes = ColetorDeSecoes("teste", _DBQuebrado())
    assert await secoes.tentar("a", _explode(), padrao="neutro") == "neutro"
    assert secoes.indisponiveis == ["a"]


def test_executar_secao_isola_calculo_sincrono():
    secoes = ColetorDeSecoes("teste")

    def _quebra():
        raise ValueError("agregação impossível")

    assert executar_secao(secoes, "resumo", _quebra, padrao={}) == {}
    assert executar_secao(secoes, "outro", lambda: {"x": 1}, padrao={}) == {"x": 1}
    assert secoes.indisponiveis == ["resumo"]


@pytest.mark.asyncio
async def test_http_exception_atravessa_o_coletor_sem_virar_degradacao():
    """Autorização NÃO degrada. Se um gate levantar 403/404 de dentro de uma
    seção, virar 200 + valor neutro esconderia justamente o erro que mais
    importa — o padrão que existe para não mascarar falha passaria a mascarar
    a falha de autorização."""
    async def _negado():
        raise HTTPException(403, "Acesso restrito à gestão (sócio+)")

    secoes = ColetorDeSecoes("teste")
    with pytest.raises(HTTPException) as exc:
        await secoes.tentar("casos", _negado(), padrao=[])
    assert exc.value.status_code == 403
    assert secoes.indisponiveis == []  # não foi contabilizada como degradação


def test_http_exception_tambem_atravessa_a_variante_sincrona():
    def _nao_encontrado():
        raise HTTPException(404, "Cliente não encontrado")

    secoes = ColetorDeSecoes("teste")
    with pytest.raises(HTTPException) as exc:
        executar_secao(secoes, "resumo", _nao_encontrado, padrao={})
    assert exc.value.status_code == 404
    assert secoes.indisponiveis == []


def test_mesma_secao_falhando_duas_vezes_nao_duplica_o_nome():
    secoes = ColetorDeSecoes("teste")
    secoes.registrar_falha("casos", RuntimeError("a"))
    secoes.registrar_falha("casos", RuntimeError("b"))
    assert secoes.indisponiveis == ["casos"]


# ── Integração: o dossiê degrada em vez de responder 500 ──────────────────────

_CLIENTE = {
    "id": "cli-1", "nome": "Fulano", "email": None, "telefone": None,
    "whatsapp": None, "tipo": "pf", "created_at": None, "cpf_cnpj": None,
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


class _DBFalhandoEm:
    """Sessão fake: responde às consultas por trecho do SQL e explode nas
    tabelas listadas em `quebrar`."""

    def __init__(self, quebrar: set[str]):
        self.quebrar = quebrar
        self.rollbacks = 0

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        for tabela in self.quebrar:
            if tabela in sql:
                raise RuntimeError(f"falha simulada em {tabela}")
        if "FROM clients" in sql:
            return _Resultado([_CLIENTE])
        if "COUNT(*)" in sql:
            return _Resultado([3])
        if "FROM fees" in sql:
            return _Resultado([{"total": 100, "recebido": 40, "pendente": 60}])
        if "FROM cases" in sql:
            return _Resultado([{
                "id": "c1", "numero_interno": "001", "titulo": "Caso",
                "area": "civel", "status": "ativo", "fase": "inicial",
                "created_at": None, "updated_at": None,
            }])
        return _Resultado([])

    async def rollback(self):
        self.rollbacks += 1


def _cliente_http(db) -> TestClient:
    app = FastAPI()
    app.include_router(dossie_cliente.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: User(
        id="u1", email="socio@ejc.test", full_name="Sócio", role="socio"
    )
    return TestClient(app)


def test_dossie_abre_com_todas_as_secoes_saudaveis():
    db = _DBFalhandoEm(set())
    r = _cliente_http(db).get("/clients/cli-1/dossie")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["secoes_indisponiveis"] == []
    assert corpo["resumo"]["total_casos"] == 1
    assert corpo["resumo"]["honorarios_total"] == 100.0


def test_dossie_degrada_a_secao_de_prazos_sem_derrubar_a_tela():
    """Regressão do 500: prazos quebrado NÃO pode levar o dossiê inteiro."""
    db = _DBFalhandoEm({"FROM deadlines"})
    r = _cliente_http(db).get("/clients/cli-1/dossie")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["secoes_indisponiveis"] == ["prazos"]
    assert corpo["prazos"] == []
    # O que não quebrou continua preenchido — a tela abre útil.
    assert corpo["cliente"]["nome"] == "Fulano"
    assert len(corpo["casos"]) == 1
    assert corpo["resumo"]["docs_total"] == 3
    assert db.rollbacks == 1


def test_dossie_com_varias_secoes_quebradas_ainda_responde_200():
    db = _DBFalhandoEm({"FROM deadlines", "FROM documents", "FROM fees"})
    r = _cliente_http(db).get("/clients/cli-1/dossie")
    assert r.status_code == 200
    corpo = r.json()
    assert sorted(corpo["secoes_indisponiveis"]) == ["documentos", "honorarios", "prazos"]
    assert corpo["resumo"]["docs_total"] == 0
    assert corpo["resumo"]["honorarios_total"] == 0.0
    assert len(corpo["casos"]) == 1


def test_dossie_sem_cliente_continua_404():
    """Degradação não engole o 404: sem cliente não há dossiê."""
    class _SemCliente(_DBFalhandoEm):
        async def execute(self, stmt, params=None):
            if "FROM clients" in str(stmt):
                return _Resultado([])
            return await super().execute(stmt, params)

    r = _cliente_http(_SemCliente(set())).get("/clients/cli-1/dossie")
    assert r.status_code == 404
