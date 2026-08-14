from app.services.legal_graph import (
    filtrar_relacoes_aprovadas,
    indexar_relacoes,
    validar_grafo,
)


def _grafo():
    return {
        "nos": ["JUR-1", "TESE-1"],
        "arestas": [
            {
                "origem": "JUR-1",
                "tipo": "fundamentado_por",
                "destino": "TESE-1",
                "status": "pendente_validacao_dos_nos",
            }
        ],
    }


def test_grafo_valido_sem_erros():
    assert validar_grafo(_grafo(), {"JUR-1", "TESE-1"}) == []


def test_grafo_rejeita_no_inexistente_e_relacao_desconhecida():
    grafo = {
        "nos": ["JUR-1", "FANTASMA"],
        "arestas": [{"origem": "JUR-1", "tipo": "prova_magica", "destino": "FANTASMA"}],
    }
    erros = validar_grafo(grafo, {"JUR-1", "TESE-1"})
    assert any("canonical_id inexistente" in e for e in erros)
    assert any("relação desconhecida" in e for e in erros)
    assert any("sem nó correspondente" in e for e in erros)


def test_indexacao_e_bidirecional():
    indice = indexar_relacoes(_grafo())
    assert indice["JUR-1"][0]["direcao"] == "saida"
    assert indice["JUR-1"][0]["outro"] == "TESE-1"
    assert indice["TESE-1"][0]["direcao"] == "entrada"
    assert indice["TESE-1"][0]["outro"] == "JUR-1"


def test_relacao_so_e_operacional_com_ambos_nos_aprovados():
    relacoes = indexar_relacoes(_grafo())["JUR-1"]
    assert filtrar_relacoes_aprovadas(
        relacoes, proprio_id="JUR-1", status_por_id={"JUR-1": "aprovado", "TESE-1": "pendente"}
    ) == []
    liberadas = filtrar_relacoes_aprovadas(
        relacoes, proprio_id="JUR-1", status_por_id={"JUR-1": "aprovado", "TESE-1": "aprovado"}
    )
    assert len(liberadas) == 1
