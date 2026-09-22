from __future__ import annotations

import pytest

from app.core import safe_outbound_url as sou


def _addrinfo(ip: str):
    fam = 10 if ":" in ip else 2
    return [(fam, 1, 6, "", (ip, 0))]


def test_validar_url_publica_bloqueia_userinfo_e_ip_privado(monkeypatch):
    with pytest.raises(ValueError, match="credenciais"):
        sou.validar_url_publica("https://user:pass@example.com/x")

    monkeypatch.setattr(
        sou.socket, "getaddrinfo", lambda host, port: _addrinfo("10.0.0.5")
    )
    with pytest.raises(ValueError, match="privado/loopback"):
        sou.validar_url_publica("https://example.com/x")


@pytest.mark.asyncio
async def test_buscar_url_publica_fixa_ip_host_e_sni_sem_segunda_resolucao(
    monkeypatch,
):
    resolucoes = {"n": 0}

    def dns(host, port):
        resolucoes["n"] += 1
        return _addrinfo(
            "93.184.216.34" if resolucoes["n"] == 1 else "10.0.0.5"
        )

    monkeypatch.setattr(sou.socket, "getaddrinfo", dns)
    capturas = []

    class Resp:
        is_redirect = False
        headers = {}

    class Client:
        def __init__(self, *args, **kwargs):
            assert kwargs["follow_redirects"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, headers=None, extensions=None):
            capturas.append((url, headers, extensions))
            return Resp()

    monkeypatch.setattr(sou.httpx, "AsyncClient", Client)
    await sou.buscar_url_publica("https://example.com:8443/doc")

    assert resolucoes["n"] == 1
    url, headers, extensions = capturas[0]
    assert url == "https://93.184.216.34:8443/doc"
    assert headers["Host"] == "example.com"
    assert extensions["sni_hostname"] == "example.com"


@pytest.mark.asyncio
async def test_buscar_url_publica_revalida_redirect_e_bloqueia_destino_privado(
    monkeypatch,
):
    def dns(host, port):
        return _addrinfo(
            "93.184.216.34" if host == "public.example" else "127.0.0.1"
        )

    monkeypatch.setattr(sou.socket, "getaddrinfo", dns)
    capturas = []

    class Redirect:
        is_redirect = True
        headers = {"location": "https://private.example/secret"}

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, headers=None, extensions=None):
            capturas.append(url)
            return Redirect()

    monkeypatch.setattr(sou.httpx, "AsyncClient", Client)

    with pytest.raises(ValueError, match="privado/loopback"):
        await sou.buscar_url_publica("https://public.example/start")

    assert capturas == ["https://93.184.216.34/start"]
