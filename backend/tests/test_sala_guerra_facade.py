from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.routing import APIRoute

from app.routers.sala_de_guerra_facade import (
    SimulacaoAdversarialRequest,
    VisualLawRequest,
    baixar_visual_law_do_caso,
    gerar_visual_law_do_caso,
    simular_contestacao_do_caso,
)


@pytest.mark.asyncio
async def test_simulacao_delega_ao_pipeline_v3_com_case_id(monkeypatch):
    from app.routers import sala_de_guerra_v3

    captured = {}

    async def fake_simular_war_room(*, payload, db, cu):
        captured.update(payload=payload, db=db, cu=cu)
        return "resultado adversarial"

    monkeypatch.setattr(sala_de_guerra_v3, "simular_war_room", fake_simular_war_room)
    db = object()
    user = SimpleNamespace(id="u1")
    result = await simular_contestacao_do_caso(
        "case-1",
        SimulacaoAdversarialRequest(peticao="Tese detalhada para teste adversarial"),
        db,
        user,
    )

    assert result == "resultado adversarial"
    assert captured["payload"] == {
        "peticao": "Tese detalhada para teste adversarial",
        "case_id": "case-1",
    }
    assert captured["db"] is db
    assert captured["cu"] is user


@pytest.mark.asyncio
async def test_visual_law_reescreve_apenas_url_de_download(monkeypatch):
    from app.routers import sala_de_guerra_v3

    captured = {}

    async def fake_gerar_visual_law(*, case_id, payload, db, cu):
        captured.update(case_id=case_id, payload=payload, db=db, cu=cu)
        return {
            "download_url": f"/sala-de-guerra-v3/visual-law/{case_id}/download",
            "versao": 1,
        }

    monkeypatch.setattr(sala_de_guerra_v3, "gerar_visual_law", fake_gerar_visual_law)
    db = object()
    user = SimpleNamespace(id="u1")
    result = await gerar_visual_law_do_caso(
        "case-1",
        VisualLawRequest(eventos=[{"data": "01/01/2026", "evento": "Marco"}]),
        db,
        user,
    )

    assert captured["case_id"] == "case-1"
    assert captured["payload"] == {
        "eventos": [{"data": "01/01/2026", "evento": "Marco"}]
    }
    assert result["versao"] == 1
    assert result["download_url"] == (
        "/cases/case-1/sala-de-guerra/visual-law/download"
    )


@pytest.mark.asyncio
async def test_download_delega_ao_mesmo_arquivo_v3(monkeypatch):
    from app.routers import sala_de_guerra_v3

    sentinel = object()

    async def fake_download_visual_law(*, case_id, db, cu):
        assert case_id == "case-1"
        return sentinel

    monkeypatch.setattr(
        sala_de_guerra_v3,
        "download_visual_law",
        fake_download_visual_law,
    )
    assert await baixar_visual_law_do_caso(
        "case-1", object(), SimpleNamespace(id="u1")
    ) is sentinel


def test_app_monta_rotas_canonicas_e_preserva_legadas():
    from app.main import app

    paths = {
        route.path
        for route in app.routes
        if isinstance(route, APIRoute)
    }
    assert "/api/cases/{case_id}/sala-de-guerra/simular-contestacao" in paths
    assert "/api/cases/{case_id}/sala-de-guerra/visual-law" in paths
    assert "/api/cases/{case_id}/sala-de-guerra/visual-law/download" in paths

    assert "/api/sala-de-guerra-v3/war-room/simular" in paths
    assert "/api/sala-de-guerra-v3/visual-law/{case_id}" in paths
    assert "/api/sala-de-guerra-v3/visual-law/{case_id}/download" in paths
    assert "/api/sala-de-guerra-v3/sentinela/auditoria" in paths


def test_facade_nao_duplica_pipeline_de_ia_ou_pdf():
    source = (
        Path(__file__).parents[1] / "app/routers/sala_de_guerra_facade.py"
    ).read_text(encoding="utf-8")
    assert "from app.services.war_room import" not in source
    assert "from app.services.visual_law_pdf import" not in source
    assert "registrar_ai_log" not in source
    assert "simular_war_room" in source
    assert "gerar_visual_law" in source
    assert "download_visual_law" in source
