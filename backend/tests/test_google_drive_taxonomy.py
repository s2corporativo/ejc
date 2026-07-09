from app.services.google_drive_taxonomy import classificar_drive_file


def test_exclui_arquivo_de_teste():
    d = classificar_drive_file("teste_ejc_drive.txt", "/geral")
    assert d.excluir is True
    assert d.categoria == "nao_indexar"
    assert d.prioridade == 0


def test_classifica_pecas_praticas_penal_como_modelo():
    d = classificar_drive_file(
        "Indulto 2024 PRD - Extinção de puniblidade.docx",
        "/geral/PEÇAS PRÁTICAS EM PENAL",
    )
    assert d.excluir is False
    assert d.categoria == "modelo_documento_juridico"
    assert d.area_juridica == "penal_execucao"
    assert d.prioridade == 70


def test_classifica_lei_execucao_penal_como_legislacao_penal():
    d = classificar_drive_file("Lei de Execução Penal - LEP.pdf", "/01_LEGISLACAO/PENAL")
    assert d.categoria == "legislacao_penal"
    assert d.prioridade == 100


def test_classifica_sumula_stj():
    d = classificar_drive_file("Súmula 611 STJ.pdf", "/02_SUMULAS/STJ")
    assert d.categoria == "sumula_stj"
    assert d.prioridade == 95
