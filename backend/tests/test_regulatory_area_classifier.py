from app.services.regulatory_area_classifier import (
    AREA_CASE_ALIASES,
    classify_area,
    impact_level,
)


def test_classificador_compartilhado_preserva_contrato_do_radar() -> None:
    assert classify_area("IBAMA", "Licenciamento ambiental", None) == "ambiental"
    assert classify_area("PGFN", "Transação tributária", None) == "tributario"
    assert classify_area("ANPD", "Dados pessoais", None) == "lgpd_ia"
    assert classify_area(None, "Tema sem vocabulário cadastrado", None) == "geral"


def test_classificador_compartilhado_preserva_reforma_tributaria() -> None:
    assert classify_area(None, "Split payment na nova sistemática", None) == "tributario"
    assert classify_area(None, "Regulamentação da LC 214/2025", None) == "tributario"
    assert classify_area("Imposto Seletivo", None, None) == "tributario"


def test_aliases_e_impacto_sao_neutros_em_relacao_ao_dpt() -> None:
    assert AREA_CASE_ALIASES["administrativo"] == {"administrativo", "licitacoes"}
    assert impact_level("ambiental", {"ambiental"}) == "alta"
    assert impact_level("administrativo", {"licitacoes"}) == "alta"
    assert impact_level("tributario", {"trabalhista"}) is None
    assert impact_level("geral", {"empresarial"}) is None
