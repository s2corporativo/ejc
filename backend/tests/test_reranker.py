"""Reranking (cross-encoder) do RAG — Fase 1 da auditoria de IA.

Garante, SEM baixar modelo no CI (fastembed é mockado/ausente):
- desligado por config OU indisponível (fastembed ausente) → passthrough
  (mantém a ORDEM RRF recebida, cortando em `limite`);
- com modelo, reordena por score desc, anexa `rerank_score` e trunca em `limite`;
- fail-safe: erro no modelo ou contagem de scores divergente → mantém RRF;
- casos-limite: lista vazia / 1 candidato não chamam o modelo;
- wiring: buscar_contexto_rag encaminha o resultado pelo reranker.
"""
import pytest

from app.services.ai import reranker as rr


class _FakeCrossEncoder:
    """Substitui fastembed TextCrossEncoder: pontua por índice na lista `scores`."""

    def __init__(self, scores, explode: bool = False):
        self._scores = scores
        self.explode = explode
        self.chamadas: list[tuple[str, list[str]]] = []

    def rerank(self, consulta, textos):
        if self.explode:
            raise RuntimeError("onnx do reranker quebrou")
        self.chamadas.append((consulta, list(textos)))
        return list(self._scores)


def _cands(n):
    return [{"chunk_id": i, "conteudo": f"trecho {i}"} for i in range(n)]


@pytest.fixture
def _rerank_on(monkeypatch):
    """Liga o rerank e limpa o estado de módulo (singleton/flag de import)."""
    monkeypatch.setattr(rr.settings, "RAG_RERANK_ENABLED", True)
    monkeypatch.setattr(rr, "_IMPORTAVEL", True)   # finge fastembed importável
    monkeypatch.setattr(rr, "_model", None)
    yield monkeypatch


# ── config / pool ────────────────────────────────────────────────────────────

def test_desligado_por_config_nao_disponivel(monkeypatch):
    monkeypatch.setattr(rr.settings, "RAG_RERANK_ENABLED", False)
    assert rr.habilitado() is False
    assert rr.disponivel() is False


def test_tamanho_pool_respeita_mult_e_piso(monkeypatch):
    monkeypatch.setattr(rr.settings, "RAG_RERANK_POOL_MULT", 5)
    monkeypatch.setattr(rr.settings, "RAG_RERANK_POOL_MIN", 20)
    assert rr.tamanho_pool(6) == 30      # 6*5=30 > piso 20
    assert rr.tamanho_pool(2) == 20      # 2*5=10 < piso 20 → 20
    assert rr.tamanho_pool(50) == 250    # 50*5


# ── passthrough (degradação graciosa) ────────────────────────────────────────

async def test_indisponivel_mantem_ordem_e_corta(monkeypatch):
    # habilitado mas fastembed ausente (import falhou) → passthrough
    monkeypatch.setattr(rr.settings, "RAG_RERANK_ENABLED", True)
    monkeypatch.setattr(rr, "_IMPORTAVEL", False)
    cands = _cands(10)
    out = await rr.rerank("consulta", cands, limite=6)
    assert [c["chunk_id"] for c in out] == list(range(6))  # ordem preservada
    assert all("rerank_score" not in c for c in out)       # não anota score


async def test_lista_vazia_e_unitaria_nao_chamam_modelo(_rerank_on):
    chamado = {"n": 0}

    def _boom():
        chamado["n"] += 1
        raise AssertionError("não deveria carregar o modelo")

    _rerank_on.setattr(rr, "_try_get_model", _boom)
    assert await rr.rerank("q", [], limite=6) == []
    um = _cands(1)
    assert await rr.rerank("q", um, limite=6) == um
    assert chamado["n"] == 0


# ── reordenação real (modelo mockado) ────────────────────────────────────────

