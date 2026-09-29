"""Regressão dos defeitos B e C (Módulos 3 e 4 da transformação da IA).

- B: issue_engine omite prova_onus_lacunas em cenários que descrevem posse/
  ausência de documentos em linguagem natural (sem substantivo "prova").
- C: legal_bench atribuía crédito 1.0 a dimensões desativadas/vazias, fazendo
  resposta vazia receber nota alta; e não publicava denominadores.
"""
import json
from pathlib import Path

import pytest

from app.eval.legal_bench import (
    REGUA_VERSION,
    LegalBenchCase,
    load_cases,
    score_structured_answer,
    summarize,
)
from app.services.legal_brain.issue_engine import identify_legal_issues

BENCH = Path(__file__).resolve().parents[1] / "app/eval/benchmarks/legal_bench.synthetic.jsonl"


# ---------------------------------------------------------------- defeito B ---
@pytest.mark.parametrize(
    "case_id,area,prompt",
    [
        (
            "synthetic-bank-002",
            "bancario",
            "[F1] Cliente questiona empréstimo e evolução do débito. "
            "[F2] Possui extratos parciais, mas não possui contrato, CET, seguros ou memória de amortização.",
        ),
        (
            "synthetic-consumer-003",
            "consumidor",
            "[F1] Cliente afirma falha na prestação de serviço e cobrança indevida. "
            "[F2] Possui contrato e protocolos. [F3] Relata risco de interrupção imediata do serviço.",
        ),
    ],
)
def test_prova_onus_detectada_em_posse_ausencia_de_documento(case_id, area, prompt):
    keys = {i.key for i in identify_legal_issues(prompt, area=area)}
    assert "prova_onus_lacunas" in keys, f"{case_id}: prova_onus_lacunas omitida"


def test_issue_engine_recupera_todas_as_questoes_esperadas_do_bench():
    cases = {c.id: c for c in load_cases(BENCH)}
    for cid in ("synthetic-bank-002", "synthetic-consumer-003"):
        case = cases[cid]
        found = {i.key for i in identify_legal_issues(case.prompt, area=case.area)}
        assert set(case.expected_issue_keys) <= found, f"{cid}: faltou {set(case.expected_issue_keys) - found}"


def test_issue_engine_preserva_controle_negativo():
    keys = {i.key for i in identify_legal_issues("O escritório recebeu aprovação interna do texto.", area="civil")}
    assert "prova_onus_lacunas" not in keys


# ---------------------------------------------------------------- defeito C ---
def _vazia():
    return {"issue_keys": [], "source_ids": [], "fact_ids": [], "research_records": [], "conclusion_status": ""}


def test_resposta_vazia_nao_recebe_credito_artificial():
    cases = load_cases(BENCH)
    scores = [score_structured_answer(c, _vazia()) for c in cases]
    summary = summarize(scores)
    assert summary["total"] == 0.0, "resposta vazia não pode receber nota agregada positiva"
    assert all(s.answer_status == "vazia" for s in scores)
    # dimensões com insumo obrigatório e insumo ausente => 0 e marcada 'ausente'
    for s in scores:
        if s.issue_recall is not None:
            assert s.issue_recall == 0.0


def test_dimensao_desativada_fica_fora_do_denominador():
    case = LegalBenchCase(
        id="c",
        area="consumidor",
        prompt="p",
        expected_issue_keys=("x",),
        source_scoring_enabled=False,  # dimensão desativada
        requires_adverse_research=False,  # não aplicável ao caso
    )
    sc = score_structured_answer(case, {"issue_keys": ["x"]})
    assert sc.source_precision is None, "fonte desativada não pode receber valor"
    dims = dict(sc.dims)
    assert dims["source_precision"].status == "nao_aplicavel"
    # total não inclui a dimensão desativada: só issue_recall=1.0 conta
    assert sc.total == 1.0
    summary = summarize([sc])
    assert summary["dimensoes"]["source_precision"]["n_aplicavel"] == 0
    assert summary["dimensoes"]["source_precision"]["media"] is None


def test_abstencao_fundamentada_difere_de_ausencia_de_resposta():
    case = LegalBenchCase(
        id="c",
        area="consumidor",
        prompt="p",
        expected_issue_keys=("x",),
        has_missing_evidence=True,
        source_scoring_enabled=False,
    )
    # abstenção fundamentada: sem insumo, mas reconhece insuficiência
    segura = score_structured_answer(
        case, {"conclusion_status": "sem_conclusao_segura"}
    )
    assert segura.answer_status == "abstencao_fundamentada"
    assert segura.uncertainty_compliance == 1.0

    # ausência pura (nada, nem status) => vazia, zero
    vazia = score_structured_answer(case, {})
    assert vazia.answer_status == "vazia"
    assert vazia.uncertainty_compliance == 0.0


def test_resumo_publica_denominadores_e_regua():
    cases = load_cases(BENCH)
    scores = [score_structured_answer(c, _vazia()) for c in cases]
    s = summarize(scores)
    assert s["regua"] == REGUA_VERSION
    for name, info in s["dimensoes"].items():
        assert info["n_total"] == len(scores), name
        assert 0 <= info["n_aplicavel"] <= info["n_total"], name
    # casos sem lacuna => uncertainty fora do denominador
    assert s["dimensoes"]["uncertainty_compliance"]["n_aplicavel"] < s["n"]


def test_source_precision_pune_id_inesperado_sem_fonte_gold():
    case = LegalBenchCase(
        id="fonte-inesperada",
        area="consumidor",
        prompt="p",
        expected_source_ids=(),
        source_scoring_enabled=True,
    )
    sc = score_structured_answer(case, {"source_ids": ["fonte-inventada"]})
    assert sc.source_precision == 0.0
    dims = dict(sc.dims)
    assert dims["source_precision"].status == "avaliado"
    assert dims["source_precision"].value == 0.0
