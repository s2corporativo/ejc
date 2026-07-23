from app.models.case import CaseArea
from app.services.ai_contextual import classificar_documento


def test_casearea_contem_areas_ampliadas():
    values = {area.value for area in CaseArea}
    assert {
        "saude",
        "medico",
        "agrario",
        "agronegocio",
        "eleitoral",
        "internacional",
        "contratual",
        "societario",
        "licitacoes",
    }.issubset(values)


def test_classificador_devolve_valores_canonicos_do_enum():
    samples = [
        ("jec.pdf", "Juizado Especial Cível, Lei 9.099 e recurso inominado", "civil"),
        ("saude.pdf", "Plano de saúde e negativa de cobertura de procedimento médico", "saude"),
        ("inquerito.pdf", "Inquérito policial instaurado pela autoridade policial contra o indiciado", "criminal"),
    ]
    valid = {area.value for area in CaseArea}
    for filename, text, expected in samples:
        result = classificar_documento(filename, text)
        assert result["area_sugerida"] == expected
        assert result["area_sugerida"] in valid
