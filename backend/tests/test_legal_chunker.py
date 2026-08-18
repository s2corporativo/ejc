from app.services.legal_chunker import chunk_documento_juridico


def test_jurisprudencia_preserva_heading_em_subchunks():
    texto = "## RATIO DECIDENDI\n\n" + ("Fundamento jurídico completo. " * 150)
    chunks = chunk_documento_juridico(
        texto, tipo_camada="jurisprudencia_estruturada", max_chars=900
    )
    assert len(chunks) > 1
    assert all(c.startswith("## RATIO DECIDENDI") for c in chunks)


def test_heading_nao_some_quando_corpo_isolado_cabe_no_limite():
    heading = "## " + ("CONTEXTO " * 20)
    corpo = "Fundamento. " * 55
    texto = heading + "\n\n" + corpo
    chunks = chunk_documento_juridico(
        texto, tipo_camada="jurisprudencia_estruturada", max_chars=900
    )
    assert chunks
    assert all(c.startswith("## ") for c in chunks)


def test_legislacao_prefere_fronteira_de_artigo_com_ordinal():
    texto = (
        "Preâmbulo.\n\n"
        "Art. 1º Regra primeira.\nParágrafo único. Complemento.\n\n"
        "Art. 2º Regra segunda.\n§ 1º Detalhe."
    )
    chunks = chunk_documento_juridico(texto, tipo_camada="fonte_primaria", max_chars=900)
    assert any(c.startswith("Art. 1º") for c in chunks)
    assert any(c.startswith("Art. 2º") for c in chunks)


def test_tese_mantem_secoes_separadas():
    texto = "# TESE\n\nResumo.\n\n## REQUISITOS\n\n1. fato.\n\n## PROVAS\n\nDocumento."
    chunks = chunk_documento_juridico(texto, tipo_camada="tese_juridica", max_chars=900)
    assert any("## REQUISITOS" in c for c in chunks)
    assert any("## PROVAS" in c for c in chunks)


def test_texto_vazio_nao_cria_chunk():
    assert chunk_documento_juridico("   ", tipo_camada="tese_juridica") == []
