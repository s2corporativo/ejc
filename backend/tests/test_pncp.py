"""PNCP contratações públicas — sem rede, sem banco.

Cobre: gate flag (503), sucesso normaliza, cache do dia SEM segunda chamada
HTTP, parsing tolerante a campos ausentes, validação de datas (422) e status.
Fakes no padrão test_infosimples.
"""
from __future__ import annotations

import json
from datetime import date

import httpx
import pytest
from fastapi import HTTPException

from app.core.config import get_settings
from app.models.user import User, UserRole
from app.services import pncp_service
from app.services.pncp_service import (
    IntegracaoDesligadaError,
    listar_contratacoes,
    normalizar_contratacao,
)


@pytest.fixture()
def pncp_ligado(monkeypatch):
    monkeypatch.setattr(get_settings(), "PNCP_ENABLED", True)
    return get_settings()


class _Res:
    def __init__(self, val):
        self._val = val

    def scalar(self):
        return self._val


class _FakeDB:
    def __init__(self, cache: dict | None = None):
        self.cache = cache
        self.inserts: list[dict] = []
        self.commits = 0

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "SELECT resultado FROM pncp_cache" in sql:
            return _Res(json.dumps(self.cache) if self.cache is not None else None)
        if "INSERT INTO pncp_cache" in sql:
            self.inserts.append(dict(params or {}))
            return _Res(None)
        return _Res(None)

    async def commit(self):
        self.commits += 1


def _advogado() -> User:
    return User(id="u1", role=UserRole.advogado)


PNCP_ITEM = {
    "numeroControlePNCP": "00000000000191-1-000001/2024",
    "orgaoEntidade": {"razaoSocial": "MUNICIPIO DE BETIM", "cnpj": "18715516000180"},
    "objetoCompra": "Aquisição de material de escritório",
    "valorTotalEstimado": 125000.50,
    "dataAberturaProposta": "2024-06-01T09:00:00",
    "unidadeOrgaoUfSigla": "MG",
    "linkSistemaOrigem": "https://pncp.gov.br/app/editais/00000000000191",
}

RESP_OK = {"data": [PNCP_ITEM], "totalRegistros": 1, "totalPaginas": 1}


def _fake_get(resp, chamadas: list | None = None):
    async def _get(url, params, timeout_s):
        if chamadas is not None:
            chamadas.append({"url": url, "params": params})
        return resp

    return _get


# ── Rotas montadas ─────────────────────────────────────────────────────────────

def test_rotas_montadas_em_main():
    from app.main import app
    paths = {getattr(r, "path", "") for r in app.routes}
    assert any(p.endswith("/pncp/contratacoes") for p in paths)
    assert any(p.endswith("/pncp/status") for p in paths)


# ── Gate ────────────────────────────────────────────────────────────────────────

async def test_gate_desligado(monkeypatch):
    monkeypatch.setattr(get_settings(), "PNCP_ENABLED", False)
    with pytest.raises(IntegracaoDesligadaError):
        await listar_contratacoes(
            _FakeDB(), data_inicial=date(2024, 6, 1), data_final=date(2024, 6, 30))


async def test_endpoint_503_flag_desligada(monkeypatch):
    from app.routers.pncp import listar_contratacoes as endpoint

    monkeypatch.setattr(get_settings(), "PNCP_ENABLED", False)
    with pytest.raises(HTTPException) as exc:
        await endpoint(
            data_inicial=date(2024, 6, 1), data_final=date(2024, 6, 30),
            uf="MG", municipio_ibge=None, modalidade=6, pagina=1,
            db=_FakeDB(), cu=_advogado())
    assert exc.value.status_code == 503


# ── Sucesso: normaliza ─────────────────────────────────────────────────────────

