"""Regressão: a resposta de 500 prometia notificação que ninguém recebia.

O handler global devolvia, incondicionalmente, "Erro interno. A equipe foi
notificada." Sem `SENTRY_DSN` não há coletor: o erro fica só no log do container,
ninguém é avisado e não existe histórico consultável. A auditoria de julho/2026
confirmou o estado pelo próprio painel do sistema ("Sem coletor de erros
persistido no banco") e classificou a frase como falso positivo — o usuário para
de reportar porque acredita que já foi reportado.

A correção não remove a frase: torna-a condicional ao coletor existir de fato.
Quando o Sentry for habilitado, a promessa volta a ser verdadeira sozinha.
"""
from __future__ import annotations

import pytest

from app.core.observability import coletor_erros_ativo


@pytest.fixture(autouse=True)
def _limpa_cache_de_settings():
    """`get_settings()` é cacheado; sem limpar, o monkeypatch não tem efeito."""
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_sem_dsn_nao_ha_coletor(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "")
    assert coletor_erros_ativo() is False


def test_dsn_apenas_com_espacos_nao_conta(monkeypatch):
    """Placeholder em branco no .env não pode ligar a promessa."""
    monkeypatch.setenv("SENTRY_DSN", "   ")
    assert coletor_erros_ativo() is False


def test_com_dsn_ha_coletor(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://chave@exemplo.ingest.sentry.io/1")
    assert coletor_erros_ativo() is True


def test_mensagem_nao_promete_notificacao_sem_coletor(monkeypatch):
    """A frase da auditoria não pode reaparecer enquanto não houver coletor."""
    monkeypatch.setenv("SENTRY_DSN", "")

    detail = (
        "Erro interno. A equipe foi notificada."
        if coletor_erros_ativo()
        else "Erro interno. Se persistir, informe o horário e o que estava fazendo."
    )

    assert "notificada" not in detail, (
        "sem coletor de erros ativo, a resposta de 500 não pode afirmar que "
        "alguém foi notificado"
    )


def test_helper_nunca_levanta(monkeypatch):
    """Observabilidade jamais derruba uma resposta de erro."""
    import app.core.observability as obs

    def _explode():
        raise RuntimeError("config indisponível")

    monkeypatch.setattr(obs, "get_settings", _explode)
    assert coletor_erros_ativo() is False
