from __future__ import annotations

import json
from pathlib import Path

import app.eval.gold_governance as gold_governance
from app.eval.gold_governance import (
    AuditoriaGold,
    auditar_diretorio,
    avaliar_prontidao,
    validar_caso_real,
)


def _caso_ok() -> dict:
    return {
        "id": "cons-001",
        "area": "consumidor",
        "cenario": "normal",
        "ficticio": False,
        "query": "questão jurídica pseudonimizada",
        "expected_titulos": ["fonte esperada"],
        "expected_citacoes": ["art. X da norma conferida"],
        "curadoria": {
            "curador": "advogado-area",
            "revisor": "revisor-independente",
            "revisado_em": "2026-08-08",
            "vigencia_conferida_em": "2026-08-08",
            "fontes_oficiais": [
                {
                    "titulo": "Fonte oficial",
                    "url": "https://www.planalto.gov.br/exemplo",
                    "consultada_em": "2026-08-08",
                    "identificador_versao": "Lei exemplo — texto compilado em 2026-08-08",
                }
            ],
        },
    }


def _caso_peca_ok() -> dict:
    caso = _caso_ok()
    caso.pop("query")
    caso.pop("expected_titulos")
    caso.pop("expected_citacoes")
    caso.update(
        {
            "id": "trab-peca-001",
            "area": "trabalhista",
            "cenario": "fronteira",
            "fatos": "Narrativa pseudonimizada do caso.",
            "tipo_peca_esperado": "peticao_inicial",
            "teses_esperadas": ["tese juridicamente conferida"],
            "jurisprudencia_esperada": ["precedente real conferido"],
            "criterios": ["pedidos coerentes com fatos e provas"],
        }
    )
    return caso


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
    assert any("placeholder/fonte fictícia" in e for e in erros)


def test_gold_de_pecas_rejeita_jurisprudencia_placeholder():
    caso = _caso_peca_ok()
    caso["jurisprudencia_esperada"] = ["SUMULA-FICTICIA-001"]

    erros = validar_caso_real(caso)

    assert any(
        "jurisprudencia_esperada contém placeholder/fonte fictícia" in e
        for e in erros
    )


def test_caso_real_precisa_ser_avaliavel_e_classificar_cenario():
    caso = _caso_ok()
    caso.pop("query")
    caso.pop("expected_titulos")
    caso.pop("cenario")

    erros = validar_caso_real(caso)

    assert any("query (RAG) ou fatos (peças)" in e for e in erros)
    assert any("cenario deve ser" in e for e in erros)


def test_gold_rag_exige_resultado_esperado_para_retrieval():
    caso = _caso_ok()
    caso["expected_titulos"] = []
    erros = validar_caso_real(caso)
    assert any("expected_titulos não vazio" in e for e in erros)


def test_gold_pecas_exige_campos_objetivamente_avaliaveis():
    caso = _caso_peca_ok()
    caso["tipo_peca_esperado"] = ""
    caso["teses_esperadas"] = []
    caso["criterios"] = []

    erros = validar_caso_real(caso)

    assert any("tipo_peca_esperado" in e for e in erros)
    assert any("teses_esperadas" in e for e in erros)
    assert any("criterios" in e for e in erros)


def test_curadoria_rejeita_data_futura_e_datas_posteriores_a_revisao():
    caso = _caso_ok()
    caso["curadoria"]["revisado_em"] = "2026-08-08"
    caso["curadoria"]["vigencia_conferida_em"] = "2099-01-01"
    caso["curadoria"]["fontes_oficiais"][0]["consultada_em"] = "2099-01-01"

    erros = validar_caso_real(caso)

    assert any("data futura" in e for e in erros)
    assert any("vigencia_conferida_em não pode ser posterior" in e for e in erros)
    assert any("consultada_em não pode ser posterior" in e for e in erros)


def test_fonte_exige_referencia_da_versao_revisada():
    caso = _caso_ok()
    fonte = caso["curadoria"]["fontes_oficiais"][0]
    fonte.pop("identificador_versao")

    erros = validar_caso_real(caso)

    assert any("identificador_versao ou hash_sha256" in e for e in erros)


