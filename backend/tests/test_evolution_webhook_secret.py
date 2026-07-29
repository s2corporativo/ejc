"""Regressão do segredo do webhook da Evolution (WhatsApp).

Achado (auditoria 2026-07-26): o secret era aceito também por query string
(`?token=`). URL vaza em access log do Nginx, em proxy reverso e no histórico do
painel da Evolution — o segredo fica registrado em texto em vários pontos fora
do controle do escritório (LGPD/segurança).

Contrato após a correção: o secret só é aceito em HEADER.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.routers import evolution_webhook as ev

SEGREDO = "segredo-de-webhook-forte"


def _request(headers: dict | None = None, query: dict | None = None):
    return SimpleNamespace(headers=headers or {}, query_params=query or {})


def test_secret_no_header_apikey_autoriza(monkeypatch):
    monkeypatch.setattr(ev, "WEBHOOK_SECRET", SEGREDO)
    assert ev._autorizado(_request(headers={"apikey": SEGREDO})) is True


def test_secret_no_header_x_webhook_token_autoriza(monkeypatch):
    monkeypatch.setattr(ev, "WEBHOOK_SECRET", SEGREDO)
    assert ev._autorizado(_request(headers={"x-webhook-token": SEGREDO})) is True


def test_secret_apenas_na_query_string_e_recusado(monkeypatch):
    """O achado: segredo em URL não autentica mais."""
    monkeypatch.setattr(ev, "WEBHOOK_SECRET", SEGREDO)
    assert ev._autorizado(_request(query={"token": SEGREDO})) is False


def test_sem_secret_algum_e_recusado(monkeypatch):
    monkeypatch.setattr(ev, "WEBHOOK_SECRET", SEGREDO)
    assert ev._autorizado(_request()) is False


def test_secret_errado_no_header_e_recusado(monkeypatch):
    monkeypatch.setattr(ev, "WEBHOOK_SECRET", SEGREDO)
    assert ev._autorizado(_request(headers={"apikey": "outro-valor"})) is False


def test_sem_secret_configurado_nada_autoriza(monkeypatch):
    """Sem `EVOLUTION_WEBHOOK_SECRET`, a rota recusa qualquer chamada."""
    monkeypatch.setattr(ev, "WEBHOOK_SECRET", "")
    assert ev._autorizado(_request(headers={"apikey": ""})) is False
    assert ev._autorizado(_request(headers={"apikey": "qualquer"})) is False
