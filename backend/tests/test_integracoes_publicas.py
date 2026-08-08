# ── tests/test_integracoes_publicas.py ───────────────────────────────────────
# Cobertura do pacote app/integrations/ (DataJud, DJEN/Comunica, BrasilAPI)
# e dos routers /api/integracoes/*.
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
import app.integrations.djen_comunica_client as djen_mod
from app.integrations import routers as integ_routers
from app.integrations.brasilapi_client import BrasilApiClient, BrasilApiError
from app.core.config import get_settings
from app.integrations.datajud_client import (
    TRIBUNAL_ALIASES,
    DataJudClient,
    DataJudDesabilitadoError,
    DataJudError,
)
from app.integrations.djen_comunica_client import (
    DjenComunicaClient,
    DjenComunicaError,
)
from app.core.database import get_db
from app.core.security import get_current_user


def _mock_async_client(monkeypatch, modulo, handler):
    """Substitui httpx.AsyncClient DO MÓDULO por um que usa MockTransport."""
    real = httpx.AsyncClient

    def factory(**kwargs):
        # httpx é módulo global: o patch atinge também o client ASGI dos
        # testes de router — quem já passa transport (ASGITransport) mantém.
        if "transport" not in kwargs:
            kwargs["transport"] = httpx.MockTransport(handler)
        return real(**kwargs)

    monkeypatch.setattr(modulo.httpx, "AsyncClient", factory)


# ── DataJud ───────────────────────────────────────────────────────────────────

async def test_datajud_limpa_mascara_envia_apikey_e_retorna_json(monkeypatch):
    visto = {}

    def handler(request: httpx.Request) -> httpx.Response:
        visto["url"] = str(request.url)
        visto["auth"] = request.headers.get("Authorization")
        visto["body"] = json.loads(request.content)
        return httpx.Response(200, json={"hits": {"hits": []}})

    # Onda 3: o wrapper delega a datajud_service (caminho único, com
    # retry/backoff) — o HTTP a mockar é o do serviço, não o do wrapper.
    from app.services import datajud_service as datajud_svc
    _mock_async_client(monkeypatch, datajud_svc, handler)
    st = get_settings()
    monkeypatch.setattr(st, "DATAJUD_ENABLED", True, raising=False)
    monkeypatch.setattr(st, "DATAJUD_API_KEY", "chave-teste", raising=False)
    cli = DataJudClient()
    out = await cli.consultar_processo(
        "0000001-02.2024.8.13.0024", TRIBUNAL_ALIASES["TJMG"]
    )
    assert out == {"hits": {"hits": []}}
    assert visto["url"].endswith("/api_publica_tjmg/_search")
    assert visto["auth"] == "APIKey chave-teste"
    assert visto["body"]["query"]["match"]["numeroProcesso"] == "00000010220248130024"


async def test_datajud_sem_chave_nao_usa_fallback_embutido(monkeypatch):
    """Onda 3 (achado de segurança): a chave pública do CNJ embutida no código
    foi REMOVIDA. Chave vazia não cai mais em fallback — a consulta é recusada
    (fail-closed), no mesmo idioma de degradação de datajud_service.

    O comportamento anterior (`DATAJUD_API_KEY=` vazia → chave embutida) fazia
    os endpoints de /integracoes continuarem batendo no CNJ mesmo com o
    kill-switch DATAJUD_ENABLED desligado.
    """
    st = get_settings()
    monkeypatch.setattr(st, "DATAJUD_ENABLED", True, raising=False)
    monkeypatch.setattr(st, "DATAJUD_API_KEY", "", raising=False)
    with pytest.raises(DataJudDesabilitadoError):
        await DataJudClient().consultar_processo(
            "0000001-02.2024.8.13.0024", TRIBUNAL_ALIASES["TJMG"]
        )


async def test_datajud_kill_switch_desliga_o_endpoint_cru(monkeypatch):
    """A superfície /integracoes passa a obedecer ao mesmo kill-switch do
    router principal: flag desligada recusa, mesmo com chave configurada."""
    st = get_settings()
    monkeypatch.setattr(st, "DATAJUD_ENABLED", False, raising=False)
    monkeypatch.setattr(st, "DATAJUD_API_KEY", "chave-valida", raising=False)
    with pytest.raises(DataJudDesabilitadoError):
        await DataJudClient().consultar_processo(
            "0000001-02.2024.8.13.0024", TRIBUNAL_ALIASES["TJMG"]
        )


def test_chave_publica_do_cnj_nao_esta_versionada():
    """Trava da correção: a chave embutida não pode voltar ao repositório."""
    from pathlib import Path

    raiz = Path(__file__).parents[1] / "app"
    embutida = "cDZHYzlZa0JadVREZDJCendQbXY"  # prefixo da chave que existia
    ofensores = [
        str(f) for f in raiz.rglob("*.py") if embutida in f.read_text(encoding="utf-8")
    ]
    assert not ofensores, f"chave do CNJ embutida de volta no código: {ofensores}"


async def test_datajud_nao_200_propaga_erro_http_do_servico(monkeypatch):
    """Onda 3: com o wrapper delegando ao serviço, o erro HTTP é o do caminho
    único (httpx após os retries). 401 é erro de contrato/auth — o predicado de
    retry do serviço não o repete, então a falha chega direto ao chamador.

    `DataJudError` continua exportado para consumidores legados do wrapper.
    """
    from app.services import datajud_service as datajud_svc

    _mock_async_client(
        monkeypatch, datajud_svc, lambda r: httpx.Response(401, text="unauthorized")
    )
    st = get_settings()
    monkeypatch.setattr(st, "DATAJUD_ENABLED", True, raising=False)
    monkeypatch.setattr(st, "DATAJUD_API_KEY", "chave-teste", raising=False)
    with pytest.raises((DataJudError, httpx.HTTPStatusError)):
        await DataJudClient().consultar_processo("123", "api_publica_tjmg")


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


