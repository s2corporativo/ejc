"""Regressão da desativação temporária e reversível do 2FA."""
from __future__ import annotations

from app.core.auth_middleware import _totp_management_temporarily_disabled
from app.core.config import get_settings
from app.core.two_factor_policy import apply_runtime_policy, two_factor_enabled
from app.models.user import User, UserRole


def _user_with_totp() -> User:
    return User(
        id="00000000-0000-0000-0000-000000000001",
        email="socio@example.test",
        full_name="Sócio Teste",
        hashed_password="hash-test-only",
        role=UserRole.socio,
        is_active=True,
        totp_enabled=True,
        totp_secret="SEGREDO_PRESERVADO",
    )


def test_2fa_nasce_temporariamente_desativado(monkeypatch):
    monkeypatch.delenv("TWO_FACTOR_AUTH_ENABLED", raising=False)
    assert two_factor_enabled() is False


def test_politica_suprime_flag_apenas_no_objeto_e_preserva_segredo(monkeypatch):
    monkeypatch.setenv("TWO_FACTOR_AUTH_ENABLED", "false")
    user = _user_with_totp()
    apply_runtime_policy(user)

    assert user.totp_enabled is False
    assert user.totp_secret == "SEGREDO_PRESERVADO"


def test_reativacao_respeita_valor_persistido(monkeypatch):
    monkeypatch.setenv("TWO_FACTOR_AUTH_ENABLED", "true")
    user = _user_with_totp()
    apply_runtime_policy(user)

    assert user.totp_enabled is True
    assert user.totp_secret == "SEGREDO_PRESERVADO"


def test_papeis_obrigatorios_ficam_vazios_no_modo_temporario():
    # O módulo de política ajusta o mesmo Settings cacheado usado por login e
    # refresh, impedindo emissão de token limitado ao setup obrigatório.
    assert get_settings().require_2fa_roles_list == []


def test_gestao_totp_fica_bloqueada_sem_alterar_login(monkeypatch):
    monkeypatch.setenv("TWO_FACTOR_AUTH_ENABLED", "false")

    assert _totp_management_temporarily_disabled("/api/auth/totp/setup") is True
    assert _totp_management_temporarily_disabled("/api/v1/auth/totp/verificar") is True
    assert _totp_management_temporarily_disabled("/api/auth/totp/desativar") is True
    assert _totp_management_temporarily_disabled("/api/auth/login") is False


def test_gestao_totp_volta_com_reativacao(monkeypatch):
    monkeypatch.setenv("TWO_FACTOR_AUTH_ENABLED", "true")
    assert _totp_management_temporarily_disabled("/api/auth/totp/setup") is False
