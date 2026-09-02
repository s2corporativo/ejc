from __future__ import annotations

import pytest


def test_instalacao_degrada_job_opcional_sem_desativar_barreira(monkeypatch):
    from app.services import datajud_cognitive_patch as patch

    chamadas: list[str] = []
    monkeypatch.setattr(patch, "_INSTALADO", False)
    monkeypatch.setattr(
        patch,
        "_instalar_wrappers",
        lambda: chamadas.append("barreira"),
    )
    monkeypatch.setattr(
        patch,
        "_registrar_categoria_restrita",
        lambda: chamadas.append("categoria"),
    )

    def _job_indisponivel():
        chamadas.append("job")
        raise RuntimeError("scheduler indisponível no ambiente de teste")

    monkeypatch.setattr(patch, "_registrar_job", _job_indisponivel)

    patch.instalar()

    assert chamadas == ["barreira", "categoria", "job"]
    assert patch._INSTALADO is True


def test_falha_da_barreira_critica_continua_fail_closed(monkeypatch):
    from app.services import datajud_cognitive_patch as patch

    monkeypatch.setattr(patch, "_INSTALADO", False)

    def _barreira_indisponivel():
        raise RuntimeError("não foi possível neutralizar criador legado")

    monkeypatch.setattr(patch, "_instalar_wrappers", _barreira_indisponivel)

    with pytest.raises(RuntimeError, match="neutralizar criador legado"):
        patch.instalar()

    assert patch._INSTALADO is False
