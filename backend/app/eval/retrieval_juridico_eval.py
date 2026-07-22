#!/usr/bin/env python3
# ── app/eval/retrieval_juridico_eval.py ───────────────────────────────────────
# Harness de avaliação da QUALIDADE JURÍDICA do retrieval do RAG, contra um
# gold set curado e VERSIONADO (gold_set_retrieval_juridico.jsonl).
#
# Estende — não substitui — o harness de súmulas (scripts/avaliar_rag_precisao.py,
# QUESTOES) e o runner genérico (app/eval/run_eval.py). Reusa dele o loader de
# gold set (_carregar_gold) e a normalização de título (_norm); acrescenta o que
# faltava para um gold set MISTO (súmulas + lei seca):
#
#   • GATE DE PRESENÇA (idempotente, honesto): um item só é PONTUADO quando o
#     documento-alvo (chave_origem_esperada) está de fato semeado e vigente na
#     base. Súmulas são semeadas de forma determinística e offline
#     (ingerir_sumulas_seed — dataset estático em código); a lei seca do
#     planalto.CATALOGO é ingerida por download de planalto.gov.br (bloqueado no
#     CI/dev), logo pode estar AUSENTE. Item ausente vira SKIP — NUNCA um MISS —
#     para o piso de regressão não medir "seed faltando" em vez de "retrieval
#     pior". Nada é fabricado.
#   • MATCH EXATO por título normalizado (não substring), evitando o falso
#     positivo de "Súmula STJ nº 54" casar com "...nº 549".
#
# MÉTRICAS (sobre os itens PONTUADOS):
#   • Hit@k — fração de consultas em que o documento-alvo aparece no top-k.
#   • MRR   — média de 1/posição do alvo (0 quando não aparece no top-k).
#
# USO (dentro do backend, com DATABASE_URL apontando para o banco a avaliar;
# requer Postgres+pgvector com migrations — em CI: RUN_DB_TESTS=1):
#   python -m app.eval.retrieval_juridico_eval
#   python -m app.eval.retrieval_juridico_eval --k 5
#   python -m app.eval.retrieval_juridico_eval --incluir-ausentes   # não pula lei ausente
#   python -m app.eval.retrieval_juridico_eval --min-hit 0.30 --min-mrr 0.12  # gate p/ CI
#   python -m app.eval.retrieval_juridico_eval --out baseline.json
#
# Também roda como regressão automatizada em
# tests/test_rag_avaliacao_precisao_dblevel.py (RUN_DB_TESTS=1).
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from app.eval.run_eval import _carregar_gold, _norm

GOLD_PADRAO = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "gold_set_retrieval_juridico.jsonl")


def carregar(caminho: str = GOLD_PADRAO) -> list[dict]:
    """Carrega o gold set versionado (reusa o loader tolerante do run_eval)."""
    return _carregar_gold(caminho)


async def chaves_presentes(db, chaves: list[str]) -> set[str]:
    """Subconjunto de `chaves` (chave_origem) que existe VIGENTE na base — o
    mesmo recorte que buscar_contexto_rag pode recuperar (deleted_at IS NULL,
    vigente=true). Um round-trip só."""
    from sqlalchemy import text
    chaves = [c for c in chaves if c]
    if not chaves:
        return set()
    rows = await db.execute(text(
        "SELECT DISTINCT chave_origem FROM knowledge_docs "
        "WHERE chave_origem = ANY(:c) AND deleted_at IS NULL AND vigente = true"
    ), {"c": chaves})
    return {r[0] for r in rows}


def _posicao_do_alvo(item: dict, titulos_recuperados: list[str]) -> int | None:
    """Posição (1-based) da 1ª ocorrência do título-alvo no top-k; None se ausente.
    Match por igualdade NORMALIZADA (sem acento/caixa) — exato, não substring."""
    esperados = [_norm(t) for t in (item.get("expected_titulos") or []) if t]
    for i, t in enumerate(titulos_recuperados, start=1):
        if _norm(t) in esperados:
            return i
    return None


