import pytest

from app.services import crawler_precedentes as cp


@pytest.mark.asyncio
async def test_agregador_consolida_fontes_e_dedup(monkeypatch):
    async def fake_lexml(termo, pagina, por_pagina):
        return {
            "status": "success",
            "fonte": "lexml",
            "total": 1,
            "precedentes": [{
                "titulo": "Tema dano moral",
                "ementa": "Ementa sobre dano moral repetida",
                "tribunal": "STJ",
                "numero_acordao": "123",
                "fonte": "LexML",
            }],
        }

    async def fake_tjmg(termo, pagina, por_pagina):
        return {
            "status": "success",
            "fonte": "tjmg",
            "total": 1,
            "precedentes": [{
                "titulo": "Tema dano moral duplicado",
                "ementa": "Outra ementa",
                "tribunal": "STJ",
                "numero_acordao": "123",
                "fonte": "TJMG",
            }],
        }

    monkeypatch.setattr(cp, "_buscar_lexml", fake_lexml)
    monkeypatch.setattr(cp, "_buscar_tjmg", fake_tjmg)

    out = await cp.buscar_precedentes("dano moral", fontes=["lexml", "tjmg"])
    assert out["status"] == "success"
    assert out["total_encontrado"] == 1
    assert set(out["fontes"].keys()) == {"lexml", "tjmg"}


@pytest.mark.asyncio
async def test_stj_stf_nao_simulam_success():
    out = await cp.buscar_precedentes("recurso especial", fontes=["stj", "stf"])
    assert out["status"] == "erro"
    assert out["total_encontrado"] == 0
    assert out["fontes"]["stj"]["status"] == "nao_implementado"
    assert out["fontes"]["stf"]["status"] == "nao_implementado"


@pytest.mark.asyncio
async def test_fontes_invalidas_caem_no_default(monkeypatch):
    called = []

    async def fake_lexml(termo, pagina, por_pagina):
        called.append("lexml")
        return {"status": "success", "fonte": "lexml", "total": 0, "precedentes": []}

    async def fake_tjmg(termo, pagina, por_pagina):
        called.append("tjmg")
        return {"status": "success", "fonte": "tjmg", "total": 0, "precedentes": []}

    monkeypatch.setattr(cp, "_buscar_lexml", fake_lexml)
    monkeypatch.setattr(cp, "_buscar_tjmg", fake_tjmg)

    out = await cp.buscar_precedentes("contrato", fontes=["invalida"])
    assert out["status"] == "success"
    assert called == ["lexml", "tjmg"]


@pytest.mark.asyncio
async def test_router_de_precedentes_e_registrado_explicitamente():
    """Onda 3 §4.1: registro explícito em app/main.py no lugar do patch em
    event_subscribers — mesmo path final."""
    from pathlib import Path

    from app.main import app

    montadas = {getattr(r, "path", "") for r in app.routes}
    assert "/api/jurisprudencia-externa/precedentes/buscar" in montadas

    main_src = Path("app/main.py").read_text(encoding="utf-8")
    assert 'precedentes_jurisprudencia.router, prefix=API + "/jurisprudencia-externa"' in main_src

    subscribers = Path("app/services/event_subscribers.py").read_text(encoding="utf-8")
    assert "jurisprudencia_externa.router.include_router" not in subscribers
