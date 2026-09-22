"""Semântica das métricas internas de jurimetria.

Testes puros, sem banco: acordo é composição consensual e não pode ser somado
à taxa de êxito judicial usada como histórico de sucesso.
"""
from app.services.jurimetria import _resumo


def test_acordo_e_separado_de_exito_judicial():
    out = _resumo([
        "exito_total",
        "exito_parcial",
        "acordo",
        "improcedente",
        "outro",
    ])

    assert out["n"] == 5
    assert out["taxa_exito"] == 40.0
    assert out["taxa_acordo"] == 20.0
    assert out["taxa_desfecho_favoravel_ou_acordo"] == 60.0
    # Alias legado preservado apenas por compatibilidade.
    assert out["taxa_exito_com_acordo"] == 60.0


def test_sem_amostra_taxas_ficam_nulas():
    out = _resumo([])
    assert out["taxa_exito"] is None
    assert out["taxa_acordo"] is None
    assert out["taxa_desfecho_favoravel_ou_acordo"] is None
