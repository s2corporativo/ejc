"""two_factor_enabled (SYS-007) — fail-secure: ligado por padrão em produção.

Sem banco. Exercita apenas a decisão do kill-switch global do 2FA em função de
APP_ENV e do override break-glass TWO_FACTOR_AUTH_ENABLED.
"""
from app.core.two_factor_policy import two_factor_enabled


def test_producao_sem_flag_liga_por_padrao(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("TWO_FACTOR_AUTH_ENABLED", raising=False)
    assert two_factor_enabled() is True


def test_break_glass_desliga_ate_em_producao(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("TWO_FACTOR_AUTH_ENABLED", "false")
    assert two_factor_enabled() is False


def test_fora_de_producao_desligado_por_padrao(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("TWO_FACTOR_AUTH_ENABLED", raising=False)
    assert two_factor_enabled() is False


def test_override_liga_fora_de_producao(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("TWO_FACTOR_AUTH_ENABLED", "true")
    assert two_factor_enabled() is True
