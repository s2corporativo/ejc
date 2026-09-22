from app.services.research_contract import (
    classificar_autoridade,
    montar_envelope,
    montar_fonte,
)


def test_material_interno_nao_e_promovido_a_fonte_oficial():
    item = {
        "titulo": "Modelo simulado EJC",
        "categoria": "modelo_documento_juridico",
        "fonte": "https://www.planalto.gov.br/nao-e-a-fonte-do-modelo",
        "extra": {"ficticio": True, "origem": "modelo"},
    }
    assert classificar_autoridade(item) == "material_interno"
    assert any("Material interno" in alerta for alerta in montar_fonte(item)["alertas"])


def test_precedente_qualificado_e_exposto_com_proveniencia():
    item = {
        "doc_id": "d1",
        "titulo": "Tema Repetitivo 466/STJ",
        "categoria": "jurisprudencia_estruturada",
        "fonte": "https://processo.stj.jus.br/repetitivos/temas_repetitivos/pesquisa.jsp",
        "tribunal": "STJ",
        "versao": 2,
        "confianca": "alta",
        "extra": {"identificador": "Tema 466", "confidence_level": "alta"},
    }
    fonte = montar_fonte(item)
    assert fonte["autoridade"] == "precedente_vinculante"
    assert fonte["identificador"] == "Tema 466"
    assert fonte["fonte_oficial"].startswith("https://")


def test_envelope_sempre_exibe_limites_e_lacunas():
    envelope = montar_envelope(
        resposta="Não há base suficiente.",
        pergunta="Qual é a tese?",
        contexto=[],
        pii_removida=False,
        log_id="log-1",
    )
    assert envelope["rascunho"] is True
    assert envelope["revisao_humana_obrigatoria"] is True
    assert envelope["fontes_relevantes"] == 0
    assert envelope["lacunas"]
    assert envelope["limites"]
