# ── tests/test_eval_gold_set_smoke.py ────────────────────────────────────────
# Smoke offline dos gold sets (P2 — auditoria IA): o modo `--smoke` de
# app.eval.run_eval valida o FORMATO dos *.jsonl sem banco e sem LLM.
# Garante que os arquivos embarcados no repo passam e que o validador pega
# caso quebrado / exemplo "fictício" com jurisprudência sem marcador.
from __future__ import annotations

from app.eval.run_eval import _smoke, _validar_caso_smoke


def test_gold_sets_do_repo_passam_no_smoke():
    assert _smoke() == 0


def test_caso_rag_valido_e_invalido():
    ok = {"id": "x-1", "query": "prazo", "expected_titulos": ["CLT art. 11"]}
    assert _validar_caso_smoke(ok, "gold_set.jsonl") == []
    sem_titulos = {"id": "x-2", "query": "prazo", "expected_titulos": []}
    assert any("expected_titulos" in e for e in _validar_caso_smoke(sem_titulos, "gold_set.jsonl"))


def test_caso_peca_exige_campos_obrigatorios():
    caso = {"id": "p-1", "fatos": "fatos pseudonimizados"}
    erros = _validar_caso_smoke(caso, "gold_set_pecas.jsonl")
    faltantes = " ".join(erros)
    for campo in ("area", "tipo_peca_esperado", "teses_esperadas", "criterios", "ficticio"):
        assert campo in faltantes


def test_exemplo_embarcado_exige_ficticio_e_placeholder():
    caso = {
        "id": "p-1", "area": "civel", "fatos": "f", "tipo_peca_esperado": "contestacao",
        "teses_esperadas": ["t"], "criterios": ["c"], "ficticio": False,
        "jurisprudencia_esperada": ["Súmula 999 do STJ"],
    }
    erros = _validar_caso_smoke(caso, "gold_set_pecas.example.jsonl")
    assert any("ficticio=true" in e for e in erros)
    # Anti-invenção: jurisprudência de exemplo sem marcador FICTICIA é rejeitada.
    assert any("FICTICIA" in e for e in erros)
    # No gold set REAL (não-example) a referência conferida é aceita.
    caso_real = dict(caso, ficticio=False)
    assert _validar_caso_smoke(caso_real, "gold_set_pecas.jsonl") == []


def test_formato_desconhecido_e_rejeitado():
    assert any(
        "formato desconhecido" in e
        for e in _validar_caso_smoke({"id": "z"}, "qualquer.jsonl")
    )
