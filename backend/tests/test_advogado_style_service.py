from types import SimpleNamespace

import pytest

from app.services import advogado_style_service as svc


@pytest.mark.asyncio
async def test_gerar_perfil_estilo_sem_base(monkeypatch):
    async def fake_carregar(db, user_id, limite=12):
        return []

    monkeypatch.setattr(svc, "carregar_pecas_base_estilo", fake_carregar)
    out = await svc.gerar_perfil_estilo(db=None, user_id="u1")
    assert out["status"] == "sem_base"
    assert out["total_pecas"] == 0
    assert out["instrucoes_prompt"] == ""


@pytest.mark.asyncio
async def test_gerar_perfil_estilo_com_pecas_humanas(monkeypatch):
    conteudo = """
    DOS FATOS
    A parte autora narra falha na prestação do serviço essencial. Ademais, houve tentativa administrativa.
    DO DIREITO
    Conforme o Código de Defesa do Consumidor, há responsabilidade objetiva.
    DOS PEDIDOS
    Diante do exposto, requer indenização por dano moral e material.
    """

    async def fake_carregar(db, user_id, limite=12):
        return [SimpleNamespace(conteudo=conteudo), SimpleNamespace(conteudo=conteudo)]

    monkeypatch.setattr(svc, "carregar_pecas_base_estilo", fake_carregar)
    out = await svc.gerar_perfil_estilo(db=None, user_id="u1")
    assert out["status"] == "ok"
    assert out["total_pecas"] == 2
    assert "dos fatos" in out["secoes_frequentes"]
    assert "dos pedidos" in out["secoes_frequentes"]
    assert "Adapte a redação ao estilo" in out["instrucoes_prompt"]
    assert "sem copiar trechos" in out["instrucoes_prompt"]


@pytest.mark.asyncio
async def test_montar_instrucoes_estilo_para_prompt_limita_tamanho(monkeypatch):
    async def fake_perfil(db, user_id):
        return {"status": "ok", "instrucoes_prompt": "x" * 3000}

    monkeypatch.setattr(svc, "gerar_perfil_estilo", fake_perfil)
    out = await svc.montar_instrucoes_estilo_para_prompt(db=None, user_id="u1")
    assert len(out) == 1600


def test_peca_geracao_injeta_estilo_no_pipeline():
    from pathlib import Path

    source = Path("app/routers/peca_geracao.py").read_text(encoding="utf-8")
    assert "montar_instrucoes_estilo_para_prompt" in source
    assert "[ESTILO DO ADVOGADO]" in source
    assert "instrucoes_adicionais=instrucoes" in source


def test_router_estilo_registrado_explicitamente():
    """Onda 3 §4.1: o router deixou de ser anexado por side effect em
    event_subscribers e passou a ser registrado em app/main.py — o path final
    permanece /api/pecas/advogado-estilo/me."""
    from pathlib import Path

    from app.main import app

    montadas = {getattr(r, "path", "") for r in app.routes}
    assert "/api/pecas/advogado-estilo/me" in montadas

    main_src = Path("app/main.py").read_text(encoding="utf-8")
    assert 'advogado_estilo.router, prefix=API + "/pecas"' in main_src

    subscribers = Path("app/services/event_subscribers.py").read_text(encoding="utf-8")
    assert "_patch_advogado_estilo_router" not in subscribers
    assert "include_router" not in subscribers
