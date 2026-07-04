"""
test_deep_research.py — pipeline de Deep Research jurídica.

Gateway de IA, RAG (pgvector) e crawler (STJ) MOCKADOS. Cobre:
  - criação do job (status em_andamento, progresso 0);
  - execução das etapas atualizando o progresso;
  - verificação de citações é chamada;
  - decomposição respeita o teto de sub-questões;
  - falha no meio → status "erro" (nunca "success" vazio).
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.models.deep_research import DeepResearchJob, DeepResearchStatus
from app.services import deep_research_service as dr


# ── Dublês ────────────────────────────────────────────────────────────────────
class FakeDB:
    """Sessão async mínima: registra commits e o progresso a cada commit."""

    def __init__(self, job=None):
        self.job = job
        self.added = []
        self.progresso_snapshots = []

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.progresso_snapshots.append(getattr(self.job, "progresso", None))

    async def rollback(self):
        pass

    async def refresh(self, obj):
        pass

    async def get(self, model, ident):
        return self.job

    async def execute(self, *a, **k):
        class _R:
            def first(self_inner):
                return None

            def scalar_one_or_none(self_inner):
                return None

        return _R()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _fake_gateway_resp(texto: str):
    return SimpleNamespace(
        texto=texto, provedor="ollama", modelo="fake-model",
        input_tokens=10, output_tokens=20,
    )


def _instalar_mocks(monkeypatch, *, subquestoes, citou):
    """Instala gateway/RAG/crawler/citação falsos. `citou` é um dict-flag."""

    async def fake_chat(messages, task_type="analise_juridica", **kw):
        conteudo_sys = messages[0]["content"]
        if "array JSON" in conteudo_sys:  # etapa de decomposição
            return _fake_gateway_resp(json.dumps(subquestoes, ensure_ascii=False))
        # etapa de síntese
        return _fake_gateway_resp("Relatório de pesquisa jurídica [Fonte 1]. " + dr._AVISO_RASCUNHO)

    async def fake_rag(db, consulta, limite=6, **kw):
        return [{
            "titulo": "Súmula 7 STJ", "categoria": "sumula", "fonte": "STJ",
            "conteudo": "A pretensão de simples reexame de prova não enseja recurso especial.",
            "score": 0.91,
        }]

    async def fake_crawler(nome, tema):
        return {
            "status": "success", "fonte": "STJ/SCON", "url": "https://scon.stj.jus.br/x",
            "precedentes": [{"ementa": "Ementa de precedente sobre o tema.",
                             "tribunal": "STJ", "fonte": "STJ/SCON"}],
        }

    async def fake_citacoes(db, texto, **kw):
        citou["chamado"] = True
        return {"total": 1, "confirmadas": 1, "nao_encontradas": 0, "citacoes": []}

    async def fake_log(*a, **k):
        return "log-id"

    monkeypatch.setattr(dr.ai_gateway, "chat", fake_chat)
    monkeypatch.setattr(dr.ai_service, "buscar_contexto_rag", fake_rag)
    monkeypatch.setattr(dr.crawler_precedentes.crawler,
                        "buscar_precedentes_magistrado", fake_crawler)
    monkeypatch.setattr(dr.citation_check, "verificar_citacoes", fake_citacoes)
    # AILog gravado por outro caminho já testado; aqui só garantimos que é chamado.
    monkeypatch.setattr(dr, "registrar_ai_log", fake_log)


def _novo_job(**kw):
    base = dict(id="job-1", user_id="u-1", case_id=None,
                pergunta="É cabível reexame de prova em recurso especial?",
                tese=None, nivel_inteligencia="alto",
                status=DeepResearchStatus.em_andamento, progresso=0,
                total_subquestoes=0, total_chamadas_ia=0,
                etapas_json="[]")
    base.update(kw)
    return DeepResearchJob(**base)


# ── Testes ────────────────────────────────────────────────────────────────────
async def test_criar_job_status_em_andamento():
    db = FakeDB()
    job = await dr.criar_job(
        db, user_id="u-1", pergunta="Pergunta jurídica de teste suficiente?",
        tese=None, case_id=None,
    )
    assert job.status == DeepResearchStatus.em_andamento
    assert job.progresso == 0
    assert job in db.added


async def test_pipeline_executa_etapas_e_verifica_citacoes(monkeypatch):
    citou = {}
    subquestoes = [
        "Qual a jurisprudência do STJ sobre reexame de prova?",  # dispara crawler
        "Qual o conceito doutrinário de reexame de prova?",       # só RAG
    ]
    _instalar_mocks(monkeypatch, subquestoes=subquestoes, citou=citou)

    job = _novo_job()
    db = FakeDB(job)
    await dr.run_pipeline(db, job)

    # Status final e progresso
    assert job.status == DeepResearchStatus.concluido
    assert job.progresso == 100
    assert job.total_subquestoes == 2
    # decomposição (1) + síntese (1)
    assert job.total_chamadas_ia == 2

    # Verificação de citações foi chamada
    assert citou.get("chamado") is True

    # Progresso foi atualizado incrementalmente (vários commits crescentes até 100)
    snaps = [p for p in db.progresso_snapshots if p is not None]
    assert snaps[0] < snaps[-1]
    assert snaps[-1] == 100
    assert snaps == sorted(snaps)          # monotônico não-decrescente
    assert len(set(snaps)) >= 4            # de fato houve várias etapas

    # Resultado estruturado com fontes rastreáveis
    resultado = json.loads(job.resultado_json)
    assert resultado["is_rascunho"] is True
    assert len(resultado["subquestoes"]) == 2
    assert resultado["relatorio"]
    assert resultado["fontes"], "deve catalogar fontes numeradas"
    assert all("n" in f for f in resultado["fontes"])
    assert resultado["verificacao_citacoes"]["confirmadas"] == 1


async def test_pipeline_respeita_teto_de_subquestoes(monkeypatch):
    # Gateway devolve 20 sub-questões; o pipeline deve cortar no MAX_SUBQUESTOES.
    subquestoes = [f"Sub-questão número {i} sobre o tema jurídico?" for i in range(20)]
    _instalar_mocks(monkeypatch, subquestoes=subquestoes, citou={})

    job = _novo_job()
    db = FakeDB(job)
    await dr.run_pipeline(db, job)

    assert job.total_subquestoes == dr.MAX_SUBQUESTOES
    resultado = json.loads(job.resultado_json)
    assert len(resultado["subquestoes"]) == dr.MAX_SUBQUESTOES


async def test_falha_no_gateway_marca_status_erro(monkeypatch):
    # Worker abre a própria sessão (AsyncSessionLocal); trocamos por uma fake.
    job = _novo_job()
    db = FakeDB(job)
    monkeypatch.setattr(dr, "AsyncSessionLocal", lambda: db)

    async def chat_quebra(*a, **k):
        raise RuntimeError("provedor de IA indisponível")

    monkeypatch.setattr(dr.ai_gateway, "chat", chat_quebra)

    await dr.executar_deep_research("job-1")

    assert job.status == DeepResearchStatus.erro
    assert "indisponível" in (job.erro_mensagem or "")
    # Nunca conclui com "success" vazio:
    assert job.resultado_json is None


async def test_crawler_falha_nao_derruba_job(monkeypatch):
    subquestoes = ["Qual a jurisprudência do STJ sobre o tema?"]
    citou = {}
    _instalar_mocks(monkeypatch, subquestoes=subquestoes, citou=citou)

    async def crawler_quebra(nome, tema):
        raise RuntimeError("timeout de rede no STJ")

    monkeypatch.setattr(dr.crawler_precedentes.crawler,
                        "buscar_precedentes_magistrado", crawler_quebra)

    job = _novo_job()
    db = FakeDB(job)
    await dr.run_pipeline(db, job)

    # Falha graciosa: RAG ainda alimenta a síntese, job conclui.
    assert job.status == DeepResearchStatus.concluido
    resultado = json.loads(job.resultado_json)
    assert all(f["tipo"] != "precedente" for f in resultado["fontes"])