async def test_sucesso_normaliza(pncp_ligado, monkeypatch):
    chamadas: list = []
    monkeypatch.setattr(pncp_service, "_get_json", _fake_get(RESP_OK, chamadas))
    db = _FakeDB()

    r = await listar_contratacoes(
        db, data_inicial=date(2024, 6, 1), data_final=date(2024, 6, 30),
        uf="mg", municipio_ibge="3106705", modalidade=6, pagina=1)

    assert r["cache"] is False
    assert r["total_registros"] == 1 and r["total_paginas"] == 1
    item = r["itens"][0]
    assert item["numero_controle_pncp"] == PNCP_ITEM["numeroControlePNCP"]
    assert item["orgao"] == "MUNICIPIO DE BETIM"
    assert item["objeto"] == "Aquisição de material de escritório"
    assert item["valor_total_estimado"] == 125000.50
    assert item["uf"] == "MG"
    assert item["link"].startswith("https://pncp.gov.br")
    # Datas viraram YYYYMMDD; uf normalizada p/ maiúsculas no query.
    assert chamadas[0]["params"]["dataInicial"] == "20240601"
    assert chamadas[0]["params"]["dataFinal"] == "20240630"
    assert chamadas[0]["params"]["uf"] == "MG"
    assert chamadas[0]["params"]["codigoMunicipioIbge"] == "3106705"
    assert len(db.inserts) == 1 and db.commits == 1


# ── Cache do dia: SEM segunda chamada HTTP ─────────────────────────────────────

async def test_cache_hit_sem_chamada(pncp_ligado, monkeypatch):
    async def _nao_chamar(*a, **k):
        raise AssertionError("cache do dia não pode gerar nova chamada HTTP")

    monkeypatch.setattr(pncp_service, "_get_json", _nao_chamar)
    salvo = {"itens": [normalizar_contratacao(PNCP_ITEM)], "total_registros": 1,
             "total_paginas": 1, "pagina": 1}
    db = _FakeDB(cache=salvo)

    r = await listar_contratacoes(
        db, data_inicial=date(2024, 6, 1), data_final=date(2024, 6, 30))

    assert r["cache"] is True
    assert r["itens"][0]["orgao"] == "MUNICIPIO DE BETIM"
    assert db.inserts == []


# ── Datas inválidas → ValueError (router traduz p/ 422) ────────────────────────

async def test_data_final_antes_inicial(pncp_ligado, monkeypatch):
    monkeypatch.setattr(pncp_service, "_get_json", _fake_get(RESP_OK))
    with pytest.raises(ValueError):
        await listar_contratacoes(
            _FakeDB(), data_inicial=date(2024, 6, 30), data_final=date(2024, 6, 1))


# ── Sem resultados (404/204 do PNCP) não é erro ────────────────────────────────

async def test_sem_resultado_204_nao_e_erro(pncp_ligado, monkeypatch):
    async def _get(url, params, timeout_s):
        req = httpx.Request("GET", url)
        raise httpx.HTTPStatusError(
            "no content", request=req, response=httpx.Response(204, request=req))

    monkeypatch.setattr(pncp_service, "_get_json", _get)
    r = await listar_contratacoes(
        _FakeDB(), data_inicial=date(2024, 6, 1), data_final=date(2024, 6, 30))
    assert r["itens"] == [] and r["cache"] is False


# ── Parsing tolerante ──────────────────────────────────────────────────────────

def test_normalizar_tolerante():
    vazio = normalizar_contratacao({})
    assert vazio["numero_controle_pncp"] is None
    assert vazio["orgao"] is None
    # Nomes de campo alternativos ainda são captados.
    alt = normalizar_contratacao({
        "numeroControle": "X-1", "objeto": "Serviço", "valorTotal": 10,
        "orgao": {"nome": "Prefeitura"},
    })
    assert alt["numero_controle_pncp"] == "X-1"
    assert alt["orgao"] == "Prefeitura"
    assert alt["objeto"] == "Serviço"


# ── Status ──────────────────────────────────────────────────────────────────────

async def test_status(pncp_ligado):
    st = await pncp_service.status()
    assert st["enabled"] is True and st["sem_chave"] is True
