# ── tests/test_radar_poder.py ─────────────────────────────────────────────────
# Parser de matérias do Senado (Dados Abertos) — função pura, sem rede.
from app.services.radar_poder import _parse_materias_senado


def _payload(materias):
    return {"PesquisaBasicaMateria": {"Materias": {"Materia": materias}}}


def test_parse_lista_de_materias_normaliza_shape():
    m = {
        "IdentificacaoMateria": {
            "CodigoMateria": "160500",
            "SiglaSubtipoMateria": "PL",
            "NumeroMateria": "1234",
            "AnoMateria": "2026",
        },
        "EmentaMateria": "Altera a tributação de PIS/COFINS.",
    }
    saida = _parse_materias_senado(_payload([m]))
    assert saida == [{
        "id": 160500,
        "siglaTipo": "PL",
        "numero": 1234,
        "ano": 2026,
        "ementa": "Altera a tributação de PIS/COFINS.",
        "casa": "senado",
        "link": "https://www25.senado.leg.br/web/atividade/materias/-/materia/160500",
    }]


def test_parse_materia_unica_vem_como_dict_nao_lista():
    """O Senado devolve dict (não lista) quando há exatamente 1 resultado."""
    m = {
        "IdentificacaoMateria": {
            "CodigoMateria": "999",
            "SiglaTipoMateria": "PEC",
            "NumeroMateria": "7",
            "AnoMateria": "2026",
        },
        "DadosBasicosMateria": {"EmentaMateria": "Ementa aninhada."},
    }
    saida = _parse_materias_senado(_payload(m))
    assert len(saida) == 1
    assert saida[0]["siglaTipo"] == "PEC"
    assert saida[0]["ementa"] == "Ementa aninhada."


def test_parse_payload_vazio_ou_sem_codigo_nao_quebra():
    assert _parse_materias_senado({}) == []
    assert _parse_materias_senado(_payload([])) == []
    assert _parse_materias_senado(_payload([{"EmentaMateria": "sem id"}])) == []
