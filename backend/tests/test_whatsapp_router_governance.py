from __future__ import annotations

from fastapi import HTTPException
import pytest

from app.core.config import Settings
from app.routers import whatsapp as wr


def test_whatsapp_kill_switch_bloqueia_rotas_manuais(monkeypatch):
    settings = Settings(_env_file=None, APP_ENV="development", WHATSAPP_ENABLED=False)
    monkeypatch.setattr(wr, "get_settings", lambda: settings)

    with pytest.raises(HTTPException) as exc:
        wr._exigir_whatsapp_habilitado()

    assert exc.value.status_code == 503
    assert "desabilitado" in str(exc.value.detail).lower()


def test_evolution_config_resolve_settings_vigentes(monkeypatch):
    settings = Settings(
        _env_file=None,
        APP_ENV="development",
        WHATSAPP_ENABLED=True,
        EVOLUTION_API_URL="http://evolution_api:8080/",
        EVOLUTION_API_KEY="chave-atual",
        EVOLUTION_INSTANCE="ejc-escritorio",
        EVOLUTION_TIMEOUT=7.0,
    )
    monkeypatch.setattr(wr, "get_settings", lambda: settings)
    monkeypatch.delenv("EVOLUTION_INSTANCE_KEY", raising=False)

    base, key, instance, instance_key, timeout = wr._evolution_config()

    assert base == "http://evolution_api:8080"
    assert key == "chave-atual"
    assert instance == "ejc-escritorio"
    assert instance_key == "chave-atual"
    assert timeout == 7.0


def test_evolution_config_falha_fechado_sem_configuracao(monkeypatch):
    settings = Settings(
        _env_file=None,
        APP_ENV="development",
        WHATSAPP_ENABLED=True,
        EVOLUTION_API_URL="",
        EVOLUTION_API_KEY="",
        EVOLUTION_INSTANCE="ejc-escritorio",
    )
    monkeypatch.setattr(wr, "get_settings", lambda: settings)
    monkeypatch.delenv("EVOLUTION_URL", raising=False)
    monkeypatch.delenv("EVOLUTION_KEY", raising=False)

    with pytest.raises(HTTPException) as exc:
        wr._evolution_config()

    assert exc.value.status_code == 503
