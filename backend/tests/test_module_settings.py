import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.routers.module_settings import (
    PROTECTED_MODULE_KEYS,
    _validate_module_key,
)
from app.schemas.system_module_settings import SystemModuleSettingUpdate


def test_module_key_is_normalized_and_restricted():
    assert _validate_module_key("  Minha-Funcionalidade  ") == "minha-funcionalidade"
    with pytest.raises(HTTPException):
        _validate_module_key("https://externo.example")


def test_disabled_requires_consistent_status_and_menu():
    valid = SystemModuleSettingUpdate(
        enabled=False,
        menu_visible=False,
        status="disabled",
        replacement_route="/casos",
        reason="Consolidado em Casos",
    )
    assert valid.status == "disabled"

    with pytest.raises(ValidationError):
        SystemModuleSettingUpdate(enabled=False, status="active")
    with pytest.raises(ValidationError):
        SystemModuleSettingUpdate(
            enabled=False,
            menu_visible=True,
            status="disabled",
        )


def test_hidden_module_remains_enabled_but_leaves_menu():
    hidden = SystemModuleSettingUpdate(
        enabled=True,
        menu_visible=False,
        status="hidden",
    )
    assert hidden.enabled is True
    assert hidden.menu_visible is False


def test_replacement_route_must_be_internal():
    with pytest.raises(ValidationError):
        SystemModuleSettingUpdate(replacement_route="https://example.com")
    with pytest.raises(ValidationError):
        SystemModuleSettingUpdate(replacement_route="//example.com")


def test_critical_modules_are_protected():
    assert {"dashboard", "configuracoes", "usuarios", "auditoria"}.issubset(
        PROTECTED_MODULE_KEYS
    )
