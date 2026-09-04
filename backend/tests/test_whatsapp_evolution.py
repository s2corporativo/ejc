"""Canal WhatsApp religado pela Evolution API (a instância que já roda na VPS).

Regressão do achado "o canal está morto e ninguém percebe": `enviar_whatsapp`
só logava e devolvia False, e `channel_availability` fixava `whatsapp=False` no
código — `WHATSAPP_ENABLED=true` não religava nada.

Sem rede e sem banco: httpx.AsyncClient é substituído por um duplo que registra
a requisição montada (a suíte não tem respx). Os testes de degradação usam um
duplo que EXPLODE se instanciado — "não tocar a rede" é asserção, não promessa.
"""
from __future__ import annotations

import logging

import httpx
import pytest

from app.core.config import Settings
from app.services import notification_service as ns
from app.services.notification_preferences import channel_availability

TELEFONE = "(31) 98888-7777"
NUMERO_E164 = "5531988887777"
MENSAGEM = "Prazo de contestação vence amanhã no caso 0001234-56.2026.8.13.0027"


def _resposta(status: int = 200) -> httpx.Response:
    req = httpx.Request("POST", "http://evolution_api:8080/message/sendText/i")
    return httpx.Response(status, json={"key": {"id": "MSG1"}}, request=req)


def _config_completa(monkeypatch) -> None:
    monkeypatch.setattr(ns.settings, "WHATSAPP_ENABLED", True)
    monkeypatch.setattr(ns.settings, "EVOLUTION_API_URL", "http://evolution_api:8080/")
    monkeypatch.setattr(ns.settings, "EVOLUTION_API_KEY", "chave-secreta")
    monkeypatch.setattr(ns.settings, "EVOLUTION_INSTANCE", "ejc-escritorio")
    monkeypatch.setattr(ns.settings, "EVOLUTION_TIMEOUT", 7.5)


def _httpx_falso(monkeypatch, *, resposta=None, excecao=None) -> dict:
    registro: dict[str, list] = {"init": [], "post": []}

    class _Cli:
        def __init__(self, **kwargs):
            registro["init"].append(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def post(self, url, headers=None, json=None):
            registro["post"].append({"url": url, "headers": headers, "json": json})
            if excecao is not None:
                raise excecao
            return resposta if resposta is not None else _resposta(200)

    monkeypatch.setattr(ns.httpx, "AsyncClient", _Cli)
    return registro


def _httpx_proibido(monkeypatch) -> None:
    class _Bomba:
        def __init__(self, **kwargs):
            raise AssertionError("canal degradado NÃO pode abrir conexão de rede")

    monkeypatch.setattr(ns.httpx, "AsyncClient", _Bomba)


# ── Degradação graciosa (sem flag / sem configuração → False, sem rede) ───────
async def test_flag_desligada_nao_envia_e_nao_toca_rede(monkeypatch):
    _config_completa(monkeypatch)
    monkeypatch.setattr(ns.settings, "WHATSAPP_ENABLED", False)
    _httpx_proibido(monkeypatch)
    assert await ns.enviar_whatsapp(TELEFONE, MENSAGEM) is False


async def test_sem_api_key_nao_envia_e_nao_toca_rede(monkeypatch):
    _config_completa(monkeypatch)
    monkeypatch.setattr(ns.settings, "EVOLUTION_API_KEY", "")
    _httpx_proibido(monkeypatch)
    assert await ns.enviar_whatsapp(TELEFONE, MENSAGEM) is False


async def test_sem_url_nao_envia_e_nao_toca_rede(monkeypatch):
    _config_completa(monkeypatch)
    monkeypatch.setattr(ns.settings, "EVOLUTION_API_URL", "")
    _httpx_proibido(monkeypatch)
    assert await ns.enviar_whatsapp(TELEFONE, MENSAGEM) is False


async def test_telefone_invalido_nao_toca_rede(monkeypatch):
    _config_completa(monkeypatch)
    _httpx_proibido(monkeypatch)
    assert await ns.enviar_whatsapp("123", MENSAGEM) is False


# ── Envio efetivo ─────────────────────────────────────────────────────────────
async def test_envio_monta_requisicao_da_evolution_api(monkeypatch):
    _config_completa(monkeypatch)
    registro = _httpx_falso(monkeypatch)

    assert await ns.enviar_whatsapp(TELEFONE, MENSAGEM) is True

    (chamada,) = registro["post"]
    assert chamada["url"] == (
        "http://evolution_api:8080/message/sendText/ejc-escritorio"
    )
    assert chamada["headers"]["apikey"] == "chave-secreta"
    assert chamada["json"] == {"number": NUMERO_E164, "text": MENSAGEM}
    assert registro["init"][0]["timeout"] == 7.5


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("(31) 98888-7777", NUMERO_E164),   # formatado com DDD
        ("31988887777", NUMERO_E164),       # celular com DDD, sem DDI
        ("+55 31 98888-7777", NUMERO_E164),  # E.164 com "+"
        (NUMERO_E164, NUMERO_E164),         # já normalizado → intacto
        ("3133334444", "553133334444"),     # fixo com DDD
        ("351912345678", "351912345678"),   # DDI estrangeiro preservado
        ("123", None),
        ("", None),
        (None, None),
        ("sem digitos", None),
    ],
)
def test_normalizacao_de_telefone(entrada, esperado):
    assert ns.normalizar_telefone_br(entrada) == esperado


