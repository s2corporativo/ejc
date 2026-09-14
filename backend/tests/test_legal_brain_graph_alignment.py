from app.services.legal_brain import (
    PrecedentPropositionStatus,
    evaluate_proposition_validity,
)
from app.services.legal_graph import RELACOES_VALIDAS, indexar_relacoes, validar_grafo


def test_grafo_canônico_aceita_relacoes_de_validade_temporal():
    esperadas = {
        "confirma",
        "distingue",
        "limita",
        "supera",
        "afetado_por_tema",
        "afetado_por_sumula",
        "afetado_por_alteracao_legislativa",
    }
    assert esperadas <= RELACOES_VALIDAS

    grafo = {
        "nos": ["prop-1", "fonte-2"],
        "arestas": [
            {"origem": "prop-1", "destino": "fonte-2", "tipo": "supera"},
        ],
    }
    assert validar_grafo(grafo, {"prop-1", "fonte-2"}) == []


def test_validade_consumidora_do_indice_canônico_do_grafo():
    grafo = {
        "nos": ["prop-1", "fonte-2", "fonte-3"],
        "arestas": [
            {"origem": "prop-1", "destino": "fonte-2", "tipo": "confirma"},
            {"origem": "prop-1", "destino": "fonte-3", "tipo": "supera"},
        ],
    }
    indice = indexar_relacoes(grafo)
    result = evaluate_proposition_validity("prop-1", indice["prop-1"])

    assert result.status == PrecedentPropositionStatus.SUPERADA
    assert result.decisive_relation == "supera"
    assert result.related_source_ids == ("fonte-2", "fonte-3")


def test_relacao_sem_no_rastreavel_nao_promove_status():
    result = evaluate_proposition_validity(
        "prop-1",
        [{"tipo": "confirma", "outro": ""}],
    )
    assert result.status == PrecedentPropositionStatus.NAO_VERIFICADA
