"""Regressões P0.1 para identificação conservadora de situação normativa.

Estes testes são deliberadamente sem rede/banco: verificam apenas a decisão
local dos ingestores. O objetivo é impedir dois erros jurídicos simétricos:
- revogar o diploma atual porque sua ementa menciona OUTRA norma revogada;
- deixar passar um ato cujo próprio título traz marcador direto de revogação.
"""

from app.services.ingestors import lexml, planalto


def _blocos_preambulo(texto: str):
    """Monta o shape mínimo aceito por planalto.situacao_juridica."""
    # O parser exige preâmbulo identificável com >= 80 caracteres.
    preambulo = texto + "\n" + ("Texto institucional do diploma. " * 5)
    return [(None, preambulo), ("Art. 1", "Art. 1º Texto do artigo.")]


def test_planalto_referencia_a_outra_lei_revogada_nao_revoga_diploma_atual():
    blocos = _blocos_preambulo(
        "LEI Nº 14.133, DE 1º DE ABRIL DE 2021\n"
        "Altera a Lei nº 8.666/1993, revogada pela Lei nº 14.133/2021, "
        "e dá outras providências."
    )

    status = planalto.situacao_juridica(blocos)

    assert status["legal_status"] == "vigencia_nao_verificada"
    assert status["legal_status_origem"] == "planalto:texto_compilado"
    assert "legal_status_inferido_em" in status
    assert "legal_status_verificado_em" not in status


def test_planalto_marcador_do_proprio_diploma_no_cabecalho_e_revogacao_verificada():
    blocos = _blocos_preambulo(
        "LEI Nº 8.666, DE 21 DE JUNHO DE 1993\n"
        "(Revogada pela Lei nº 14.133, de 2021)\n"
        "Regulamenta o art. 37, inciso XXI, da Constituição Federal."
    )

    status = planalto.situacao_juridica(blocos)

    assert status["legal_status"] == "revogada"
    assert status["legal_status_origem"] == "planalto:texto_compilado"
    assert "legal_status_verificado_em" in status
    assert "legal_status_inferido_em" not in status


def test_lexml_titulo_com_marcador_parentetico_direto_e_revogado():
    item = {
        "titulo": "Lei nº 8.666, de 21 de junho de 1993 (Revogada)",
        "ementa": "Norma histórica de licitações e contratos.",
    }

    assert lexml.situacao_juridica(item, "legislacao") == "revogada"


def test_lexml_titulo_com_marcador_final_direto_e_revogado():
    item = {
        "titulo": "Lei nº 8.666, de 21 de junho de 1993 — Revogada",
        "ementa": "Norma histórica de licitações e contratos.",
    }

    assert lexml.situacao_juridica(item, "legislacao") == "revogada"


def test_lexml_forma_ativa_revoga_outra_norma_nao_autorrevoga_item():
    item = {
        "titulo": "Lei nº 14.133/2021 — Revoga a Lei nº 8.666/1993",
        "ementa": "Lei de Licitações e Contratos Administrativos.",
    }

    assert lexml.situacao_juridica(item, "legislacao") is None


def test_lexml_ementa_nao_e_prova_de_autorrevogacao():
    item = {
        "titulo": "Lei nº 14.133, de 1º de abril de 2021",
        "ementa": "Revoga a Lei nº 8.666/1993 e dá outras providências.",
    }

    assert lexml.situacao_juridica(item, "legislacao") is None
