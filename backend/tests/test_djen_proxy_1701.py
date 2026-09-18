"""#1701 — transporte DJEN permite egress privado sem vazar configuração."""
from __future__ import annotations

import pytest

from app.services import djen_http


class _FakeClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def test_cliente_direto_nao_herda_proxy_global(monkeypatch):
    monkeypatch.delenv("DJEN_HTTP_PROXY_URL", raising=False)
    monkeypatch.setattr(djen_http.httpx, "AsyncClient", _FakeClient)
    cli = djen_http.criar_cliente_djen(timeout=25)
    assert cli.kwargs["trust_env"] is False
    assert "proxy" not in cli.kwargs


def test_cliente_proxy_usa_env_sem_mudar_endpoint(monkeypatch):
    segredo = "http://usuario:senha@proxy.exemplo:3128"
    monkeypatch.setenv("DJEN_HTTP_PROXY_URL", segredo)
    monkeypatch.setattr(djen_http.httpx, "AsyncClient", _FakeClient)
    cli = djen_http.criar_cliente_djen(timeout=30)
    assert cli.kwargs["proxy"] == segredo
    assert cli.kwargs["trust_env"] is False
    assert djen_http.DJEN_COMUNICACAO_URL == "https://comunicaapi.pje.jus.br/api/v1/comunicacao"


@pytest.mark.parametrize("valor", ["socks5://proxy:1080", "file:///tmp/x", "http://proxy:3128/path", "http://proxy:3128/?x=1"])
def test_proxy_invalido_falha_fechado_sem_expor_valor(monkeypatch, valor):
    monkeypatch.setenv("DJEN_HTTP_PROXY_URL", valor)
    with pytest.raises(RuntimeError) as exc:
        djen_http.criar_cliente_djen(timeout=10)
    assert valor not in str(exc.value)


def test_todas_as_portas_djen_usam_transporte_canonico():
    import inspect
    from app.integrations import djen_comunica_client
    from app.services import djen_service
    from app.services.ingestors import djen as ingestor
    assert "criar_cliente_djen" in inspect.getsource(djen_service._djen_get)
    fonte_ingestor = inspect.getsource(ingestor._coletar_oab)
    assert "fetch(" in fonte_ingestor
    assert "preparar_requisicao_djen" in fonte_ingestor
    assert "trust_env=False" in fonte_ingestor
    assert "criar_cliente_djen" in inspect.getsource(djen_comunica_client.DjenComunicaClient.consultar_por_oab)
    assert "criar_cliente_djen" in inspect.getsource(djen_comunica_client.DjenComunicaClient.consultar_por_processo)


@pytest.mark.asyncio
async def test_fetch_proxy_e_trust_env_sao_opt_in(monkeypatch):
    from app.services import ingestion_service

    capturado = {}

    class _Response:
        status_code = 200
        def raise_for_status(self):
            return None

    class _Client:
        def __init__(self, **kwargs):
            capturado.update(kwargs)
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def request(self, *args, **kwargs):
            return _Response()

    monkeypatch.setattr(ingestion_service.httpx, "AsyncClient", _Client)
    await ingestion_service.fetch(
        "https://exemplo.invalid",
        proxy="http://proxy.exemplo:3128",
        trust_env=False,
        tentativas=1,
    )
    assert capturado["proxy"] == "http://proxy.exemplo:3128"
    assert capturado["trust_env"] is False


def _relay_private_key_b64():
    import base64
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return key, base64.b64encode(pem).decode()


def test_relay_assina_query_canonica_e_tem_precedencia_sobre_proxy(monkeypatch):
    import base64

    key, key_b64 = _relay_private_key_b64()
    monkeypatch.setenv("DJEN_RELAY_URL", "https://relay.example/api/djen")
    monkeypatch.setenv("DJEN_RELAY_PRIVATE_KEY_B64", key_b64)
    monkeypatch.setenv("DJEN_HTTP_PROXY_URL", "http://proxy.exemplo:3128")
    monkeypatch.setattr(djen_http.time, "time", lambda: 1_800_000_000)

    params = {
        "ufOab": "MG",
        "numeroOab": "104080",
        "pagina": 1,
        "itensPorPagina": 50,
    }
    alvo, headers, proxy = djen_http.preparar_requisicao_djen(params)

    assert alvo == "https://relay.example/api/djen"
    assert proxy is None
    assert headers["x-ejc-timestamp"] == "1800000000"
    canonica = "itensPorPagina=50&numeroOab=104080&pagina=1&ufOab=MG"
    assinatura = base64.urlsafe_b64decode(
        headers["x-ejc-signature"] + "=="
    )
    key.public_key().verify(
        assinatura,
        ("1800000000\n" + canonica).encode(),
    )

    monkeypatch.setattr(djen_http.httpx, "AsyncClient", _FakeClient)
    cli = djen_http.criar_cliente_djen(timeout=10)
    assert "proxy" not in cli.kwargs


def test_relay_sem_chave_falha_fechado(monkeypatch):
    monkeypatch.setenv("DJEN_RELAY_URL", "https://relay.example/api/djen")
    monkeypatch.delenv("DJEN_RELAY_PRIVATE_KEY_B64", raising=False)
    with pytest.raises(RuntimeError, match="ausente"):
        djen_http.preparar_requisicao_djen({"numeroOab": "1", "ufOab": "MG"})


@pytest.mark.parametrize(
    "valor",
    [
        "http://relay.example/api/djen",
        "https://user:pass@relay.example/api/djen",
        "https://relay.example/api/djen?x=1",
        "file:///tmp/relay",
    ],
)
def test_relay_invalido_falha_fechado_sem_expor_valor(monkeypatch, valor):
    monkeypatch.setenv("DJEN_RELAY_URL", valor)
    with pytest.raises(RuntimeError) as exc:
        djen_http.preparar_requisicao_djen({"numeroOab": "1", "ufOab": "MG"})
    assert valor not in str(exc.value)
