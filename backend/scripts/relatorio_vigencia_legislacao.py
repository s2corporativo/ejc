#!/usr/bin/env python
# ── scripts/relatorio_vigencia_legislacao.py ─────────────────────────────────
# Onda 3/4 da Refatoração Total — "Verificação de vigência dos docs
# legal_status_unverified; bloquear norma não vigente na geração de peça".
#
# Este script entrega a metade SEGURA e imediatamente executável do achado:
# um relatório de TRIAGEM, somente leitura, para priorizar a revisão humana
# da vigência de legislação na base RAG. NÃO altera nenhum dado, e
# DELIBERADAMENTE não tenta bloquear a citação em geração de peça — essa
# parte exige tocar o gate anti-alucinação (citation_gate.py /
# verificador_jurisprudencia.py / citation_check.py), cuja verificação real
# depende de Postgres com o schema completo (RUN_DB_TESTS=1) para não
# arriscar enfraquecer silenciosamente o gate (regra crítica do CLAUDE.md);
# fica registrado como pendência de sessão própria com ambiente de banco.
#
# O QUE O RELATÓRIO MOSTRA (reaproveita a MESMA lógica de
# knowledge_governance.health_snapshot — nenhum critério novo, nenhuma
# segunda fonte de verdade):
#   1. Legislação com vigência NÃO VERIFICADA (extra.legal_status ausente ou
#      "vigencia_nao_verificada") — candidatos a revisão, ordenados por
#      relevância aparente (nº de chunks/embeddings — proxy de uso no RAG).
#   2. CONTRADIÇÕES: doc marcado vigente=TRUE (versão atual no EJC) mas cujo
#      legal_status já foi explicitamente registrado como "revogada" ou
#      "suspensa" — o par mais perigoso, porque hoje NADA impede esse
#      documento de ser citado como direito em vigor (achado da auditoria).
#
# Execução (container ejc_backend):
#     docker exec -it ejc_backend python -m scripts.relatorio_vigencia_legislacao
#     docker exec -it ejc_backend python -m scripts.relatorio_vigencia_legislacao --formato json
from __future__ import annotations

import argparse
import asyncio
import json
import logging

from app.core.database import AsyncSessionLocal
from app.services.knowledge_governance import (
    _active_docs,
    _chunk_metrics,
    inferir_situacao_juridica,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ejc.relatorio_vigencia")

CODIGOS_CONTRADITORIOS = {"revogada", "parcialmente_revogada", "suspensa"}


async def _levantar(db) -> dict:
    """Monta o relatório. Função pura o bastante para testar sem banco real
    injetando `db` fake — só usa o que `_active_docs`/`_chunk_metrics` (já
    testados em knowledge_governance) devolvem."""
    # include_history=False já filtra vigente=TRUE na query (só a versão
    # atual de cada doc — histórico marcado vigente=False fica de fora).
    docs = await _active_docs(db, include_history=False)
    metrics = await _chunk_metrics(db)

    nao_verificados: list[dict] = []
    contraditorios: list[dict] = []

    for doc in docs:
        situacao = inferir_situacao_juridica(doc)
        metric = metrics.get(doc.id, {"chunks": 0, "embedded": 0})

        if situacao["code"] == "vigencia_nao_verificada":
            nao_verificados.append({
                "id": doc.id,
                "titulo": doc.titulo,
                "categoria": doc.categoria,
                "fonte": doc.fonte,
                "chunks": metric.get("chunks", 0),
                "embedded_chunks": metric.get("embedded", 0),
            })
        elif situacao["code"] in CODIGOS_CONTRADITORIOS:
            contraditorios.append({
                "id": doc.id,
                "titulo": doc.titulo,
                "categoria": doc.categoria,
                "legal_status": situacao["code"],
                "label": situacao["label"],
                "chunks": metric.get("chunks", 0),
                "embedded_chunks": metric.get("embedded", 0),
            })

    # Mais chunks/embeddings ≈ mais superfície de citação possível pela IA —
    # prioriza a revisão pelo maior risco de aparecer numa peça.
    nao_verificados.sort(key=lambda r: r["embedded_chunks"], reverse=True)
    contraditorios.sort(key=lambda r: r["embedded_chunks"], reverse=True)

    return {
        "total_docs_ativos": len(docs),
        "vigencia_nao_verificada": {
            "total": len(nao_verificados),
            "documentos": nao_verificados,
        },
        "contradicao_vigente_mas_status_nao_atual": {
            "total": len(contraditorios),
            "documentos": contraditorios,
            "explicacao": (
                "Documento marcado como versão ATUAL no EJC (vigente=TRUE), mas "
                "cujo legal_status já foi registrado como revogado/suspenso pela "
                "governança — hoje nada impede que a IA cite este texto como "
                "direito em vigor. Prioridade de revisão."
            ),
        },
    }


def _imprimir_texto(relatorio: dict) -> None:
    print(f"Documentos ativos analisados: {relatorio['total_docs_ativos']}")
    print()
    nv = relatorio["vigencia_nao_verificada"]
    print(f"Vigência não verificada: {nv['total']}")
    for item in nv["documentos"][:50]:
        print(f"  - [{item['id']}] {item['titulo']} ({item['categoria']}) "
              f"— {item['embedded_chunks']} chunk(s) vetorizado(s)")
    if nv["total"] > 50:
        print(f"  ... e mais {nv['total'] - 50} (use --formato json para a lista completa)")
    print()
    ct = relatorio["contradicao_vigente_mas_status_nao_atual"]
    print(f"CONTRADIÇÕES (vigente=TRUE com legal_status não-atual): {ct['total']}")
    for item in ct["documentos"]:
        print(f"  - [{item['id']}] {item['titulo']} — status: {item['label']} "
              f"— {item['embedded_chunks']} chunk(s) vetorizado(s)")
    if ct["total"]:
        print()
        print("  ATENÇÃO: os itens acima podem ser citados hoje como direito vigente.")
        print("  Revisar em /governanca-rag e corrigir `vigente`/`legal_status` do doc.")


async def _main(formato: str) -> None:
    async with AsyncSessionLocal() as db:
        relatorio = await _levantar(db)
    if formato == "json":
        print(json.dumps(relatorio, ensure_ascii=False, indent=2))
    else:
        _imprimir_texto(relatorio)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--formato", choices=["texto", "json"], default="texto")
    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(_main(_parse_args().formato))
