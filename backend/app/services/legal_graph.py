"""Validação e indexação do grafo jurídico canônico do EJC.

O grafo descreve dependências conceituais entre fontes, jurisprudência, teses,
argumentos, pedidos e modelos. Relação de grafo nunca cria autoridade jurídica:
ela só pode ser usada operacionalmente depois que os nós envolvidos estiverem
aprovados no RAG.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any


RELACOES_VALIDAS = {
    "fundamentado_por",
    "cita",
    "aplica",
    "interpreta",
    "complementa",
    "complementar_a",
    "diverge_de",
    "supera",
    "distingue",
    "confirma",
    "relacionado_a",
    "utilizado_em",
    "depende_de",
    "contratese_de",
    "pedido_relacionado",
}


def validar_grafo(grafo: dict[str, Any] | None, canonical_ids: set[str]) -> list[str]:
    """Valida integridade referencial e vocabulário; retorna erros, sem exceção."""
    if not grafo:
        return []
    erros: list[str] = []
    nos = grafo.get("nos") or []
    arestas = grafo.get("arestas") or []
    if not isinstance(nos, list):
        return ["grafo.nos deve ser lista"]
    if not isinstance(arestas, list):
        return ["grafo.arestas deve ser lista"]

    nos_set = {str(n).strip() for n in nos if str(n).strip()}
    duplicados = len(nos_set) != len([n for n in nos if str(n).strip()])
    if duplicados:
        erros.append("grafo contém nós duplicados")

    desconhecidos = sorted(nos_set - canonical_ids)
    ausentes = sorted(canonical_ids - nos_set)
    if desconhecidos:
        erros.append("grafo referencia canonical_id inexistente: " + ", ".join(desconhecidos))
    if ausentes:
        erros.append("documentos sem nó correspondente no grafo: " + ", ".join(ausentes))

    vistos: set[tuple[str, str, str]] = set()
    for i, edge in enumerate(arestas, start=1):
        if not isinstance(edge, dict):
            erros.append(f"aresta {i} não é objeto")
            continue
        origem = str(edge.get("origem") or "").strip()
        destino = str(edge.get("destino") or "").strip()
        tipo = str(edge.get("tipo") or "").strip()
        if not origem or not destino or not tipo:
            erros.append(f"aresta {i} incompleta: origem, destino e tipo são obrigatórios")
            continue
        if origem == destino:
            erros.append(f"aresta {i} contém autorrelação: {origem}")
        if origem not in nos_set:
            erros.append(f"aresta {i} tem origem fora de nos: {origem}")
        if destino not in nos_set:
            erros.append(f"aresta {i} tem destino fora de nos: {destino}")
        if tipo not in RELACOES_VALIDAS:
            erros.append(f"aresta {i} usa relação desconhecida: {tipo}")
        chave = (origem, tipo, destino)
        if chave in vistos:
            erros.append(f"aresta duplicada: {origem} -[{tipo}]-> {destino}")
        vistos.add(chave)
    return erros


def indexar_relacoes(grafo: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    """Converte arestas em lista bidirecional por canonical_id para persistência JSONB."""
    indice: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if not grafo:
        return {}
    for edge in grafo.get("arestas") or []:
        if not isinstance(edge, dict):
            continue
        origem = str(edge.get("origem") or "").strip()
        destino = str(edge.get("destino") or "").strip()
        tipo = str(edge.get("tipo") or "").strip()
        if not origem or not destino or tipo not in RELACOES_VALIDAS:
            continue
        comum = {
            "tipo": tipo,
            "status": edge.get("status") or "pendente_validacao_dos_nos",
            "observacao": edge.get("observacao"),
        }
        indice[origem].append({**comum, "direcao": "saida", "outro": destino})
        indice[destino].append({**comum, "direcao": "entrada", "outro": origem})
    return dict(indice)


def filtrar_relacoes_aprovadas(
    relacoes: list[dict[str, Any]] | None,
    *,
    proprio_id: str,
    status_por_id: dict[str, str],
) -> list[dict[str, Any]]:
    """Só libera relação operacional quando os dois nós estão aprovados."""
    if status_por_id.get(proprio_id) != "aprovado":
        return []
    saida = []
    for rel in relacoes or []:
        outro = str(rel.get("outro") or "")
        if outro and status_por_id.get(outro) == "aprovado":
            saida.append(dict(rel))
    return saida
