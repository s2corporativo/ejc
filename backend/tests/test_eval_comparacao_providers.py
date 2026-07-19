"""Modo --providers do eval harness (comparação Claude × Sabiá) — offline.

Sem rede/banco: ai_gateway.chat, citation_check e buscar_contexto_rag são
mockados. Valida que a comparação gera UMA resposta por provedor sobre o MESMO
contexto, registra fallback honestamente e agrega por provedor pedido.
"""
from __future__ import annotations

import pytest

from app.eval.run_eval import (
    CasoMetrica,
    _agregar_providers,
    _avaliar_caso,
    _avaliar_provider,
)
from app.services.ai_gateway import GatewayResponse

_CHUNKS = [
    {"titulo": "Súmula interna A", "conteudo": "conteudo A"},
    {"titulo": "Modelo B", "conteudo": "conteudo B"},
]


def _resp(provedor: str, modelo: str = "m1", custo: float = 0.5,
          duracao: int = 120) -> GatewayResponse:
    return GatewayResponse(
        texto="análise fundamentada", modelo=modelo, provedor=provedor,
        task_type="analise_juridica", custo_estimado_brl=custo,
        duracao_ms=duracao,
    )


@pytest.fixture
def mocks(monkeypatch):
    chamadas: list[dict] = []

    async def _fake_chat(messages, task_type="analise_juridica", **kw):
        chamadas.append({"messages": messages, "task_type": task_type, **kw})
        return _resp(kw.get("provider_override") or "anthropic")

    async def _fake_citacoes(db, texto):
        return {"total": 4, "nao_encontradas": 1}

    from app.services import ai_gateway, citation_check
    monkeypatch.setattr(ai_gateway, "chat", _fake_chat)
    monkeypatch.setattr(citation_check, "verificar_citacoes", _fake_citacoes)
    return chamadas


@pytest.mark.asyncio
async def test_avaliar_provider_mede_citacoes_custo_latencia(mocks):
    mp = await _avaliar_provider(None, {"query": "tese aplicável?"}, _CHUNKS,
                                 "maritaca", judge=False)
    assert mp.provider_pedido == "maritaca"
    assert mp.provider_real == "maritaca"
    assert mp.fallback is False
    assert (mp.citacoes_total, mp.citacoes_nao_confirmadas) == (4, 1)
    assert mp.custo_brl == 0.5
    assert mp.duracao_ms == 120
    assert mp.erro is None
    # o contexto RAG vai no system e o override é o provedor comparado
    assert mocks[0]["provider_override"] == "maritaca"
    assert "conteudo A" in mocks[0]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_avaliar_provider_registra_fallback(monkeypatch, mocks):
    # Cadeia respondeu com OUTRO provedor (ex.: maritaca inelegível → groq).
    async def _chat_fallback(messages, **kw):
        return _resp("groq")

    from app.services import ai_gateway
    monkeypatch.setattr(ai_gateway, "chat", _chat_fallback)
    mp = await _avaliar_provider(None, {"query": "q"}, _CHUNKS, "maritaca", judge=False)
    assert mp.fallback is True
    assert mp.provider_real == "groq"


@pytest.mark.asyncio
async def test_avaliar_provider_erro_nao_propaga(monkeypatch, mocks):
    async def _chat_erro(messages, **kw):
        raise RuntimeError("provedor fora do ar")

    from app.services import ai_gateway
    monkeypatch.setattr(ai_gateway, "chat", _chat_erro)
    mp = await _avaliar_provider(None, {"query": "q"}, _CHUNKS, "anthropic", judge=False)
    assert mp.erro and "fora do ar" in mp.erro


@pytest.mark.asyncio
async def test_avaliar_caso_uma_resposta_por_provedor(monkeypatch, mocks):
    async def _fake_rag(db, query, limite=6, categorias=None):
        return _CHUNKS

    from app.services import ai_service
    monkeypatch.setattr(ai_service, "buscar_contexto_rag", _fake_rag)
    caso = {"id": "c1", "query": "prazo recursal", "expected_titulos": ["Modelo B"]}
    m = await _avaliar_caso(None, caso, k=6, full=True, judge=False,
                            providers=["anthropic", "maritaca"])
    assert [p["provider_pedido"] for p in m.providers] == ["anthropic", "maritaca"]
    assert m.hit is True  # métricas de retrieval preservadas no modo comparação
    # modo comparação NÃO roda o caminho --full legado (uma IA por provedor já basta)
    assert m.citacoes_total == 0


@pytest.mark.asyncio
async def test_avaliar_caso_sem_providers_mantem_fluxo_antigo(monkeypatch, mocks):
    async def _fake_rag(db, query, limite=6, categorias=None):
        return _CHUNKS

    from app.services import ai_service
    monkeypatch.setattr(ai_service, "buscar_contexto_rag", _fake_rag)
    caso = {"id": "c2", "query": "q", "expected_titulos": ["Modelo B"]}
    m = await _avaliar_caso(None, caso, k=6, full=False, judge=False, providers=None)
    assert m.providers == []
    assert m.hit is True


def test_agregar_providers_por_provedor_pedido():
    m1 = CasoMetrica(id="a", area="", providers=[
        {"provider_pedido": "anthropic", "provider_real": "anthropic",
         "fallback": False, "citacoes_total": 4, "citacoes_nao_confirmadas": 1,
         "groundedness": 0.9, "custo_brl": 1.0, "duracao_ms": 100, "erro": None},
        {"provider_pedido": "maritaca", "provider_real": "groq",
         "fallback": True, "citacoes_total": 2, "citacoes_nao_confirmadas": 2,
         "groundedness": 0.5, "custo_brl": 0.2, "duracao_ms": 300, "erro": None},
    ])
    m2 = CasoMetrica(id="b", area="", providers=[
        {"provider_pedido": "anthropic", "provider_real": "anthropic",
         "fallback": False, "citacoes_total": 6, "citacoes_nao_confirmadas": 0,
         "groundedness": 1.0, "custo_brl": 2.0, "duracao_ms": 200, "erro": None},
        {"provider_pedido": "maritaca", "provider_real": "maritaca",
         "fallback": False, "citacoes_total": 0, "citacoes_nao_confirmadas": 0,
         "groundedness": None, "custo_brl": 0.1, "duracao_ms": 150,
         "erro": "timeout"},
    ])
    r = _agregar_providers([m1, m2])
    # anthropic: 2 execuções válidas (sem erro, sem fallback) → compõem métricas.
    assert r["anthropic"]["n_validos"] == 2
    assert r["anthropic"]["taxa_alucinacao"] == 0.1          # 1/10
    assert r["anthropic"]["groundedness"] == 0.95
    assert r["anthropic"]["custo_total_brl"] == 3.0
    assert r["anthropic"]["fallbacks"] == 0
    # maritaca: 1 fallback (m1) + 1 erro (m2) → NENHUMA execução válida.
    # A resposta de fallback (que veio do groq) NÃO entra nas métricas da
    # maritaca — senão a comparação atribuiria a ela o que outro provedor fez.
    assert r["maritaca"]["n_validos"] == 0
    assert r["maritaca"]["erros"] == 1
    assert r["maritaca"]["fallbacks"] == 1
    assert r["maritaca"]["taxa_alucinacao"] is None          # sem execução válida
    assert r["maritaca"]["groundedness"] is None
    assert r["maritaca"]["custo_total_brl"] == 0.0
