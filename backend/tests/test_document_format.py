"""Padronização de documentos jurídicos (Fase 5) — remove markdown bruto/mojibake.

Cobre o achado do laudo sobre "asteriscos brutos" em saídas de IA e a correção
da auditoria funcional: acentuação pt-BR PRESERVADA no conteúdo armazenado
("Petição" nunca vira "Peticao"); a dobra ASCII vive só em ascii_seguro()
(nomes de arquivo).
"""
from app.services.document_format import (
    ascii_seguro,
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


def test_preserva_acentuacao_pt_br():
    # Texto jurídico armazenado/exibido NUNCA perde acentuação.
    assert sem_caracteres_problematicos("ação coração") == "ação coração"


def test_peticao_permanece_peticao_ao_salvar():
    # Regressão da auditoria: título/conteúdo salvos preservam "Petição".
    assert padronizar_documento_juridico("# **Petição Inicial**") == "Petição Inicial"
    assert "Petição" in padronizar_documento_juridico(
        "PETIÇÃO INICIAL\n\nA presente Petição versa sobre ação de cobrança."
    )


def test_simbolos_juridicos_preservados():
    assert sem_caracteres_problematicos("§ 1º, art. 5ª") == "§ 1º, art. 5ª"


def test_repara_mojibake_para_acentos_corretos():
    assert sem_caracteres_problematicos("PetiÃ§Ã£o") == "Petição"


def test_normaliza_travessao_e_aspas_curvas():
    assert sem_caracteres_problematicos("caso — “urgente”") == 'caso - "urgente"'


def test_remove_caracteres_de_controle_e_zero_width():
    assert sem_caracteres_problematicos("Pet​ição\x00") == "Petição"


def test_ascii_seguro_para_nomes_de_arquivo():
    # A dobra ASCII antiga continua disponível SÓ para filename/legado.
    assert ascii_seguro("ação coração") == "acao coracao"
    assert ascii_seguro("§") == "paragrafo"


def test_entrada_vazia():
    assert padronizar_documento_juridico(None) == ""
    assert padronizar_documento_juridico("") == ""


def test_aviso_rascunho_marca_ia():
    aviso = aviso_rascunho_ia()
    assert "RASCUNHO" in aviso
    assert "REVISÃO" in aviso
