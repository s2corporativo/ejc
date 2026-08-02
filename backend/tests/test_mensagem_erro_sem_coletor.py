"""Regressão: a resposta de 500 prometia notificação que ninguém recebia.

O handler global devolvia, incondicionalmente, "Erro interno. A equipe foi
notificada." Sem `SENTRY_DSN` não há coletor: o erro fica só no log do container,
ninguém é avisado e não existe histórico consultável. A auditoria de julho/2026
confirmou o estado pelo próprio painel do sistema ("Sem coletor de erros
persistido no banco") e classificou a frase como falso positivo — o usuário para
de reportar porque acredita que já foi reportado.

A correção não remove a frase: torna-a condicional ao coletor existir DE FATO.
Review do PR #619 apertou dois parafusos deste arquivo:

1. `coletor_erros_ativo()` reporta o estado real do `sentry_sdk.init()` (flag
   `_sentry_inicializado`), não a mera presença de DSN — DSN malformado ou
   falha de import não podem manter a promessa de pé.
2. O teste da mensagem exercita `global_exception_handler` de `app.main`, e
   não uma reconstrução local da condicional — reverter o handler quebra aqui.

NOTA DE TESTE — por que aqui não se mexe em `get_settings.cache_clear()`:
`Settings` é um singleton cacheado e vários módulos guardam a referência dele.
Limpar o cache faz nascer uma instância nova, com OUTRA chave Fernet efêmera
para o Cofre, e derruba testes de outros arquivos que dependem da identidade do
objeto ou da estabilidade da chave (`test_vault_service`, `test_vault_rotacao`,
`test_two_factor_policy`, `test_roteamento_gateway`). A dependência é
substituída no espaço de nomes do módulo sob teste — local, e não vaza.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import app.core.observability as obs
from app.core.observability import coletor_erros_ativo


def _config(dsn: str) -> SimpleNamespace:
    return SimpleNamespace(
        SENTRY_DSN=dsn,
        SENTRY_ENVIRONMENT="test",
        APP_ENV="development",
        SENTRY_TRACES_SAMPLE_RATE=0.0,
    )


def _inicializar_com(monkeypatch, dsn: str) -> None:
    """Roda o init REAL com a config vista por observability trocada.

    O flag `_sentry_inicializado` também é monkeypatchado para que o estado
    não vaze entre testes (restauração automática).
    """
    monkeypatch.setattr(obs, "_sentry_inicializado", False)
    monkeypatch.setattr(obs, "get_settings", lambda: _config(dsn))
    obs.init_sentry()


# ── coletor_erros_ativo reflete o estado real do init ────────────────────────

def test_sem_dsn_nao_ha_coletor(monkeypatch):
    _inicializar_com(monkeypatch, "")
    assert coletor_erros_ativo() is False


def test_dsn_apenas_com_espacos_nao_conta(monkeypatch):
    """Placeholder em branco no .env não pode ligar a promessa."""
    _inicializar_com(monkeypatch, "   ")
    assert coletor_erros_ativo() is False


def test_com_dsn_valido_ha_coletor(monkeypatch):
    pytest.importorskip("sentry_sdk")
    _inicializar_com(monkeypatch, "https://chave@exemplo.ingest.sentry.io/1")
    assert coletor_erros_ativo() is True


def test_dsn_malformado_nao_liga_a_promessa(monkeypatch):
    """DSN preenchido mas inválido: o init falha (engolido) e o coletor segue
    inexistente — presença de configuração não é coletor funcionando."""
    pytest.importorskip("sentry_sdk")
    _inicializar_com(monkeypatch, "isto-nao-e-um-dsn")
    assert coletor_erros_ativo() is False


def test_init_nunca_levanta_e_nao_liga_o_coletor(monkeypatch):
    """Observabilidade jamais derruba o boot; falha de config = sem coletor."""

    def _explode():
        raise RuntimeError("config indisponível")

    monkeypatch.setattr(obs, "_sentry_inicializado", False)
    monkeypatch.setattr(obs, "get_settings", _explode)
    obs.init_sentry()  # não pode levantar
    assert coletor_erros_ativo() is False


def test_nao_recria_o_singleton_de_settings():
    """Trava: se alguém reintroduzir `cache_clear()` aqui, a suíte volta a quebrar.

    Sem monkeypatch, o helper usa o estado real do módulo — e não pode tocar
    no singleton de Settings.
    """
    from app.core.config import get_settings

    antes = get_settings()
    coletor_erros_ativo()
    assert get_settings() is antes, (
        "coletor_erros_ativo() não pode recriar o singleton de Settings"
    )


# ── a mensagem sai do HANDLER REAL, não de uma reconstrução local ────────────

def _requisicao_fake():
    return SimpleNamespace(url=SimpleNamespace(path="/api/teste-500"))


async def _detail_do_handler(monkeypatch, coletor: bool) -> str:
    main = pytest.importorskip(
        "app.main", reason="app.main exige dependências completas (CI)"
    )
    # O handler consulta o nome importado no namespace de app.main.
    monkeypatch.setattr(main, "coletor_erros_ativo", lambda: coletor)
    resposta = await main.global_exception_handler(
        _requisicao_fake(), RuntimeError("explosão de teste")
    )
    assert resposta.status_code == 500
    return json.loads(resposta.body)["detail"]


async def test_handler_global_nao_promete_notificacao_sem_coletor(monkeypatch):
    """A frase da auditoria não pode reaparecer enquanto não houver coletor."""
    detail = await _detail_do_handler(monkeypatch, coletor=False)
    assert "notificada" not in detail, (
        "sem coletor de erros ativo, a resposta de 500 não pode afirmar que "
        "alguém foi notificado"
    )
    assert "informe o horário" in detail


async def test_handler_global_promete_notificacao_com_coletor(monkeypatch):
    """Com coletor real ativo, a promessa volta a ser verdadeira — e volta só."""
    detail = await _detail_do_handler(monkeypatch, coletor=True)
    assert "A equipe foi notificada" in detail
