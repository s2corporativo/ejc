"""Revogação/rotação de credencial Groq com client JÁ CONSTRUÍDO (achado da
revisão de segurança sobre o fix de bypass de revogação, 18/08 — mesma classe
de bug que anthropic_provider tinha).

groq_provider.get_client() cacheava o client do SDK por PROCESSO
(`--workers 1`), com a api_key gravada DENTRO do objeto no momento da
construção. Revogar a credencial pelo Cofre zerava Settings.GROQ_API_KEY, mas
o client já construído seguia mandando a chave ANTIGA em toda chamada até o
restart do container — _api_key não é reavaliada depois que o singleton
existe.
"""
from __future__ import annotations

import pytest
from groq import AsyncGroq

from app.core.config import get_settings
from app.services.providers import groq_provider as gp


def _fake_groq_sdk(monkeypatch):
    class _FakeClient:
        def __init__(self, **kwargs):
            self.api_key = kwargs.get("api_key")

    monkeypatch.setattr("app.services.providers.groq_provider.AsyncGroq", _FakeClient)
    monkeypatch.setattr(gp, "_client", None)
    monkeypatch.setattr(gp, "_client_api_key", None)


def test_client_ja_construido_e_revogado_nao_continua_servindo_a_chave_velha(monkeypatch):
    _fake_groq_sdk(monkeypatch)
    monkeypatch.setattr(gp.settings, "GROQ_API_KEY", "gsk-VALIDA-inicial")

    client1 = gp.get_client()
    assert client1.api_key == "gsk-VALIDA-inicial"

    monkeypatch.setattr(gp.settings, "GROQ_API_KEY", "")
    with pytest.raises(RuntimeError, match="GROQ_API_KEY não configurada"):
        gp.get_client()
    assert gp._client is None  # fail-closed: não reaproveita o client velho


def test_rotacao_de_credencial_reconstroi_o_client_com_a_chave_nova(monkeypatch):
    _fake_groq_sdk(monkeypatch)
    monkeypatch.setattr(gp.settings, "GROQ_API_KEY", "gsk-chave-A")
    client1 = gp.get_client()

    monkeypatch.setattr(gp.settings, "GROQ_API_KEY", "gsk-chave-B")
    client2 = gp.get_client()

    assert client2.api_key == "gsk-chave-B"
    assert client2 is not client1


def test_sem_mudanca_de_chave_o_client_e_reaproveitado(monkeypatch):
    _fake_groq_sdk(monkeypatch)
    monkeypatch.setattr(gp.settings, "GROQ_API_KEY", "gsk-estavel")

    assert gp.get_client() is gp.get_client()
