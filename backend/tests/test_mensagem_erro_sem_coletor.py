"""Regressão: a resposta de 500 prometia notificação que ninguém recebia.

O handler global devolvia, incondicionalmente, "Erro interno. A equipe foi
notificada." Sem coletor de erros persistido, ninguém é avisado e não existe
histórico consultável. A auditoria de julho/2026 confirmou o estado pelo
próprio painel do sistema ("Sem coletor de erros persistido no banco") e
classificou a frase como falso positivo — o usuário para de reportar porque
acredita que já foi reportado.

Issue #761 removeu o Sentry (único coletor de erros que o EJC já teve): não
há mais NENHUM coletor possível, então a mensagem do handler é FIXA — a
versão "sem coletor" (orienta o usuário a informar o horário do erro).

NOTA DE TESTE — por que aqui não se mexe em `get_settings.cache_clear()`:
`Settings` é um singleton cacheado e vários módulos guardam a referência dele.
Limpar o cache faz nascer uma instância nova, com OUTRA chave Fernet efêmera
para o Cofre, e derruba testes de outros arquivos que dependem da identidade do
objeto ou da estabilidade da chave (`test_vault_service`, `test_vault_rotacao`,
`test_two_factor_policy`, `test_roteamento_gateway`).
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest


def _requisicao_fake():
    return SimpleNamespace(url=SimpleNamespace(path="/api/teste-500"))


async def _detail_do_handler() -> str:
    main = pytest.importorskip(
        "app.main", reason="app.main exige dependências completas (CI)"
    )
    resposta = await main.global_exception_handler(
        _requisicao_fake(), RuntimeError("explosão de teste")
    )
    assert resposta.status_code == 500
    return json.loads(resposta.body)["detail"]


async def test_handler_global_nao_promete_notificacao():
    """A frase da auditoria não pode reaparecer — não há coletor de erros."""
    detail = await _detail_do_handler()
    assert "notificada" not in detail, (
        "sem coletor de erros no sistema, a resposta de 500 não pode afirmar "
        "que alguém foi notificado"
    )
    assert "informe o horário" in detail


async def test_handler_global_mensagem_e_sempre_a_mesma():
    """A mensagem é fixa: não há mais ramo condicional (Sentry removido)."""
    d1 = await _detail_do_handler()
    d2 = await _detail_do_handler()
    assert d1 == d2 == (
        "Erro interno. Se persistir, informe o horário e o que estava fazendo."
    )
