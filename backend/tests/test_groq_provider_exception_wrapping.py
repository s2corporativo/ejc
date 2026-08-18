"""groq_provider.chat não embrulhava a exceção do SDK — era o único dos
quatro providers sem essa barreira (auditoria de segurança, 18/08). O SDK
pode ecoar trecho da requisição na mensagem de erro (corpo malformado,
conteúdo enviado); sem embrulhar, isso chegava cru a quem loga/observa a
falha. Mesmo padrão de anthropic_provider/maritaca_provider: mensagem CURTA
e segura (tipo + status), `from None` corta a cadeia original.
"""
from __future__ import annotations

import pytest
from groq import GroqError

from app.services.providers import groq_provider as gp


class _FakeCompletions:
    def __init__(self, excecao):
        self._excecao = excecao

    async def create(self, **kwargs):
        raise self._excecao


class _FakeChat:
    def __init__(self, excecao):
        self.completions = _FakeCompletions(excecao)


class _FakeClient:
    def __init__(self, excecao):
        self.chat = _FakeChat(excecao)


async def test_erro_do_sdk_vira_runtimeerror_curto_sem_ecoar_conteudo(monkeypatch):
    segredo_do_request = "CPF 123.456.789-09 do cliente Fulano de Tal"
    excecao_do_sdk = GroqError(f"erro ao processar: {segredo_do_request}")
    monkeypatch.setattr(gp, "get_client", lambda: _FakeClient(excecao_do_sdk))

    with pytest.raises(RuntimeError) as exc:
        await gp.chat(messages=[{"role": "user", "content": "oi"}])

    msg = str(exc.value)
    assert "Groq API falhou" in msg
    assert "GroqError" in msg
    # A mensagem original do SDK (que pode ecoar dado do request) NÃO vaza.
    assert segredo_do_request not in msg
    assert "123.456.789-09" not in msg


async def test_erro_com_status_code_inclui_o_status(monkeypatch):
    excecao_do_sdk = GroqError("falhou")
    excecao_do_sdk.status_code = 401  # revogação/chave inválida

    monkeypatch.setattr(gp, "get_client", lambda: _FakeClient(excecao_do_sdk))

    with pytest.raises(RuntimeError, match="HTTP 401"):
        await gp.chat(messages=[{"role": "user", "content": "oi"}])


async def test_erro_sem_status_code_nao_quebra(monkeypatch):
    """GroqError puro (sem status_code) não pode gerar AttributeError."""
    excecao_do_sdk = GroqError("erro genérico")
    monkeypatch.setattr(gp, "get_client", lambda: _FakeClient(excecao_do_sdk))

    with pytest.raises(RuntimeError, match="Groq API falhou"):
        await gp.chat(messages=[{"role": "user", "content": "oi"}])
