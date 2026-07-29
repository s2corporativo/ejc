# ── tests/test_eval_gold_set_smoke.py ────────────────────────────────────────
# Smoke offline dos gold sets (P2 — auditoria IA): o modo `--smoke` de
# app.eval.run_eval valida o FORMATO dos *.jsonl sem banco e sem LLM.
# Garante que os arquivos embarcados no repo passam e que o validador pega
# caso quebrado / exemplo "fictício" com jurisprudência sem marcador.
from __future__ import annotations

from app.eval.run_eval import CasoMetrica, _agregar, _smoke, _validar_caso_smoke


def test_gold_sets_do_repo_passam_no_smoke():
    assert _smoke() == 0


# ── AI-087 (auditoria máxima 2026-07-26): gate de qualidade POR ÁREA ─────────

def test_smoke_falha_quando_area_critica_nao_tem_cobertura():
    """Área crítica exigida sem gold set REAL é FALHA — hoje o repo só tem
    exemplos de formato, então cobertura zero não pode passar como aprovação."""
    assert _smoke(areas_obrigatorias="penal", min_casos_area=10) == 1


def test_agregado_segmenta_metricas_por_area():
    """A média global esconde a área ruim: `por_area` mede cada uma à parte."""
    metricas = [
        CasoMetrica(id="c1", area="civel", hit=True, recall=1.0, precision=0.5, rr=1.0),
        CasoMetrica(id="c2", area="civel", hit=True, recall=1.0, precision=0.5, rr=1.0),
        CasoMetrica(id="c3", area="Penal", hit=False, recall=0.0, precision=0.0, rr=0.0),
    ]
    ag = _agregar(metricas)
    assert ag.recall == round(2 / 3, 4)          # média global "boa"
    assert ag.por_area["civel"]["recall"] == 1.0
    assert ag.por_area["penal"]["recall"] == 0.0  # área ruim fica exposta
    assert ag.por_area["penal"]["n"] == 1


def test_caso_sem_area_aparece_no_relatorio():
    """Caso sem `area` não some na média — cai em '(sem_area)' e é visível."""
    ag = _agregar([CasoMetrica(id="c1", area="", hit=True, recall=1.0)])
    assert "(sem_area)" in ag.por_area


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
