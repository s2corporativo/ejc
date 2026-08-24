"""Regressão do item V2-1.4 (plano-mestre): a resposta de erro 500 só pode
prometer "a equipe foi notificada" quando existe de fato um coletor de erros
(Sentry) recebendo esse processo. Sem `SENTRY_DSN`, o erro fica só no log do
container -- ninguém é avisado e não há histórico consultável. Afirmar
notificação nesse estado faz o usuário esperar um retorno que nunca vem
(achado da auditoria de julho/2026 em `/analytics/roi-por-area`).

O handler (`app.main.global_exception_handler`) já resolve isso lendo
`coletor_erros_ativo()` -- este arquivo apenas trava o comportamento com
teste de regressão, que faltava.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.main as main_module


def _app_com_rota_quebrada() -> FastAPI:
    """App isolado (não sobe os 163 routers de produção): registra o MESMO
    handler global de app/main.py contra uma rota que sempre explode."""
    app = FastAPI()
    app.add_exception_handler(Exception, main_module.global_exception_handler)

    @app.get("/explode")
    async def explode():
        raise RuntimeError("falha simulada")

    return app


def test_sem_coletor_ativo_nao_promete_notificacao(monkeypatch):
    monkeypatch.setattr(main_module, "coletor_erros_ativo", lambda: False)
    client = TestClient(_app_com_rota_quebrada(), raise_server_exceptions=False)

    r = client.get("/explode")

    assert r.status_code == 500
    detail = r.json()["detail"]
    assert "equipe foi notificada" not in detail
    assert "informe o horário" in detail


def test_com_coletor_ativo_promete_notificacao(monkeypatch):
    monkeypatch.setattr(main_module, "coletor_erros_ativo", lambda: True)
    client = TestClient(_app_com_rota_quebrada(), raise_server_exceptions=False)

    r = client.get("/explode")

    assert r.status_code == 500
    assert r.json()["detail"] == "Erro interno. A equipe foi notificada."


def test_resposta_de_erro_nunca_vaza_stack_trace(monkeypatch):
    monkeypatch.setattr(main_module, "coletor_erros_ativo", lambda: False)
    client = TestClient(_app_com_rota_quebrada(), raise_server_exceptions=False)

    r = client.get("/explode")

    corpo = r.text
    assert "RuntimeError" not in corpo
    assert "falha simulada" not in corpo
    assert "Traceback" not in corpo
