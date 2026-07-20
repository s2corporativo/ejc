from __future__ import annotations

import pytest

from app.services import backup_drive_auth


_BACKUP_ENV = (
    "BACKUP_GOOGLE_DRIVE_AUTH_MODE",
    "BACKUP_GOOGLE_DRIVE_OAUTH_USER_FILE",
    "BACKUP_GOOGLE_DRIVE_OAUTH_USER_JSON",
    "BACKUP_GOOGLE_DRIVE_OAUTH_CLIENT_ID",
    "BACKUP_GOOGLE_DRIVE_OAUTH_CLIENT_SECRET",
    "BACKUP_GOOGLE_DRIVE_OAUTH_REFRESH_TOKEN",
    "BACKUP_GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE",
    "BACKUP_GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON",
)


def _clear(monkeypatch):
    for name in _BACKUP_ENV:
        monkeypatch.delenv(name, raising=False)


def test_auth_mode_invalido_falha_com_mensagem_acionavel(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("BACKUP_GOOGLE_DRIVE_AUTH_MODE", "qualquer")
    with pytest.raises(RuntimeError, match="BACKUP_GOOGLE_DRIVE_AUTH_MODE"):
        backup_drive_auth.auth_mode()


def test_service_account_exclusiva_e_fail_closed(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("BACKUP_GOOGLE_DRIVE_AUTH_MODE", "service_account")
    with pytest.raises(RuntimeError, match="service account"):
        backup_drive_auth.build_credentials()


def test_auto_prefere_service_account_dedicada(monkeypatch):
    _clear(monkeypatch)
    dedicada = object()
    monkeypatch.setattr(
        backup_drive_auth, "_service_account_dedicated", lambda: dedicada
    )
    monkeypatch.setattr(
        backup_drive_auth,
        "_oauth_dedicated",
        lambda: pytest.fail("OAuth não deveria ser consultado"),
    )
    monkeypatch.setattr(
        backup_drive_auth,
        "_inherited_credentials",
        lambda: pytest.fail("credencial herdada não deveria ser consultada"),
    )
    assert backup_drive_auth.build_credentials() is dedicada


def test_auto_herda_somente_quando_nao_ha_dedicada(monkeypatch):
    _clear(monkeypatch)
    herdada = object()
    monkeypatch.setattr(backup_drive_auth, "_service_account_dedicated", lambda: None)
    monkeypatch.setattr(backup_drive_auth, "_oauth_dedicated", lambda: None)
    monkeypatch.setattr(backup_drive_auth, "_inherited_credentials", lambda: herdada)
    assert backup_drive_auth.build_credentials() is herdada


def test_oauth_exclusivo_nao_cai_para_credencial_do_rag(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("BACKUP_GOOGLE_DRIVE_AUTH_MODE", "oauth")
    monkeypatch.setattr(backup_drive_auth, "_oauth_dedicated", lambda: None)
    monkeypatch.setattr(
        backup_drive_auth,
        "_inherited_credentials",
        lambda: pytest.fail("modo oauth deve ser fail-closed"),
    )
    with pytest.raises(RuntimeError, match="OAuth exclusiva"):
        backup_drive_auth.build_credentials()


def test_auth_status_nao_expoe_valores_secretos(monkeypatch):
    _clear(monkeypatch)
    segredo = '{"private_key":"SEGREDO-NUNCA-RETORNAR"}'
    monkeypatch.setenv("BACKUP_GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON", segredo)
    status = backup_drive_auth.auth_status()
    assert status["credencial_dedicada_configurada"] is True
    assert status["service_account_json_configurado"] is True
    assert "SEGREDO-NUNCA-RETORNAR" not in str(status)
