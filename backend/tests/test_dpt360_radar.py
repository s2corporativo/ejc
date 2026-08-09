from app.modules.dpt360.radar_service import classify_area, impact_level


def test_classificacao_do_radar_por_termos_objetivos():
    assert classify_area("IBAMA", "Licenciamento ambiental", None) == "ambiental"
    assert classify_area("PGFN", "Transação tributária", None) == "tributario"
    assert classify_area("ANPD", "Dados pessoais", None) == "lgpd_ia"
    assert classify_area(None, "Tema sem vocabulário cadastrado", None) == "geral"


def test_impacto_so_existe_com_sinal_objetivo_da_empresa():
    assert impact_level("ambiental", {"ambiental"}) == "alta"
    assert impact_level("administrativo", {"licitacoes"}) == "alta"
    assert impact_level("tributario", {"trabalhista"}) is None
    assert impact_level("geral", {"empresarial"}) is None
