import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.routers import whatsapp as wa


def test_router_whatsapp_respeita_kill_switch(monkeypatch):
    monkeypatch.setattr(
        wa, "get_settings",
        lambda: Settings(
            _env_file=None,
            WHATSAPP_ENABLED=False,
            EVOLUTION_API_URL="http://evolution_api:8080",
            EVOLUTION_API_KEY="x",
            EVOLUTION_INSTANCE="ejc-escritorio",
        ),
    )
    with pytest.raises(HTTPException) as exc:
        wa._config_evolution()
    assert exc.value.status_code == 503


def test_router_whatsapp_exige_configuracao_completa(monkeypatch):
    monkeypatch.setattr(
        wa, "get_settings",
        lambda: Settings(
            _env_file=None,
            WHATSAPP_ENABLED=True,
            EVOLUTION_API_URL="http://evolution_api:8080",
            EVOLUTION_API_KEY="",
            EVOLUTION_INSTANCE="ejc-escritorio",
        ),
    )
    with pytest.raises(HTTPException) as exc:
        wa._config_evolution()
    assert exc.value.status_code == 503


async def test_status_nao_engole_kill_switch(monkeypatch):
    async def bloqueado(_path):
        raise HTTPException(503, "canal desligado")

    monkeypatch.setattr(wa, "_evo_get", bloqueado)
    monkeypatch.setattr(wa, "_instance", lambda: "ejc-escritorio")
    with pytest.raises(HTTPException) as exc:
        await wa.get_status(current_user=None)
    assert exc.value.status_code == 503


async def test_chats_nao_engole_kill_switch(monkeypatch):
    async def bloqueado(_path, _body):
        raise HTTPException(503, "canal desligado")

    monkeypatch.setattr(wa, "_evo_post", bloqueado)
    monkeypatch.setattr(wa, "_instance", lambda: "ejc-escritorio")
    with pytest.raises(HTTPException) as exc:
        await wa.list_chats(limit=20, current_user=None)
    assert exc.value.status_code == 503
