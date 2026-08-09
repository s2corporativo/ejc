import pytest

from app.modules.dpt360.diagnostic_service import DIAGNOSTIC_AREAS, _evidence_map


class Profile:
    areas_com_casos = ["ambiental", "tributario"]
    documentos = 4
    autos_ambientais = 1
    sociedades = 0
    operacoes_lgpd = 0


def test_diagnostico_completo_cobre_sete_eixos_sem_score():
    assert DIAGNOSTIC_AREAS["completo"] == [
        "tributario",
        "ambiental",
        "administrativo",
        "trabalhista",
        "contratual",
        "lgpd",
        "governanca_ia",
    ]


def test_mapa_de_evidencias_distingue_presenca_de_lacuna():
    evidence = _evidence_map(Profile())
    assert any(item["presente"] for item in evidence["ambiental"])
    assert next(item for item in evidence["lgpd"] if item["tipo"] == "ropa")[
        "presente"
    ] is False
    assert next(
        item
        for item in evidence["governanca_ia"]
        if item["tipo"] == "inventario_ia"
    )["presente"] is False


def test_documento_generico_nao_preenche_evidencia_de_area():
    evidence = _evidence_map(Profile())
    all_types = {item["tipo"] for items in evidence.values() for item in items}
    assert "documentos_vinculados" not in all_types
    assert all("document" not in item_type for item_type in all_types)


def test_lacuna_nao_e_modelada_como_irregularidade():
    evidence = _evidence_map(Profile())
    assert all(
        "irregular" not in str(item).lower()
        for items in evidence.values()
        for item in items
    )


def test_tipo_desconhecido_nao_e_convertido_em_completo():
    assert "qualquer_coisa" not in DIAGNOSTIC_AREAS
    with pytest.raises(KeyError):
        _ = DIAGNOSTIC_AREAS["qualquer_coisa"]  # type: ignore[index]