# ── Falhas de rede/HTTP nunca propagam ────────────────────────────────────────
async def test_http_400_retorna_false_sem_propagar(monkeypatch):
    _config_completa(monkeypatch)
    _httpx_falso(monkeypatch, resposta=_resposta(400))
    assert await ns.enviar_whatsapp(TELEFONE, MENSAGEM) is False


async def test_timeout_retorna_false_sem_propagar(monkeypatch):
    _config_completa(monkeypatch)
    _httpx_falso(monkeypatch, excecao=httpx.ConnectTimeout("estourou"))
    assert await ns.enviar_whatsapp(TELEFONE, MENSAGEM) is False


async def test_erro_inesperado_retorna_false_sem_propagar(monkeypatch):
    _config_completa(monkeypatch)
    _httpx_falso(monkeypatch, excecao=RuntimeError("boom"))
    assert await ns.enviar_whatsapp(TELEFONE, MENSAGEM) is False


# ── LGPD: log não pode conter telefone completo nem a mensagem ────────────────
@pytest.mark.parametrize("cenario", ["sucesso", "http", "rede"])
async def test_log_nao_vaza_telefone_nem_mensagem(monkeypatch, caplog, cenario):
    _config_completa(monkeypatch)
    if cenario == "sucesso":
        _httpx_falso(monkeypatch)
    elif cenario == "http":
        _httpx_falso(monkeypatch, resposta=_resposta(401))
    else:
        _httpx_falso(monkeypatch, excecao=httpx.ConnectError("dns"))

    with caplog.at_level(logging.DEBUG, logger=ns.logger.name):
        await ns.enviar_whatsapp(TELEFONE, MENSAGEM)

    texto = caplog.text
    assert texto.strip(), "o envio precisa deixar rastro de diagnóstico"
    assert NUMERO_E164 not in texto
    assert "98888-7777" not in texto
    assert "988887777" not in texto
    assert MENSAGEM not in texto
    assert "contestação" not in texto
    assert "***7777" in texto


# ── Disponibilidade do canal deixa de ser hard-coded ──────────────────────────
def test_canal_disponivel_com_flag_e_configuracao_completa():
    disponivel = channel_availability(
        Settings(
            _env_file=None,
            WHATSAPP_ENABLED=True,
            EVOLUTION_API_KEY="chave",
            EVOLUTION_API_URL="http://evolution_api:8080",
        )
    )
    assert disponivel.whatsapp is True


@pytest.mark.parametrize(
    "over",
    [
        {"WHATSAPP_ENABLED": False, "EVOLUTION_API_KEY": "chave"},
        {"WHATSAPP_ENABLED": True, "EVOLUTION_API_KEY": ""},
        {
            "WHATSAPP_ENABLED": True,
            "EVOLUTION_API_KEY": "chave",
            "EVOLUTION_API_URL": "",
        },
    ],
)
def test_canal_indisponivel_sem_flag_ou_sem_configuracao(over):
    disponivel = channel_availability(Settings(_env_file=None, **over))
    assert disponivel.whatsapp is False