# ── Routers /api/integracoes/* ────────────────────────────────────────────────

class _FakeUser:
    id = "user-teste"
    role = "advogado"


class _FakeDB:
    """Mínimo para criar_audit_log: add() síncrono + commit() awaitable."""

    def __init__(self):
        self.adds: list = []
        self.commits = 0

    def add(self, obj):
        self.adds.append(obj)

    async def commit(self):
        self.commits += 1


def _mini_app(db: _FakeDB | None = None) -> FastAPI:
    mini = FastAPI()
    mini.include_router(integ_routers.datajud_router, prefix="/api")
    mini.include_router(integ_routers.djen_router, prefix="/api")
    mini.include_router(integ_routers.brasilapi_router, prefix="/api")
    mini.dependency_overrides[get_current_user] = lambda: _FakeUser()
    mini.dependency_overrides[get_db] = lambda: db or _FakeDB()
    return mini


async def _get(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.get(path)


def test_mapa_de_tribunais_cobre_todos_os_aliases_do_servico():
    """Regressão (review Codex PR #305): o endpoint deve aceitar QUALQUER
    tribunal mapeado pelo serviço interno (todos TJs/TRTs/TRFs + STJ/TST),
    não só os 5 exemplos da spec."""
    m = integ_routers._ALIAS_POR_SIGLA
    assert m["TJSP"] == "api_publica_tjsp"
    assert m["TJRJ"] == "api_publica_tjrj"
    assert m["STJ"] == "api_publica_stj"
    assert m["TST"] == "api_publica_tst"
    assert len(m) >= 55  # 27 TJs + 24 TRTs + TRFs + superiores
    for sigla, alias in TRIBUNAL_ALIASES.items():
        assert m[sigla] == alias  # entradas da spec preservadas


async def test_router_datajud_aceita_tribunal_fora_da_spec(monkeypatch):
    visto = {}

    async def _ok(numero, alias):
        visto["alias"] = alias
        return {"hits": {"hits": []}}

    monkeypatch.setattr(integ_routers._datajud, "consultar_processo", _ok)
    resp = await _get(
        _mini_app(),
        "/api/integracoes/datajud/processos/tjsp/0000001-02.2024.8.26.0100",
    )
    assert resp.status_code == 200
    assert visto["alias"] == "api_publica_tjsp"


async def test_router_datajud_tribunal_nao_mapeado_400():
    resp = await _get(_mini_app(), "/api/integracoes/datajud/processos/XX/123")
    assert resp.status_code == 400


async def test_router_datajud_erro_de_integracao_vira_502(monkeypatch):
    async def _boom(numero, alias):
        raise DataJudError("falhou")

    monkeypatch.setattr(integ_routers._datajud, "consultar_processo", _boom)
    resp = await _get(
        _mini_app(),
        "/api/integracoes/datajud/processos/TJMG/0000001-02.2024.8.13.0024",
    )
    assert resp.status_code == 502
    # Detail genérico — corpo do upstream NUNCA ecoado ao cliente (auditoria A4).
    assert "falhou" not in resp.text


async def test_router_datajud_numero_curto_400():
    resp = await _get(_mini_app(), "/api/integracoes/datajud/processos/TJMG/123")
    assert resp.status_code == 400


async def test_router_registra_trilha_de_auditoria(monkeypatch):
    async def _ok(numero_oab, uf_oab, **kwargs):
        return {"items": []}

    monkeypatch.setattr(integ_routers._djen, "consultar_por_oab", _ok)
    db = _FakeDB()
    resp = await _get(_mini_app(db), "/api/integracoes/djen/oab/mg/104080")
    assert resp.status_code == 200
    assert db.commits == 1 and len(db.adds) == 1
    log = db.adds[0]
    assert log.acao == "CONSULTA_EXTERNA"
    assert log.entidade == "integracoes_djen"
    assert log.registro_id == "OAB 104080/MG"


async def test_router_djen_ok_passa_resultado(monkeypatch):
    async def _ok(numero_oab, uf_oab, **kwargs):
        return {"status": "success", "count": 0, "items": []}

    monkeypatch.setattr(integ_routers._djen, "consultar_por_oab", _ok)
    resp = await _get(_mini_app(), "/api/integracoes/djen/oab/MG/104080")
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


async def test_router_djen_repassa_paginacao_e_datas(monkeypatch):
    visto = {}

    async def _ok(numero_oab, uf_oab, data_inicio=None, data_fim=None, pagina=1):
        visto.update(
            oab=numero_oab, uf=uf_oab,
            data_inicio=data_inicio, data_fim=data_fim, pagina=pagina,
        )
        return {"items": []}

    monkeypatch.setattr(integ_routers._djen, "consultar_por_oab", _ok)
    resp = await _get(
        _mini_app(),
        "/api/integracoes/djen/oab/MG/104080"
        "?pagina=3&data_inicio=2026-07-01&data_fim=2026-07-18",
    )
    assert resp.status_code == 200
    assert visto["pagina"] == 3
    assert str(visto["data_inicio"]) == "2026-07-01"
    assert str(visto["data_fim"]) == "2026-07-18"


async def test_router_200_com_corpo_nao_json_vira_502(monkeypatch):
    """200 do upstream com HTML (WAF/manutenção) não pode virar 500 genérico."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>manutencao</html>")

    _mock_async_client(monkeypatch, brasilapi_mod, handler)
    resp = await _get(_mini_app(), "/api/integracoes/brasilapi/cep/30130010")
    assert resp.status_code == 502


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
