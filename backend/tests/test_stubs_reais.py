# tests/test_stubs_reais.py — garante que os antigos módulos simulados agora
# se comportam de forma REAL e honesta (sem "success" fake nem números inventados).
import httpx
import pytest

from app.core.veredito_ia import VereditoIA
from app.services import crawler_precedentes as cp
from app.services.rag_juridico import rag_juridico
from app.services.jurimetria import _resumo


# ── Crawler de precedentes (STJ/SCON) ────────────────────────────────────────

class _FakeResp:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "erro", request=httpx.Request("GET", cp.SCON_URL),
                response=httpx.Response(self.status_code),
            )


def _fake_client(resp=None, exc=None):
    class _FakeClient:
        def __init__(self, *a, **k): ...
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def get(self, *a, **k):
            if exc:
                raise exc
            return resp
    return _FakeClient


HTML_OK = """
<html><body>
<span>2 documentos encontrados</span>
<div class="docTexto">EMENTA. RECURSO ESPECIAL. Responsabilidade civil por dano
ambiental configurada nos termos da jurisprudência consolidada.</div>
<div class="docTexto">EMENTA. AGRAVO INTERNO. Aplicação da taxa Selic às
dívidas civis conforme entendimento da Corte Especial do STJ.</div>
</body></html>
"""


async def test_crawler_sucesso_com_httpx_mockado(monkeypatch):
    monkeypatch.setattr(cp.httpx, "AsyncClient", _fake_client(resp=_FakeResp(HTML_OK)))
    out = await cp.crawler.buscar_precedentes_magistrado("Min. Fulano", "dano ambiental")
    assert out["status"] == "success"
    assert out["total_encontrado"] == 2
    assert len(out["precedentes"]) == 2
    assert "Selic" in out["precedentes"][1]["ementa"]
    assert out["fonte"] == "STJ/SCON"


async def test_crawler_erro_de_rede_nao_vira_success(monkeypatch):
    monkeypatch.setattr(
        cp.httpx, "AsyncClient",
        _fake_client(exc=httpx.ConnectError("connection refused")),
    )
    out = await cp.crawler.buscar_precedentes_magistrado("Min. Fulano", "tema x")
    assert out["status"] == "erro"
    assert "rede" in out["mensagem"].lower()
    assert out["precedentes"] == []


async def test_crawler_nenhum_resultado_honesto(monkeypatch):
    html = "<html><body>Nenhum documento encontrado</body></html>"
    monkeypatch.setattr(cp.httpx, "AsyncClient", _fake_client(resp=_FakeResp(html)))
    out = await cp.crawler.buscar_precedentes_magistrado("Min. Fulano", "tema y")
    assert out["status"] == "success"
    assert out["total_encontrado"] == 0


async def test_crawler_pagina_ininterpretavel_e_erro(monkeypatch):
    html = "<html><body><p>layout completamente novo</p></body></html>"
    monkeypatch.setattr(cp.httpx, "AsyncClient", _fake_client(resp=_FakeResp(html)))
    out = await cp.crawler.buscar_precedentes_magistrado("Min. Fulano", "tema z")
    assert out["status"] == "erro"


# ── Veredito IA (jurimetria honesta) ─────────────────────────────────────────

async def test_veredito_sem_amostra_retorna_probabilidade_none(monkeypatch):
    v = VereditoIA()

    async def _amostra_vazia(area):
        return _resumo([])          # n=0 → amostra insuficiente

    async def _sem_juris(tese, limite=5):
        return []

    async def _sem_teses(**kwargs):
        return []

    monkeypatch.setattr(v, "_amostra_resultados", _amostra_vazia)
    monkeypatch.setattr(v, "_buscar_jurisprudencia", _sem_juris)
    monkeypatch.setattr(v.victory_vault, "get_teses_vitoriosas", _sem_teses)

    resp = await v.predict_success("tese qualquer", "civel", ["STJ"])
    assert resp.probabilidade_exito is None
    assert resp.aviso is not None and "insuficiente" in resp.aviso.lower()
    assert resp.amostra["n"] == 0
    assert resp.jurisprudencia_suporte == []


async def test_veredito_com_amostra_usa_taxa_real(monkeypatch):
    v = VereditoIA()
    amostra = _resumo(["exito_total"] * 3 + ["acordo"] * 1 + ["improcedente"] * 1)
    assert amostra["amostra_suficiente"]  # n=5

    async def _amostra(area):
        return amostra

    async def _sem_juris(tese, limite=5):
        return []

    async def _sem_teses(**kwargs):
        return []

    monkeypatch.setattr(v, "_amostra_resultados", _amostra)
    monkeypatch.setattr(v, "_buscar_jurisprudencia", _sem_juris)
    monkeypatch.setattr(v.victory_vault, "get_teses_vitoriosas", _sem_teses)

    resp = await v.predict_success("tese", "civel", ["STJ"])
    # 3 êxitos + 1 acordo em 5 casos = 80% → 0.8 (taxa real, não fórmula fixa)
    assert resp.probabilidade_exito == pytest.approx(0.8)
    assert resp.aviso is None


# ── RAG Jurídico (match de casos com busca vetorial) ─────────────────────────

async def test_match_de_casos_usa_busca_vetorial_e_llm(monkeypatch):
    import app.services.ai_service as ai_service

    chunks = [
        {"chunk_id": "c1", "conteudo": "Precedente interno sobre dano moral.",
         "titulo": "Doc 1", "categoria": "jurisprudencia", "fonte": "TJMG",
         "score": 0.91},
    ]

    async def _fake_rag(db, consulta, limite=6, categorias=None,
                        modo_or=False, scope_client_id=None):
        return chunks

    async def _fake_llm(prompt, modo="principal"):
        assert "Doc 1" in prompt or "dano moral" in prompt
        return "O documento [1] é aplicável ao caso."

    monkeypatch.setattr(ai_service, "buscar_contexto_rag", _fake_rag)
    monkeypatch.setattr(rag_juridico.ai, "generate", _fake_llm)

    out = await rag_juridico.match_de_casos("Ação de dano moral", "civel", db=None)
    assert out["status"] == "success"
    assert out["casos_similares"] == chunks
    assert "aplicável" in out["analise"]


async def test_match_de_casos_sem_resultados_nao_chama_llm(monkeypatch):
    import app.services.ai_service as ai_service

    async def _fake_rag(db, consulta, limite=6, categorias=None,
                        modo_or=False, scope_client_id=None):
        return []

    async def _llm_nao_deve_rodar(prompt, modo="principal"):
        raise AssertionError("LLM não deve ser chamado sem documentos recuperados")

    monkeypatch.setattr(ai_service, "buscar_contexto_rag", _fake_rag)
    monkeypatch.setattr(rag_juridico.ai, "generate", _llm_nao_deve_rodar)

    out = await rag_juridico.match_de_casos("caso inédito", "civel", db=None)
    assert out["status"] == "sem_resultados"
    assert out["casos_similares"] == []
    assert out["analise"] is None


# ── Diplomacia Digital (dossiê sem texto fixo) ───────────────────────────────

async def test_dossie_pressao_falta_de_dados_e_erro():
    from app.services.diplomacia_digital import diplomacia
    out = await diplomacia.gerar_dossie_pressao({"valor_causa": 100000})
    assert out["status"] == "erro"
    assert "faltam" in out["mensagem"]
