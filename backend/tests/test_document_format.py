"""Padronização de documentos jurídicos (Fase 5) — remove markdown bruto/mojibake.

Cobre o achado do laudo sobre "asteriscos brutos" em saídas de IA.
"""
from app.services.document_format import (
    sem_caracteres_problematicos,
    padronizar_documento_juridico,
    aviso_rascunho_ia,
)


def test_remove_asteriscos_de_markdown():
    assert padronizar_documento_juridico("texto **importante** aqui") == "texto importante aqui"


def test_remove_titulos_markdown():
    assert padronizar_documento_juridico("# Titulo\n## Fatos") == "Titulo\nFatos"


def test_remove_blockquote():
    assert padronizar_documento_juridico("> citacao relevante") == "citacao relevante"


def test_normaliza_checkbox():
    assert padronizar_documento_juridico("[ ] pendente [x] feito") == "( ) pendente (x) feito"


def test_converte_acentos_para_ascii():
    assert sem_caracteres_problematicos("ação coração") == "acao coracao"


def test_simbolo_paragrafo():
    assert sem_caracteres_problematicos("§") == "paragrafo"


def test_entrada_vazia():
    assert padronizar_documento_juridico(None) == ""
    assert padronizar_documento_juridico("") == ""


def test_aviso_rascunho_marca_ia():
    aviso = aviso_rascunho_ia()
    assert "RASCUNHO" in aviso
    assert "REVISAO" in aviso
