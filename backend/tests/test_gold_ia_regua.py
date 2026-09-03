"""I7 — RÉGUA (gold set) das cinco capacidades de IA.

Trava três coisas:

1. o gold set candidato tem a forma e a governança prometidas (fictício,
   `status: "candidato"`, `atestado_por: null`, distribuição por área);
2. o runner `--mock` roda OFFLINE, é determinístico e produz relatório com
   score por caso e agregado — é isso que o CI pode rodar sem rede;
3. a pontuação PUNE o que não pode aparecer: promessa de resultado zera o caso,
   e caso candidato nunca é contado como cobertura atestada.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.eval import run_gold_ia

GOLD = Path(run_gold_ia.GOLD_PADRAO)


@pytest.fixture(scope="module")
def casos() -> list[dict]:
    return run_gold_ia.carregar_gold(str(GOLD))


# ── 1. Forma e governança do gold set ────────────────────────────────────────

def test_gold_set_tem_dez_casos_ficticios_e_candidatos(casos):
    assert len(casos) == 10
    for c in casos:
        assert c["ficticio"] is True, c["id"]
        assert c["status"] == "candidato", c["id"]
        assert c["atestado_por"] is None, c["id"]
        assert str(c["id"]).startswith("E2E-FICTICIO-"), c["id"]


def test_distribuicao_por_area_conforme_encomendado(casos):
    contagem: dict[str, int] = {}
    for c in casos:
        contagem[c["area"]] = contagem.get(c["area"], 0) + 1
    assert contagem == {"consumidor": 4, "civel": 3, "trabalhista": 2, "familia": 1}


def test_todo_caso_aponta_para_uma_das_cinco_capacidades(casos):
    from app.services.ai.core import capacidades

    for c in casos:
        assert c["capacidade"] in capacidades.CAPACIDADES, c["id"]


def test_todo_caso_tem_entrada_criterios_e_proibicoes(casos):
    for c in casos:
        assert "PERGUNTA" in c["entrada"] or "PEDIDO" in c["entrada"], c["id"]
        assert len(c["criterios"]) >= 4, c["id"]
        assert c["nao_deve_conter"], c["id"]
        # Citação é exigida por TIPO — número de súmula/artigo fica para o
        # curador humano conferir em fonte oficial.
        for tipo in c.get("citacoes_esperadas_tipo") or []:
            assert not any(ch.isdigit() for ch in tipo), (c["id"], tipo)


def test_ids_sao_unicos(casos):
    ids = [c["id"] for c in casos]
    assert len(ids) == len(set(ids))


# ── 2. Runner --mock: offline, determinístico, com relatório ─────────────────

def test_mock_gera_relatorio_completo(tmp_path):
    saida = tmp_path / "relatorio_gold_ia.json"
    assert run_gold_ia.main(["--mock", "--out", str(saida)]) == 0

    rel = json.loads(saida.read_text(encoding="utf-8"))
    assert rel["modo"] == "mock"
    # O relatório precisa DIZER que mock não mede qualidade jurídica — senão o
    # verde do CI é lido como "a IA está boa".
    assert rel["mede_qualidade_juridica"] is False
    assert rel["governanca"]["candidatos_nao_atestados"] == 10
    assert rel["governanca"]["atestados_por_humano"] == 0
    assert rel["governanca"]["aviso"]

    assert len(rel["por_caso"]) == 10
    for r in rel["por_caso"]:
        assert 0.0 <= r["score"] <= 1.0
        assert 0.0 <= r["cobertura_criterios"] <= 1.0
        assert set(r) >= {
            "id", "capacidade", "area", "score", "cobertura_criterios",
            "cobertura_citacoes_tipo", "conteudo_proibido", "aprovado",
        }

    ag = rel["agregado"]
    assert ag["global"]["n"] == 10
    assert 0.0 < ag["global"]["score_medio"] <= 1.0
    assert set(ag["por_area"]) == {"consumidor", "civel", "trabalhista", "familia"}
    assert set(ag["por_capacidade"]) <= {
        "analisar", "redigir", "resumir", "conversar", "extrair",
    }
    for bloco in list(ag["por_area"].values()) + list(ag["por_capacidade"].values()):
        assert bloco["n"] >= 1
        assert 0.0 <= bloco["score_medio"] <= 1.0


def test_mock_e_deterministico(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    assert run_gold_ia.main(["--mock", "--out", str(a)]) == 0
    assert run_gold_ia.main(["--mock", "--out", str(b)]) == 0
    ra = json.loads(a.read_text(encoding="utf-8"))
    rb = json.loads(b.read_text(encoding="utf-8"))
    assert ra["por_caso"] == rb["por_caso"]
    assert ra["agregado"] == rb["agregado"]


def test_mock_nao_toca_rede_nem_banco(monkeypatch, tmp_path):
    """`--mock` que abrisse sessão de banco não roda em CI — trava isso."""
    import app.core.database as db_mod

    def explode(*a, **kw):
        raise AssertionError("--mock não pode abrir sessão de banco")

    monkeypatch.setattr(db_mod, "AsyncSessionLocal", explode)
    assert run_gold_ia.main(["--mock", "--out", str(tmp_path / "r.json")]) == 0


# ── 3. Gates de regressão ────────────────────────────────────────────────────

def test_gate_de_score_falha_quando_o_piso_e_maior_que_o_resultado(tmp_path):
    saida = tmp_path / "r.json"
    assert run_gold_ia.main(["--mock", "--out", str(saida)]) == 0
    medio = json.loads(saida.read_text(encoding="utf-8"))["agregado"]["global"]["score_medio"]

    assert run_gold_ia.main(
        ["--mock", "--out", str(saida), "--min-score", "0.0"]) == 0
    assert run_gold_ia.main(
        ["--mock", "--out", str(saida), "--min-score", str(min(1.0, medio + 0.05))]) == 1


def test_gate_de_conteudo_proibido(tmp_path):
    saida = tmp_path / "r.json"
    # -1 é sempre menor que a contagem: prova que o gate corta, não decora.
    assert run_gold_ia.main(
        ["--mock", "--out", str(saida), "--max-proibidos", "-1"]) == 1


# ── 4. Pontuação ─────────────────────────────────────────────────────────────

def test_promessa_de_resultado_zera_o_caso():
    caso = {
        "id": "X", "capacidade": "analisar", "area": "civel",
        "criterios": ["identificar o vício do produto"],
        "citacoes_esperadas_tipo": [],
        "nao_deve_conter": ["vitória garantida"],
    }
    bom = run_gold_ia.pontuar(caso, "Cabe identificar o vício do produto no caso.")
    assert bom["score"] == 1.0 and bom["aprovado"] is True

    ruim = run_gold_ia.pontuar(
        caso, "Cabe identificar o vício do produto. Temos vitória garantida.")
    assert ruim["score"] == 0.0
    assert ruim["aprovado"] is False
    assert ruim["conteudo_proibido"] == ["vitória garantida"]


def test_criterio_nao_enfrentado_aparece_no_relatorio_do_caso():
    caso = {
        "id": "Y", "capacidade": "resumir", "area": "civel",
        "criterios": ["informar o valor da condenação",
                      "informar o que foi rejeitado pelo juízo"],
        "citacoes_esperadas_tipo": [], "nao_deve_conter": [],
    }
    r = run_gold_ia.pontuar(caso, "Informar o valor da condenação: R$ 10,00.")
    assert r["cobertura_criterios"] == 0.5
    assert r["criterios_nao_enfrentados"] == ["informar o que foi rejeitado pelo juízo"]
    assert r["aprovado"] is False


def test_citacao_por_tipo_pesa_no_score():
    caso = {
        "id": "Z", "capacidade": "analisar", "area": "consumidor",
        "criterios": ["apontar a responsabilidade solidária dos fornecedores"],
        "citacoes_esperadas_tipo": ["artigo do CDC sobre responsabilidade solidária"],
        "nao_deve_conter": [],
    }
    sem_fonte = run_gold_ia.pontuar(
        caso, "Cabe apontar a responsabilidade solidária dos fornecedores.")
    assert sem_fonte["cobertura_criterios"] == 1.0
    assert sem_fonte["cobertura_citacoes_tipo"] == 0.0
    assert sem_fonte["score"] == 0.6


# ── 5. O candidato não vira cobertura em nenhuma régua ───────────────────────

def test_governanca_do_acervo_nao_conta_candidato_como_gold_real():
    from app.eval.gold_governance import auditar_diretorio

    audit = auditar_diretorio(GOLD.parent)
    assert audit.erros == [], "\n".join(audit.erros)
    assert audit.casos_candidatos == 10
    # Candidato NÃO entra na cobertura por área: continua zero enquanto ninguém
    # atestar. Esse é o ponto da governança.
    for area in ("consumidor", "civel", "trabalhista", "familia"):
        assert audit.por_area.get(area, 0) == 0


def test_smoke_do_run_eval_valida_o_arquivo_de_candidatos():
    from app.eval.run_eval import _validar_caso_smoke

    for caso in run_gold_ia.carregar_gold(str(GOLD)):
        assert _validar_caso_smoke(caso, GOLD.name) == [], caso["id"]

    # E recusa candidato que tente se passar por atestado.
    falso = dict(run_gold_ia.carregar_gold(str(GOLD))[0])
    falso["atestado_por"] = "quem-nao-conferiu"
    assert any("atestado_por" in e for e in _validar_caso_smoke(falso, GOLD.name))
