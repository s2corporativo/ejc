from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.eval.adaptive_bench import load_cases, score_case, summarize
from app.eval.architecture_comparison import simulated
from app.services.ai import provider_quality_policy as pqp


def test_adaptive_bench_detecta_falha_critica_e_segmenta_dificuldade():
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "app" / "eval" / "benchmarks" / "adaptive_bench.synthetic.jsonl"
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


class _ReviewDB:
    def __init__(self, event):
        self.event = event

    async def get(self, model, key):
        return self.event


@pytest.mark.asyncio
async def test_aprovacao_do_proprio_autor_e_bloqueada():
    from fastapi import HTTPException
    from types import SimpleNamespace
    from app.models.ai_learning import AILearningEventType
    from app.models.user import UserRole
    from app.services.ai.supervised_learning import review_event

    event = SimpleNamespace(
        id="evt",
        case_id=None,
        created_by="u1",
        event_type=AILearningEventType.correction,
        corrected_text="Correção humana suficientemente detalhada.",
        reason="A resposta original omitiu uma questão jurídica relevante.",
        metadata_json={},
        ai_log_id=None,
    )
    user = SimpleNamespace(id="u1", role=UserRole.advogado)
    with pytest.raises(HTTPException) as exc:
        await review_event(
            _ReviewDB(event),
            user=user,
            event_id="evt",
            approved=True,
            notes="Tentativa de autoaprovação.",
        )
    assert exc.value.status_code == 409
    assert "independente" in str(exc.value.detail).lower()



class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _LearningDB:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, stmt):
        return _Rows(self.rows)


@pytest.mark.asyncio
async def test_aprendizado_entre_casos_usa_licao_generalizada_nao_resposta_integral():
    from app.services.ai.supervised_learning import approved_learning_context

    row = SimpleNamespace(
        reason="Erro específico do caso.",
        corrected_text="ESTRATEGIA SIGILOSA COMPLETA DO CASO",
        error_type="prova",
        metadata_json={
            "review_notes": "Sempre separar alegação, fato provado e lacuna documental."
        },
    )
    texto = await approved_learning_context(
        _LearningDB([row]), area="civil", limit=3
    )
    assert "Sempre separar alegação" in texto
    assert "ESTRATEGIA SIGILOSA" not in texto