async def avaliar(db, k: int = 5, gold: str = GOLD_PADRAO,
                  incluir_ausentes: bool = False) -> dict:
    """Roda o gold set contra ai_service.buscar_contexto_rag e calcula Hit@k/MRR.

    Retorna {k, itens, avaliados, pulados, acertos, hit_rate, mrr, detalhes}.
    Itens cujo alvo não está semeado viram SKIP (a menos de incluir_ausentes).
    """
    from app.services.ai_service import buscar_contexto_rag

    itens = carregar(gold)
    presentes = await chaves_presentes(
        db, [it.get("chave_origem_esperada") for it in itens]
    )

    detalhes: list[dict] = []
    for it in itens:
        chave = it.get("chave_origem_esperada") or ""
        ausente = bool(chave) and chave not in presentes
        if ausente and not incluir_ausentes:
            detalhes.append({
                "id": it.get("id"), "query": it.get("query"),
                "alvo": (it.get("expected_titulos") or [None])[0],
                "chave": chave, "posicao": None, "acertou": False,
                "pontua": False, "status": "SKIP (fonte não semeada)",
            })
            continue
        resultados = await buscar_contexto_rag(
            db, it.get("query") or "", limite=k,
            categorias=None, modo_or=True,
        )
        titulos = [str(r.get("titulo") or "") for r in resultados]
        pos = _posicao_do_alvo(it, titulos)
        detalhes.append({
            "id": it.get("id"), "query": it.get("query"),
            "alvo": (it.get("expected_titulos") or [None])[0],
            "chave": chave, "posicao": pos, "acertou": pos is not None,
            "pontua": True,
            "status": (f"OK (pos {pos})" if pos else "MISS"),
        })

    pontuados = [d for d in detalhes if d["pontua"]]
    total = len(pontuados)
    acertos = sum(1 for d in pontuados if d["acertou"])
    hit_rate = acertos / total if total else 0.0
    mrr = (sum((1 / d["posicao"]) if d["posicao"] else 0.0 for d in pontuados) / total
           if total else 0.0)

    return {
        "k": k, "itens": len(itens), "avaliados": total,
        "pulados": len(itens) - total, "acertos": acertos,
        "hit_rate": hit_rate, "mrr": mrr, "detalhes": detalhes,
    }


def imprimir_relatorio(resultado: dict) -> None:
    k = resultado["k"]
    print(f"\n=== Avaliação jurídica do retrieval RAG — Hit@{k} / MRR ===")
    print(f"Gold set: {resultado['itens']} itens | avaliados: {resultado['avaliados']} "
          f"| pulados (fonte ausente): {resultado['pulados']}")
    print(f"Acertos: {resultado['acertos']}/{resultado['avaliados']} "
          f"| Hit@{k}: {resultado['hit_rate']:.1%} | MRR: {resultado['mrr']:.3f}\n")
    for d in resultado["detalhes"]:
        print(f"  [{d['status']:22}] {d['id']:12} {str(d['query'])[:58]}")
    print()


async def _main(args) -> int:
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        resultado = await avaliar(db, k=args.k, gold=args.gold,
                                  incluir_ausentes=args.incluir_ausentes)
    imprimir_relatorio(resultado)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump({k: v for k, v in resultado.items() if k != "detalhes"} |
                      {"detalhes": resultado["detalhes"]}, fh,
                      ensure_ascii=False, indent=2)
        print(f"resultados → {args.out}")
    rc = 0
    if resultado["avaliados"] == 0:
        print("FALHA: nenhum item pontuado — base sem as fontes do gold set "
              "(semeie súmulas/legislação antes).", file=sys.stderr)
        return 2
    if args.min_hit is not None and resultado["hit_rate"] < args.min_hit:
        print(f"FALHA: Hit@{args.k}={resultado['hit_rate']:.1%} < piso {args.min_hit:.0%}",
              file=sys.stderr)
        rc = 1
    if args.min_mrr is not None and resultado["mrr"] < args.min_mrr:
        print(f"FALHA: MRR={resultado['mrr']:.3f} < piso {args.min_mrr}", file=sys.stderr)
        rc = 1
    return rc


def main() -> None:
    p = argparse.ArgumentParser(
        description="Avalia Hit@k/MRR do retrieval RAG contra o gold set jurídico versionado.")
    p.add_argument("--k", type=int, default=5, help="top-k do retrieval (default 5)")
    p.add_argument("--gold", default=GOLD_PADRAO, help="gold set JSONL (default: o versionado)")
    p.add_argument("--incluir-ausentes", action="store_true",
                   help="pontua também itens cuja fonte não está semeada (viram MISS)")
    p.add_argument("--min-hit", type=float, default=None, help="piso de Hit@k p/ CI (falha abaixo)")
    p.add_argument("--min-mrr", type=float, default=None, help="piso de MRR p/ CI (falha abaixo)")
    p.add_argument("--out", default=None, help="grava o resultado em JSON (baseline p/ diff)")
    args = p.parse_args()
    raise SystemExit(asyncio.run(_main(args)))


if __name__ == "__main__":
    main()
