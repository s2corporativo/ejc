from __future__ import annotations

import json
from pathlib import Path

from app.eval.gold_governance import (
    auditar_diretorio,
    avaliar_prontidao,
    validar_caso_real,
)


def _caso_ok() -> dict:
    return {
        "id": "cons-001",
        "area": "consumidor",
        "ficticio": False,
        "query": "questão jurídica pseudonimizada",
        "expected_titulos": ["fonte esperada"],
        "expected_citacoes": ["art. X da norma conferida"],
        "curadoria": {
            "curador": "advogado-area",
            "revisor": "revisor-independente",
            "revisado_em": "2026-08-08",
            "vigencia_conferida_em": "2026-08-08",
            "fontes_oficiais": [{
                "titulo": "Fonte oficial",
                "url": "https://www.planalto.gov.br/exemplo",
                "consultada_em": "2026-08-08",
            }],
        },
    }


def test_caso_real_exige_revisao_independente_e_fonte_oficial():
    caso = _caso_ok()
    assert validar_caso_real(caso) == []

    caso["curadoria"]["revisor"] = "advogado-area"
    caso["curadoria"]["fontes_oficiais"][0]["url"] = "https://example.com/lei"
    erros = validar_caso_real(caso)
    assert any("distintas" in e for e in erros)
    assert any("domínio oficial" in e for e in erros)


def test_caso_sintetico_nao_pode_se_passar_por_gold_real():
    caso = _caso_ok()
    caso["ficticio"] = True
    caso["expected_citacoes"] = ["SUMULA-FICTICIA-001"]
    erros = validar_caso_real(caso)
    assert any("ficticio deve ser false" in e for e in erros)
    assert any("fictícia" in e for e in erros)


def test_auditoria_ignora_example_na_cobertura(tmp_path: Path):
    (tmp_path / "gold_set.example.jsonl").write_text(
        json.dumps({"id": "x", "area": "civel", "query": "x"}) + "\n",
        encoding="utf-8",
    )
    audit = auditar_diretorio(tmp_path)
    assert audit.casos_reais == 0
    assert audit.arquivos_reais == 0


def test_auditoria_conta_apenas_caso_real_valido(tmp_path: Path):
    path = tmp_path / "gold_set.jsonl"
    path.write_text(json.dumps(_caso_ok(), ensure_ascii=False) + "\n", encoding="utf-8")
    audit = auditar_diretorio(tmp_path)
    assert audit.erros == []
    assert audit.casos_reais == 1
    assert audit.por_area == {"consumidor": 1}


def test_prontidao_falha_area_critica_sem_amostra_suficiente():
    from app.eval.gold_governance import AuditoriaGold

    audit = AuditoriaGold(
        arquivos_reais=1,
        casos_reais=12,
        por_area={"consumidor": 12},
    )
    erros = avaliar_prontidao(
        audit,
        areas=["consumidor", "trabalhista"],
        min_casos_area=10,
        min_total=10,
    )
    assert any("trabalhista" in e for e in erros)


def test_gold_sets_reais_do_repositorio_cumprem_governanca():
    # Este teste é o gate automático que já entra na suíte backend atual.
    # Enquanto só houver exemplos, ele não finge certificação; quando um
    # gold_set real for versionado, qualquer caso sem proveniência/LGPD falha CI.
    base = Path(__file__).parents[1] / "app" / "eval"
    audit = auditar_diretorio(base)
    assert audit.erros == [], "\n".join(audit.erros)
