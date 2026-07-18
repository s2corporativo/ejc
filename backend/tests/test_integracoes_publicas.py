# ── tests/test_integracoes_publicas.py ───────────────────────────────────────
# Cobertura do pacote app/integrations/ (DataJud, DJEN/Comunica, BrasilAPI,
# Conecta gov.br) e dos routers /api/integracoes/*.
#
# Rede é SEMPRE mockada (httpx.MockTransport) — CI não tem egress para as
# APIs públicas. O teste real (curl) contra DataJud/DJEN/BrasilAPI roda no
# servidor, fora da suíte.
from __future__ import annotations

import json

import httpx
import pytest
from fastapi import FastAPI

import app.integrations.brasilapi_client as brasilapi_mod
import app.integrations.conecta_gov_client as conecta_mod
import app.integrations.datajud_client as datajud_mod
import app.integrations.djen_comunica_client as djen_mod
from app.integrations import routers as integ_routers
from app.integrations.brasilapi_client import BrasilApiClient, BrasilApiError
from app.integrations.conecta_gov_client import ConectaGovClient, ConectaGovError
from app.integrations.datajud_client import (
    TRIBUNAL_ALIASES,
    DataJudClient,
    DataJudError,
)
from app.integrations.djen_comunica_client import (
    DjenComunicaClient,
    DjenComunicaError,
)
from app.core.security import get_current_user


def _mock_async_client(monkeypatch, modulo, handler):
    """Substitui httpx.AsyncClient DO MÓDULO por um que usa MockTransport."""
    real = httpx.AsyncClient

    def factory(**kwargs):
        kwargs.pop("transport", None)
        return real(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(modulo.httpx, "AsyncClient", factory)


# ── DataJud ───────────────────────────────────────────────────────────────────

async def test_datajud_limpa_mascara_envia_apikey_e_retorna_json(monkeypatch):
    visto = {}

    def handler(request: httpx.Request) -> httpx.Response:
        visto["url"] = str(request.url)
        visto["auth"] = request.headers.get("Authorization")
        visto["body"] = json.loads(request.content)
        return httpx.Response(200, json={"hits": {"hits": []}})

    _mock_async_client(monkeypatch, datajud_mod, handler)
    cli = DataJudClient(api_key="chave-teste")
    out = await cli.consultar_processo(
        "0000001-02.2024.8.13.0024", TRIBUNAL_ALIASES["TJMG"]
    )
    assert out == {"hits": {"hits": []}}
    assert visto["url"].endswith("/api_publica_tjmg/_search")
    assert visto["auth"] == "APIKey chave-teste"
    assert visto["body"]["query"]["match"]["numeroProcesso"] == "00000010220248130024"


async def test_datajud_nao_200_vira_datajuderror(monkeypatch):
    _mock_async_client(
        monkeypatch, datajud_mod, lambda r: httpx.Response(401, text="unauthorized")
    )
    with pytest.raises(DataJudError):
        await DataJudClient(api_key="x").consultar_processo("123", "api_publica_tjmg")


# ── DJEN/Comunica ─────────────────────────────────────────────────────────────

async def test_djen_consulta_por_oab_monta_params(monkeypatch):
    visto = {}

    def handler(request: httpx.Request) -> httpx.Response:
        visto["params"] = dict(request.url.params)
        return httpx.Response(200, json={"status": "success", "count": 1, "items": []})

    _mock_async_client(monkeypatch, djen_mod, handler)
    out = await DjenComunicaClient().consultar_por_oab("104080", "MG")
    assert out["count"] == 1
    assert visto["params"] == {"numeroOab": "104080", "ufOab": "MG", "pagina": "1"}


async def test_djen_erro_http_vira_djenerror(monkeypatch):
    _mock_async_client(monkeypatch, djen_mod, lambda r: httpx.Response(503, text="down"))
    with pytest.raises(DjenComunicaError):
        await DjenComunicaClient().consultar_por_processo("0000001-02.2024.8.13.0024")


# ── BrasilAPI ─────────────────────────────────────────────────────────────────

async def test_brasilapi_cnpj_e_cep_limpam_entrada(monkeypatch):
    urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, json={"ok": True})

    _mock_async_client(monkeypatch, brasilapi_mod, handler)
    cli = BrasilApiClient()
    await cli.consultar_cnpj("00.000.000/0001-91")
    await cli.consultar_cep("30130-010")
    assert urls[0].endswith("/cnpj/v1/00000000000191")
    assert urls[1].endswith("/cep/v2/30130010")


async def test_brasilapi_404_vira_brasilapierror(monkeypatch):
    _mock_async_client(monkeypatch, brasilapi_mod, lambda r: httpx.Response(404))
    with pytest.raises(BrasilApiError):
        await BrasilApiClient().consultar_cep("00000000")


# ── Conecta gov.br (scaffold — sem credenciais deve falhar SEM rede) ─────────

async def test_conecta_sem_credenciais_erro_claro(monkeypatch):
    monkeypatch.delenv("CONECTA_CLIENT_ID", raising=False)
    monkeypatch.delenv("CONECTA_CLIENT_SECRET", raising=False)
    cli = ConectaGovClient()
    with pytest.raises(ConectaGovError, match="credenciamento"):
        await cli.consultar_cpf("11111111111")


# ── Routers /api/integracoes/* ────────────────────────────────────────────────

def _mini_app() -> FastAPI:
    mini = FastAPI()
    mini.include_router(integ_routers.datajud_router, prefix="/api")
    mini.include_router(integ_routers.djen_router, prefix="/api")
    mini.include_router(integ_routers.brasilapi_router, prefix="/api")
    mini.dependency_overrides[get_current_user] = lambda: {"id": "t", "role": "adv"}
    return mini


async def _get(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.get(path)


async def test_router_datajud_tribunal_nao_mapeado_400():
    resp = await _get(_mini_app(), "/api/integracoes/datajud/processos/XX/123")
    assert resp.status_code == 400


async def test_router_datajud_erro_de_integracao_vira_502(monkeypatch):
    async def _boom(numero, alias):
        raise DataJudError("falhou")

    monkeypatch.setattr(integ_routers._datajud, "consultar_processo", _boom)
    resp = await _get(
        _mini_app(), "/api/integracoes/datajud/processos/TJMG/0000001"
    )
    assert resp.status_code == 502


async def test_router_djen_ok_passa_resultado(monkeypatch):
    async def _ok(numero_oab, uf_oab):
        return {"status": "success", "count": 0, "items": []}

    monkeypatch.setattr(integ_routers._djen, "consultar_por_oab", _ok)
    resp = await _get(_mini_app(), "/api/integracoes/djen/oab/MG/104080")
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


async def test_router_brasilapi_ok(monkeypatch):
    async def _ok(cnpj):
        return {"razao_social": "X"}

    monkeypatch.setattr(integ_routers._brasilapi, "consultar_cnpj", _ok)
    resp = await _get(_mini_app(), "/api/integracoes/brasilapi/cnpj/00000000000191")
    assert resp.status_code == 200


def test_todos_endpoints_exigem_jwt():
    """Cada rota de integração deve declarar get_current_user (defesa em
    profundidade além do AuthMiddleware global)."""
    for router in (
        integ_routers.datajud_router,
        integ_routers.djen_router,
        integ_routers.brasilapi_router,
    ):
        for rota in router.routes:
            deps = [d.call for d in rota.dependant.dependencies]
            assert get_current_user in deps, f"rota sem JWT: {rota.path}"
