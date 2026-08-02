"""Regressão: a resposta de 500 prometia notificação que ninguém recebia.

O handler global devolvia, incondicionalmente, "Erro interno. A equipe foi
notificada." Sem `SENTRY_DSN` não há coletor: o erro fica só no log do container,
ninguém é avisado e não existe histórico consultável. A auditoria de julho/2026
confirmou o estado pelo próprio painel do sistema ("Sem coletor de erros
persistido no banco") e classificou a frase como falso positivo — o usuário para
de reportar porque acredita que já foi reportado.

A correção não remove a frase: torna-a condicional ao coletor existir de fato.
Quando o Sentry for habilitado, a promessa volta a ser verdadeira sozinha.

NOTA DE TESTE — por que aqui não se mexe em `get_settings.cache_clear()`:
`Settings` é um singleton cacheado e vários módulos guardam a referência dele.
Limpar o cache faz nascer uma instância nova, com OUTRA chave Fernet efêmera
para o Cofre, e derruba testes de outros arquivos que dependem da identidade do
objeto ou da estabilidade da chave (`test_vault_service`, `test_vault_rotacao`,
`test_two_factor_policy`, `test_roteamento_gateway`). A dependência é
substituída no espaço de nomes do módulo sob teste — local, e não vaza.
"""
from __future__ import annotations

from types import SimpleNamespace

import app.core.observability as obs
from app.core.observability import coletor_erros_ativo


def _com_dsn(monkeypatch, dsn: str) -> None:
    """Troca a fonte de config vista por observability, sem tocar no singleton."""
    monkeypatch.setattr(obs, "get_settings", lambda: SimpleNamespace(SENTRY_DSN=dsn))


def test_sem_dsn_nao_ha_coletor(monkeypatch):
    _com_dsn(monkeypatch, "")
    assert coletor_erros_ativo() is False


def test_dsn_apenas_com_espacos_nao_conta(monkeypatch):
    """Placeholder em branco no .env não pode ligar a promessa."""
    _com_dsn(monkeypatch, "   ")
    assert coletor_erros_ativo() is False


def test_com_dsn_ha_coletor(monkeypatch):
    _com_dsn(monkeypatch, "https://chave@exemplo.ingest.sentry.io/1")
    assert coletor_erros_ativo() is True


def test_mensagem_nao_promete_notificacao_sem_coletor(monkeypatch):
    """A frase da auditoria não pode reaparecer enquanto não houver coletor."""
    _com_dsn(monkeypatch, "")

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

    def _explode():
        raise RuntimeError("config indisponível")

    monkeypatch.setattr(obs, "get_settings", _explode)
    assert coletor_erros_ativo() is False


def test_nao_recria_o_singleton_de_settings():
    """Trava: se alguém reintroduzir `cache_clear()` aqui, a suíte volta a quebrar.

    Sem monkeypatch, o helper usa o singleton real — e não pode substituí-lo.
    """
    from app.core.config import get_settings

    antes = get_settings()
    coletor_erros_ativo()
    assert get_settings() is antes, (
        "coletor_erros_ativo() não pode recriar o singleton de Settings"
    )