def test_hash_de_fonte_quando_informado_precisa_ser_sha256():
    caso = _caso_ok()
    fonte = caso["curadoria"]["fontes_oficiais"][0]
    fonte.pop("identificador_versao")
    fonte["hash_sha256"] = "abc"

    erros = validar_caso_real(caso)

    assert any("hash_sha256 deve ter 64 caracteres hex" in e for e in erros)


def test_pii_em_campo_versionado_fora_da_lista_antiga_e_bloqueada():
    caso = _caso_ok()
    caso["metadados"] = {"observacao": "CPF 123.456.789-00"}

    erros = validar_caso_real(caso)

    assert any("PII detectada no payload versionado" in e for e in erros)
    assert any("CPF" in e for e in erros)


def test_sanitizer_indisponivel_bloqueia_gold(monkeypatch):
    def indisponivel():
        raise RuntimeError("sanitizer indisponível")

    monkeypatch.setattr(gold_governance, "_validador_pii", indisponivel)
    erros = validar_caso_real(_caso_ok())
    assert any("validação de PII indisponível" in e for e in erros)


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
    path.write_text(
        json.dumps(_caso_ok(), ensure_ascii=False) + "\n", encoding="utf-8"
    )
    audit = auditar_diretorio(tmp_path)
    assert audit.erros == []
    assert audit.casos_reais == 1
    assert audit.por_area == {"consumidor": 1}
    assert audit.por_cenario == {"normal": 1}


def test_auditoria_rejeita_id_duplicado_entre_arquivos(tmp_path: Path):
    caso = _caso_ok()
    (tmp_path / "gold_set_a.jsonl").write_text(
        json.dumps(caso, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "gold_set_b.jsonl").write_text(
        json.dumps(caso, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    audit = auditar_diretorio(tmp_path)

    assert audit.casos_reais == 1
    assert any(
        "gold_set_b.jsonl:1" in e
        and "id duplicado" in e
        and "gold_set_a.jsonl:1" in e
        for e in audit.erros
    )


def test_auditoria_preserva_numero_da_linha_fisica_do_jsonl(tmp_path: Path):
    path = tmp_path / "gold_set.jsonl"
    invalido = _caso_ok()
    invalido["id"] = "sem-cenario"
    invalido.pop("cenario")
    path.write_text(
        "# cabeçalho\n\n# observação\n"
        + json.dumps(invalido, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    audit = auditar_diretorio(tmp_path)

    assert any(
        erro.startswith("gold_set.jsonl:4 (sem-cenario):") for erro in audit.erros
    )


def test_prontidao_falha_area_critica_sem_amostra_suficiente():
    audit = AuditoriaGold(
        arquivos_reais=1,
        casos_reais=12,
        por_area={"consumidor": 12},
        por_cenario={"normal": 12},
    )
    erros = avaliar_prontidao(
        audit,
        areas=["consumidor", "trabalhista"],
        min_casos_area=10,
        min_total=10,
    )
    assert any("trabalhista" in e for e in erros)


def test_prontidao_exige_cobertura_de_normal_fronteira_e_excecao():
    audit = AuditoriaGold(
        arquivos_reais=1,
        casos_reais=20,
        por_area={"consumidor": 20},
        por_cenario={"normal": 20},
    )

    erros = avaliar_prontidao(
        audit,
        cenarios=["normal", "fronteira", "excecao"],
        min_casos_cenario=2,
    )

    assert any("cenário fronteira" in e for e in erros)
    assert any("cenário excecao" in e for e in erros)


def test_gold_sets_reais_do_repositorio_cumprem_governanca():
    # Este teste é o gate automático que já entra na suíte backend atual.
    # Enquanto só houver exemplos, ele não finge certificação; quando um
    # gold_set real for versionado, qualquer caso sem proveniência/LGPD falha CI.
    base = Path(__file__).parents[1] / "app" / "eval"
    audit = auditar_diretorio(base)
    assert audit.erros == [], "\n".join(audit.erros)
