from app.eval.check_public_sources import _allowed


def test_monitor_aceita_apenas_https_em_dominios_oficiais():
    assert _allowed("https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm")
    assert _allowed("https://portal.stf.jus.br/jurisprudenciaRepercussao/tema.asp?num=69")
    assert not _allowed("http://www.planalto.gov.br/lei")
    assert not _allowed("https://example.com/lei")
