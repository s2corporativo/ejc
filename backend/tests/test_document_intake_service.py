from app.services.document_intake_service import (
    dividir_em_chunks_juridicos,
    extrair_sinais_documento,
    montar_dossie_documental,
)


def test_dividir_em_chunks_preserva_inicio_meio_e_fim():
    texto = (
        "INÍCIO DOS FATOS\n" + "A" * 7000 +
        "\n\nPEDIDO DE TUTELA DE URGÊNCIA COM VALOR DA CAUSA R$ 12.000,00\n" +
        "B" * 7000 +
        "\n\nFINAL DO DOCUMENTO COM PROVA DOCUMENTAL E PRAZO"
    )

    chunks = dividir_em_chunks_juridicos(texto, chunk_size=3000, overlap=200)

    assert len(chunks) > 3
    assert chunks[0].texto.startswith("INÍCIO DOS FATOS")
    assert "FINAL DO DOCUMENTO" in chunks[-1].texto


def test_extrair_sinais_documento_detecta_dados_juridicos():
    texto = """
    Processo 1234567-89.2024.8.13.0027.
    Autor CPF 123.456.789-00, empresa CNPJ 12.345.678/0001-99.
    Valor da causa R$ 25.000,00. Audiência em 10/07/2026.
    contato@exemplo.com
    """

    sinais = extrair_sinais_documento(texto)

    assert sinais.numeros_processo == ["1234567-89.2024.8.13.0027"]
    assert sinais.cpfs == ["123.456.789-00"]
    assert sinais.cnpjs == ["12.345.678/0001-99"]
    assert sinais.valores_monetarios == ["R$ 25.000,00"]
    assert sinais.datas == ["10/07/2026"]
    assert sinais.emails == ["contato@exemplo.com"]


def test_montar_dossie_documental_nao_fica_so_no_primeiro_trecho():
    inicio = "INÍCIO: qualificação das partes e narrativa inicial.\n" + "A" * 5000
    meio = "\n\nTRECHO CENTRAL: pedido liminar, prova documental, prazo e valor da causa R$ 9.999,00.\n" + "B" * 5000
    final = "\n\nFINAL: documentos faltantes, riscos, audiência e providências urgentes."
    texto = inicio + meio + final

    dossie = montar_dossie_documental(texto, titulo="Caso de teste", max_chars=9000)

    assert "DOSSIÊ DOCUMENTAL JURÍDICO" in dossie
    assert "INÍCIO:" in dossie
    assert "TRECHO CENTRAL" in dossie
    assert "FINAL:" in dossie
    assert "R$ 9.999,00" in dossie
