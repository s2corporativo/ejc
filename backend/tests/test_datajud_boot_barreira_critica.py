from __future__ import annotations

import importlib

import pytest


def test_instalar_mantem_barreira_se_scheduler_opcional_falhar(monkeypatch):
    patch = importlib.import_module("app.services.datajud_cognitive_patch")
    monkeypatch.setattr(patch, "_INSTALADO", False)

    chamadas = []
    monkeypatch.setattr(patch, "_instalar_wrappers", lambda: chamadas.append("barreira"))
    monkeypatch.setattr(patch, "_registrar_categoria_restrita", lambda: chamadas.append("categoria"))

    def scheduler_indisponivel():
        chamadas.append("scheduler")
        raise RuntimeError("indisponível")

    monkeypatch.setattr(patch, "_registrar_job", scheduler_indisponivel)

    patch.instalar()

    assert chamadas == ["barreira", "categoria", "scheduler"]
    assert patch._INSTALADO is True


def test_instalar_falha_fechado_se_barreira_critica_falhar(monkeypatch):
    patch = importlib.import_module("app.services.datajud_cognitive_patch")
    monkeypatch.setattr(patch, "_INSTALADO", False)

    def barreira_falha():
        raise RuntimeError("wrapper crítico indisponível")

    monkeypatch.setattr(patch, "_instalar_wrappers", barreira_falha)

    with pytest.raises(RuntimeError, match="wrapper crítico"):
        patch.instalar()

    assert patch._INSTALADO is False


def test_event_subscriber_trata_datajud_como_barreira_critica():
    import inspect
    from app.services import event_subscribers

    fonte = inspect.getsource(event_subscribers._install_datajud_cognitive_feed)
    assert "logger.critical" in fonte
    assert "raise RuntimeError" in fonte
