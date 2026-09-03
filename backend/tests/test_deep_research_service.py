from types import SimpleNamespace

import pytest

from app.services import deep_research_service as dr


class FakeDB:
    def __init__(self):
        self.added = []
        self.committed = False

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_decompor_tese_fallback_quando_gateway_falha(monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("gateway indisponivel")

    monkeypatch.setattr(dr, "gw_chat", boom)
    out = await dr.decompor_tese("dano moral por falha de servico", "fatos com prazo", "consumidor", 4)
    assert len(out) == 4
    assert any("Cabimento" in q for q in out)


@pytest.mark.asyncio
async def test_executar_deep_research_agrega_rag_precedentes_e_log(monkeypatch):
    async def fake_decompor(tese, fatos, area, max_subquestoes=5, **kw):
        return ["cabimento", "provas"]

    async def fake_rag(db, consulta, limite=4, scope_client_id=None, **kw):
        return [{
            "chunk_id": f"c-{consulta[:4]}",
            "titulo": "Fonte interna",
            "categoria": "jurisprudencia",
            "fonte": "RAG",
            "conteudo": "Conteudo juridico interno validado.",
        }]

    async def fake_precedentes(termo, fontes=None, numero_cnj=None, por_pagina=8):
        return {
            "fontes": {"lexml": {"status": "success"}},
            "precedentes": [{
                "titulo": "Precedente externo",
                "ementa": "Ementa confirmada.",
                "tribunal": "TJMG",
                "numero_acordao": "123",
                "fonte": "TJMG",
                "link_original": "",
            }],
        }

    async def fake_chat(*args, **kwargs):
        return SimpleNamespace(texto="Resultado final da pesquisa", modelo="modelo-teste")

    monkeypatch.setattr(dr, "decompor_tese", fake_decompor)
    monkeypatch.setattr(dr, "buscar_contexto_rag", fake_rag)
    monkeypatch.setattr(dr, "buscar_precedentes", fake_precedentes)
    monkeypatch.setattr(dr, "gw_chat", fake_chat)

    db = FakeDB()
    entrada = dr.DeepResearchInput(
        tese="cobranca indevida e dano moral",
        fatos="Consumidor recebeu cobranca indevida e teve servico interrompido.",
        area="consumidor",
        case_id="case-1",
        scope_client_id="client-1",
    )
    out = await dr.executar_deep_research(db, entrada, user_id="user-1")

    assert out["status"] == "ok"
    assert out["modo"] == "deep_research_v1_sincrono"
    assert out["fontes_rag_total"] >= 1
    assert out["precedentes_total"] == 1
    assert out["ai_log_id"]
    assert db.committed is True
    assert db.added


def test_router_pecas_expoe_deep_research():
    from pathlib import Path

    source = Path("app/routers/peca_geracao.py").read_text(encoding="utf-8")
    assert "/deep-research/juridica" in source
    assert "DeepResearchRequest" in source
    assert "executar_deep_research" in source
    assert "rate_limit(\"deep_research_juridica\", 6)" in source


# ── Revisão automatizada do PR (03/09/2026) ─────────────────────────────────
# O custo do deep research precisa bater com a contabilidade do gateway. O
# recálculo local cobrava por resposta servida do cache (tokens registrados,
# custo zero apurado).
def test_somar_uso_usa_o_custo_apurado_pelo_gateway():
    from decimal import Decimal
    from types import SimpleNamespace

    from app.services.deep_research_service import _somar_uso

    paga = SimpleNamespace(provedor="anthropic", modelo="claude-opus-4-8",
                           input_tokens=1000, output_tokens=500,
                           custo_estimado_brl=0.42)
    do_cache = SimpleNamespace(provedor="anthropic", modelo="claude-opus-4-8",
                               input_tokens=1000, output_tokens=500,
                               custo_estimado_brl=0.0)

    _, _, custo = _somar_uso([paga, do_cache])
    assert custo == Decimal("0.42"), "cache hit não pode ser cobrado de novo"

    tokens_in, tokens_out, _ = _somar_uso([paga, do_cache])
    assert (tokens_in, tokens_out) == (2000, 1000)


def test_somar_uso_recalcula_quando_o_objeto_nao_traz_o_custo():
    from types import SimpleNamespace

    from app.services.deep_research_service import _somar_uso

    parcial = SimpleNamespace(provedor="anthropic", modelo="claude-opus-4-8",
                              input_tokens=1000, output_tokens=500)
    _, _, custo = _somar_uso([parcial])
    assert custo is not None and custo > 0


def test_somar_uso_sem_tokens_em_nenhuma_resposta_devolve_none():
    from types import SimpleNamespace

    from app.services.deep_research_service import _somar_uso

    vazio = SimpleNamespace(provedor="anthropic", modelo="x",
                            input_tokens=None, output_tokens=None,
                            custo_estimado_brl=0.0)
    assert _somar_uso([vazio]) == (None, None, None)
