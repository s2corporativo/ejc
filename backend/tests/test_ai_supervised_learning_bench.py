from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.eval.adaptive_bench import load_cases, score_case, summarize
from app.eval.architecture_comparison import simulated
from app.services.ai import provider_quality_policy as pqp
from app.services import ingestion_service
from app.models.rag import KnowledgeDoc


def test_adaptive_bench_detecta_falha_critica_e_segmenta_dificuldade():
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "app" / "eval" / "gold_set_adaptive.synthetic.jsonl"
    cases = load_cases(path)
    rows = [score_case(c, c.simulated_answer or {}) for c in cases]
    summary = summarize(rows)

    assert summary["global"]["n"] == 8
    assert summary["global"]["critical_failures"] == 1
    fail = next(r for r in rows if r["id"] == "ADAPT-SIM-FAIL-001")
    assert fail["raw_score"] == 100.0
    assert fail["certification_score"] == 0.0
    assert "citação inexistente/incorreta" in fail["critical_reasons"]
    assert summary["by_difficulty"]["excepcional"]["n"] == 1


def test_architecture_comparison_simulation_is_explicitly_non_evidence():
    report = simulated()
    assert report["simulated"] is True
    assert "não mede" in report["warning"]
    assert report["n"] == 12
    assert report["delta_mean"] > 0


def test_adaptive_provider_requires_certified_holdout(tmp_path, monkeypatch):
    artifact = tmp_path / "quality.json"
    payload = {
        "schema": pqp.SCHEMA,
        "certified": True,
        "holdout_evaluated": True,
        "areas": {
            "tributario": {
                "analise_juridica": {
                    "providers": {
                        "maritaca": {
                            "n": 20, "score": 0.91,
                            "critical_failures": 0, "avg_cost_brl": 0.02,
                        },
                        "anthropic": {
                            "n": 20, "score": 0.88,
                            "critical_failures": 0, "avg_cost_brl": 0.08,
                        },
                    }
                }
            }
        },
    }
    artifact.write_text(json.dumps(payload), encoding="utf-8")
    settings = SimpleNamespace(
        AI_ADAPTIVE_ROUTING_ENABLED=True,
        AI_ADAPTIVE_ROUTING_ARTIFACT=str(artifact),
        AI_ADAPTIVE_ROUTING_MIN_CASES=15,
    )
    monkeypatch.setattr(pqp, "get_settings", lambda: settings)
    pqp._load_artifact.cache_clear()

    provider, reason = pqp.recommend_provider(
        area="tributario",
        task_type="analise_juridica",
        eligible=["maritaca", "anthropic"],
    )
    assert provider == "maritaca"
    assert "benchmark certificado" in reason

    payload["holdout_evaluated"] = False
    artifact.write_text(json.dumps(payload), encoding="utf-8")
    pqp._load_artifact.cache_clear()
    provider, _ = pqp.recommend_provider(
        area="tributario",
        task_type="analise_juridica",
        eligible=["maritaca", "anthropic"],
    )
    assert provider is None


class _Res:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _DB:
    def __init__(self, existing=None):
        self.existing = existing
        self.added = []

    async def execute(self, stmt, params=None):
        return _Res(self.existing)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None


@pytest.mark.asyncio
async def test_ingestion_declara_vigencia_nao_verificada_sem_inventar(monkeypatch):
    async def no_embeddings(texts, *args, **kwargs):
        return None

    monkeypatch.setattr(ingestion_service, "gerar_embeddings", no_embeddings)
    db = _DB()
    await ingestion_service.upsert_documento(
        db,
        titulo="Lei de teste",
        categoria="legislacao_geral",
        conteudo="Art. 1º " + ("texto jurídico verificável " * 4),
        chave_origem="test:temporal:1",
        fonte="https://exemplo.gov.br/lei",
        tribunal="BR",
    )
    doc = next(x for x in db.added if isinstance(x, KnowledgeDoc))
    assert doc.extra["source"] == "https://exemplo.gov.br/lei"
    assert doc.extra["jurisdiction"] == "BR"
    assert doc.extra["legal_status"] == "vigencia_nao_verificada"
    assert doc.extra["last_verified_at"] is None
    assert doc.extra["last_ingested_at"]


@pytest.mark.asyncio
async def test_nova_versao_aponta_superseded_by(monkeypatch):
    async def no_embeddings(texts, *args, **kwargs):
        return None

    monkeypatch.setattr(ingestion_service, "gerar_embeddings", no_embeddings)
    existing = KnowledgeDoc(
        id="old",
        titulo="Lei",
        categoria="legislacao_geral",
        fonte="https://exemplo.gov.br/lei",
        chave_origem="test:version",
        hash_conteudo="oldhash",
        versao=1,
        vigente=True,
        extra={"rag_status": "aprovado"},
    )
    db = _DB(existing=existing)
    await ingestion_service.upsert_documento(
        db,
        titulo="Lei",
        categoria="legislacao_geral",
        conteudo="Art. 1º " + ("nova redação oficial " * 5),
        chave_origem="test:version",
        fonte="https://exemplo.gov.br/lei",
    )
    new_doc = next(x for x in db.added if isinstance(x, KnowledgeDoc))
    assert existing.vigente is False
    assert existing.extra["superseded_by"] == new_doc.id
    assert existing.extra["superseded_at"]
