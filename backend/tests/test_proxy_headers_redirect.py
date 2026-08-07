"""Redirect de barra final atrás do Nginx (Onda 1 da refatoração).

Sintoma reproduzido pela auditoria: `GET /api/sala-juridica/` morria com
"Failed to fetch" no browser, enquanto `GET /api/sala-juridica` respondia 200.

Causa: o EJC tem 163 routers e eles divergem — uns declaram a rota de coleção
como `""` (`/api/sala-juridica`), outros como `"/"` (`/api/clients/`). Nos dois
casos o Starlette resolve a forma "errada" com um 307 cujo `Location` é
ABSOLUTO, montado a partir do esquema que o app enxerga. O uvicorn subia com
`--proxy-headers`, mas o default de `--forwarded-allow-ips` é só `127.0.0.1` —
e a origem que chega ao container, pela porta publicada do Docker, é o gateway
da bridge. O `X-Forwarded-Proto: https` do Nginx era descartado, o app se via
em `http` e o redirect apontava para `http://…`: downgrade que o browser bloqueia
numa página https.

Correção: `--forwarded-allow-ips` explícito no entrypoint. Estes testes travam
o comportamento (redirect em https) e a configuração que o garante.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware


def _app_com_rota_sem_barra() -> FastAPI:
    """Mesma forma do router da Sala Jurídica: coleção declarada como `""`."""
    app = FastAPI()
    router = APIRouter(prefix="/sala-juridica")

    @router.get("")
    async def listar():
        return []

    app.include_router(router, prefix="/api")
    return app


def _app_com_rota_com_barra() -> FastAPI:
    """Mesma forma do router de Clientes: coleção declarada como `"/"`."""
    app = FastAPI()
    router = APIRouter(prefix="/clients")

    @router.get("/")
    async def listar():
        return []

    app.include_router(router, prefix="/api")
    return app


_PROXY = {"X-Forwarded-Proto": "https", "X-Forwarded-For": "203.0.113.9"}


# base_url http:// = o que o uvicorn realmente enxerga na conexão vinda do
# Nginx; é o X-Forwarded-Proto (e só ele) que deve promover o esquema a https.
_BASE = "http://ejc.test"


def test_sem_confiar_no_proxy_o_redirect_faz_downgrade_para_http():
    """Documenta o defeito: é este `Location: http://` que o browser bloqueia
    quando a página de origem está em https."""
    cliente = TestClient(_app_com_rota_sem_barra(), base_url=_BASE)
    r = cliente.get("/api/sala-juridica/", headers=_PROXY, follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "http://ejc.test/api/sala-juridica"


def test_confiando_no_proxy_o_redirect_preserva_https():
    app = _app_com_rota_sem_barra()
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
    cliente = TestClient(app, base_url=_BASE)

    r = cliente.get("/api/sala-juridica/", headers=_PROXY, follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "https://ejc.test/api/sala-juridica"
    # O destino do redirect é a rota real — seguir o 307 conclui a chamada.
    assert cliente.get("/api/sala-juridica", headers=_PROXY).status_code == 200


def test_vale_para_a_forma_inversa_rota_declarada_com_barra():
    """Metade dos routers declara `"/"`: lá o redirect é do caminho SEM barra."""
    app = _app_com_rota_com_barra()
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
    cliente = TestClient(app, base_url=_BASE)

    r = cliente.get("/api/clients", headers=_PROXY, follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "https://ejc.test/api/clients/"
    assert cliente.get("/api/clients/", headers=_PROXY).status_code == 200


def test_entrypoint_sobe_o_uvicorn_confiando_no_proxy_do_host():
    """Guarda de configuração: `--proxy-headers` sem `--forwarded-allow-ips`
    reintroduz o bug (o default do uvicorn confia só em 127.0.0.1)."""
    entrypoint = (Path(__file__).resolve().parents[1] / "entrypoint.sh").read_text(encoding="utf-8")
    linha_uvicorn = entrypoint[entrypoint.index("exec uvicorn"):]
    assert "--proxy-headers" in linha_uvicorn
    assert "--forwarded-allow-ips" in linha_uvicorn
    # Sobreponível pelo .env, com default utilizável no stack padrão.
    assert "${FORWARDED_ALLOW_IPS:-*}" in linha_uvicorn