async def test_reordena_por_score_desc_e_anota(_rerank_on):
    cands = _cands(4)  # chunk_id 0..3
    # scores: o candidato 2 é o mais relevante, depois 0, 3, 1
    fake = _FakeCrossEncoder(scores=[0.5, 0.1, 0.9, 0.3])
    _rerank_on.setattr(rr, "_try_get_model", lambda: fake)

    out = await rr.rerank("dano moral", cands, limite=3)

    assert [c["chunk_id"] for c in out] == [2, 0, 3]   # top-3 por score desc
    assert out[0]["rerank_score"] == 0.9
    assert all("rerank_score" in c for c in out)
    # a consulta e os trechos foram passados ao cross-encoder
    consulta, textos = fake.chamadas[0]
    assert consulta == "dano moral"
    assert textos == [f"trecho {i}" for i in range(4)]


async def test_trunca_conteudo_longo_no_encode(_rerank_on):
    grande = {"chunk_id": 1, "conteudo": "x" * 9000}
    outro = {"chunk_id": 2, "conteudo": "y" * 10}
    fake = _FakeCrossEncoder(scores=[0.2, 0.8])
    _rerank_on.setattr(rr, "_try_get_model", lambda: fake)

    await rr.rerank("q", [grande, outro], limite=2)

    _consulta, textos = fake.chamadas[0]
    assert len(textos[0]) == rr._MAX_CHARS   # trecho longo truncado


# ── fail-safe ────────────────────────────────────────────────────────────────

async def test_erro_no_modelo_mantem_rrf(_rerank_on, caplog):
    cands = _cands(5)
    _rerank_on.setattr(rr, "_try_get_model", lambda: _FakeCrossEncoder(scores=[], explode=True))
    with caplog.at_level("WARNING", logger="ejc.ai.reranker"):
        out = await rr.rerank("q", cands, limite=3)
    assert [c["chunk_id"] for c in out] == [0, 1, 2]   # ordem RRF preservada


async def test_contagem_de_scores_divergente_mantem_rrf(_rerank_on, caplog):
    cands = _cands(5)
    # 3 scores para 5 candidatos → descarta e mantém RRF
    _rerank_on.setattr(rr, "_try_get_model", lambda: _FakeCrossEncoder(scores=[0.9, 0.8, 0.7]))
    with caplog.at_level("WARNING", logger="ejc.ai.reranker"):
        out = await rr.rerank("q", cands, limite=3)
    assert [c["chunk_id"] for c in out] == [0, 1, 2]


async def test_modelo_indisponivel_desliga_no_processo(_rerank_on):
    # _try_get_model devolve None (modelo não suportado) → passthrough, sem erro
    _rerank_on.setattr(rr, "_try_get_model", lambda: None)
    out = await rr.rerank("q", _cands(4), limite=2)
    assert [c["chunk_id"] for c in out] == [0, 1]


# ── wiring com buscar_contexto_rag ───────────────────────────────────────────

async def test_buscar_contexto_rag_encaminha_pelo_reranker(monkeypatch):
    """A busca textual (embeddings off) deve devolver o que o reranker retornar."""
    from app.services import ai_service
    from app.services import embedding_service as es

    monkeypatch.setattr(es, "disponivel", lambda: False)  # força caminho textual

    sentinela = [{"chunk_id": 99, "conteudo": "top", "titulo": "t",
                  "categoria": "c", "fonte": None, "confianca": "media"}]

    capturado = {}

    async def _spy_rerank(consulta, candidatos, limite, campo="conteudo"):
        capturado["consulta"] = consulta
        capturado["limite"] = limite
        return sentinela

    # `_reranker` é importado DENTRO da função (from app.services.ai import
    # reranker as _reranker) — é o mesmo objeto-módulo `rr`, então basta patchá-lo.
    monkeypatch.setattr(rr, "rerank", _spy_rerank)

    class _Row:
        def __init__(self, i):
            self.id, self.conteudo, self.titulo = i, f"c{i}", f"t{i}"
            self.categoria, self.fonte, self.confianca = "cat", None, "media"

    class _DB:
        async def execute(self, sql, params=None):
            return [_Row(1), _Row(2), _Row(3)]

    out = await ai_service.buscar_contexto_rag(_DB(), "dano moral", limite=6)

    assert out is sentinela
    assert capturado["limite"] == 6
    assert capturado["consulta"] == "dano moral"
