from app.modules.dpt360.radar_service import classify_area, impact_level


def test_classificacao_do_radar_por_termos_objetivos():
    assert classify_area("IBAMA", "Licenciamento ambiental", None) == "ambiental"
    assert classify_area("PGFN", "Transação tributária", None) == "tributario"
    assert classify_area("ANPD", "Dados pessoais", None) == "lgpd_ia"
    assert classify_area(None, "Tema sem vocabulário cadastrado", None) == "geral"


def test_classificacao_reconhece_termos_da_reforma_tributaria():
    """Os termos de busca da reforma (radar_legislativo.TERMOS_POR_RAMO) só têm
    efeito prático se também classificarem como "tributario" aqui — senão o
    alerta capturado cai em "geral" e nunca chega ao impact_level da empresa."""
    assert classify_area(None, "Split payment na nova sistemática", None) == "tributario"
    assert classify_area(None, "Regulamentação da LC 214/2025", None) == "tributario"
    assert classify_area("Imposto Seletivo", None, None) == "tributario"


def test_impacto_so_existe_com_sinal_objetivo_da_empresa():
    assert impact_level("ambiental", {"ambiental"}) == "alta"
    assert impact_level("administrativo", {"licitacoes"}) == "alta"
    assert impact_level("tributario", {"trabalhista"}) is None
    assert impact_level("geral", {"empresarial"}) is None
