#!/usr/bin/env python3
# ── app/eval/run_eval.py ──────────────────────────────────────────────────────
# Harness de avaliação do RAG/IA jurídica do EJC (auditoria 2026-07-17, O-4).
#
# PROPÓSITO: dar uma RÉGUA. Sem baseline medido, toda mudança (reranker, embedding,
# prompt, threshold) é aposta. Este runner mede o pipeline REAL contra um gold set
# curado pelo escritório e imprime métricas comparáveis entre execuções.
#
# MÉTRICAS (por caso e agregadas):
#   • RETRIEVAL (determinístico, sempre): hit@k, precision@k, recall@k, MRR —
#     compara os títulos recuperados por buscar_contexto_rag com expected_titulos.
#   • CITAÇÃO (--full): roda a IA de verdade e passa a resposta pelo gate de
#     citações (citation_check) → taxa de citações NÃO confirmadas (alucinação).
#   • GROUNDEDNESS (--judge): LLM-as-judge barato (Haiku) pontua se a resposta se
#     apoia no contexto recuperado (0..1). Valide o juiz contra alguns casos humanos.
#
# USO (dentro do backend, com DATABASE_URL apontando para o banco a avaliar):
#   python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6
#   python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6 --full --judge
#   python -m app.eval.run_eval --gold ... --out resultados.json     # baseline p/ diff
#
# O gold set é o ATIVO mais valioso e só o escritório produz — comece com
# gold_set.example.jsonl e cresça para 50–150 casos reais (pseudonimizados)
# cobrindo as áreas de atuação. Rode em CI para barrar regressão de qualidade.
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import unicodedata
from dataclasses import dataclass, field


def _norm(s: str) -> str:
    """Normaliza para casar títulos: minúsculo, sem acento, espaços colapsados."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


def _casa(esperado: str, recuperado: str) -> bool:
    """Match tolerante: um título casa se um é substring normalizada do outro."""
    e, r = _norm(esperado), _norm(recuperado)
    return bool(e) and bool(r) and (e in r or r in e)


@dataclass
class CasoMetrica:
    id: str
    area: str
    hit: bool = False
    precision: float = 0.0
    recall: float = 0.0
    rr: float = 0.0  # reciprocal rank do 1º acerto (para MRR)
    citacoes_total: int = 0
    citacoes_nao_confirmadas: int = 0
    groundedness: float | None = None
    erro: str | None = None


def _carregar_gold(caminho: str) -> list[dict]:
    casos: list[dict] = []
    with open(caminho, "r", encoding="utf-8") as fh:
        for i, linha in enumerate(fh, 1):
            linha = linha.strip()
            if not linha or linha.startswith("#"):
                continue
            try:
                casos.append(json.loads(linha))
            except json.JSONDecodeError as e:
                print(f"[gold] linha {i} inválida, ignorada: {e}", file=sys.stderr)
    return casos


def _metrica_retrieval(esperados: list[str], titulos_rec: list[str]) -> tuple[bool, float, float, float]:
    """precision@k, recall@k, hit e reciprocal-rank a partir dos títulos recuperados."""
    if not esperados:
        return (False, 0.0, 0.0, 0.0)
    acertos_rank = [
        i for i, t in enumerate(titulos_rec)
        if any(_casa(e, t) for e in esperados)
    ]
    esperados_achados = [
        e for e in esperados if any(_casa(e, t) for t in titulos_rec)
    ]
    hit = bool(acertos_rank)
    precision = (len(acertos_rank) / len(titulos_rec)) if titulos_rec else 0.0
    recall = len(esperados_achados) / len(esperados)
    rr = (1.0 / (acertos_rank[0] + 1)) if acertos_rank else 0.0
    return (hit, round(precision, 4), round(recall, 4), round(rr, 4))


async def _groundedness_judge(query: str, resposta: str, contexto: str) -> float | None:
    """LLM-as-judge barato: 0..1 de quanto a resposta se apoia no contexto."""
    try:
        from app.services import ai_gateway
        r = await ai_gateway.chat(
            [{"role": "system", "content": (
                "Voce e um avaliador rigoroso. Dado CONTEXTO e RESPOSTA, responda APENAS "
                "um numero entre 0 e 1 (2 casas) = fracao da RESPOSTA sustentada pelo "
                "CONTEXTO (groundedness). 1=totalmente apoiada; 0=sem apoio/alucinada.")},
             {"role": "user", "content": f"CONTEXTO:\n{contexto[:6000]}\n\nRESPOSTA:\n{resposta[:3000]}\n\nNota (0..1):"}],
            task_type="resumo", temperature=0.0, max_tokens=8, nivel_inteligencia="padrao",
        )
        import re
        m = re.search(r"[01](?:\.\d+)?", r.texto or "")
        return round(min(1.0, max(0.0, float(m.group(0)))), 3) if m else None
    except Exception as e:
        print(f"[judge] indisponível: {e}", file=sys.stderr)
        return None


async def _avaliar_caso(db, caso: dict, k: int, full: bool, judge: bool) -> CasoMetrica:
    from app.services import ai_service
    cid = str(caso.get("id") or "?")
    m = CasoMetrica(id=cid, area=str(caso.get("area") or ""))
    try:
        chunks = await ai_service.buscar_contexto_rag(
            db, caso.get("query") or "", limite=k,
            categorias=caso.get("categorias") or None,
        )
        titulos = [str(c.get("titulo") or "") for c in chunks]
        m.hit, m.precision, m.recall, m.rr = _metrica_retrieval(
            caso.get("expected_titulos") or [], titulos
        )

        if full:
            # Roda a IA real e passa a resposta pelo gate de citações.
            resp = await ai_service.executar_analise_juridica(  # type: ignore[attr-defined]
                db, caso.get("query") or "", nivel_inteligencia="alto",
            ) if hasattr(ai_service, "executar_analise_juridica") else None
            texto = (resp or {}).get("conteudo") if isinstance(resp, dict) else None
            if texto is None:
                from app.services import ai_gateway
                gw = await ai_gateway.executar_tarefa_ia(
                    "analise_juridica", caso.get("query") or "",
                    contexto_rag=[str(c.get("conteudo") or "") for c in chunks],
                )
                texto = gw.get("conteudo", "")
            try:
                from app.services.citation_check import verificar_citacoes
                cit = await verificar_citacoes(db, texto or "")
                if isinstance(cit, dict):
                    m.citacoes_total = int(cit.get("total") or 0)
                    m.citacoes_nao_confirmadas = int(cit.get("nao_encontradas") or 0)
            except Exception as e:
                print(f"[{cid}] citation_check indisponível: {e}", file=sys.stderr)
            if judge:
                contexto = "\n\n".join(str(c.get("conteudo") or "") for c in chunks)
                m.groundedness = await _groundedness_judge(caso.get("query") or "", texto or "", contexto)
    except Exception as e:
        m.erro = str(e)[:300]
    return m


@dataclass
class Agregado:
    n: int = 0
    hit: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    mrr: float = 0.0
    taxa_alucinacao: float | None = None
    groundedness: float | None = None
    por_caso: list[dict] = field(default_factory=list)


def _agregar(metricas: list[CasoMetrica]) -> Agregado:
    validos = [m for m in metricas if m.erro is None]
    n = len(validos) or 1
    ag = Agregado(n=len(validos))
    ag.hit = round(sum(1 for m in validos if m.hit) / n, 4)
    ag.precision = round(sum(m.precision for m in validos) / n, 4)
    ag.recall = round(sum(m.recall for m in validos) / n, 4)
    ag.mrr = round(sum(m.rr for m in validos) / n, 4)
    tot_cit = sum(m.citacoes_total for m in validos)
    if tot_cit:
        ag.taxa_alucinacao = round(sum(m.citacoes_nao_confirmadas for m in validos) / tot_cit, 4)
    grs = [m.groundedness for m in validos if m.groundedness is not None]
    if grs:
        ag.groundedness = round(sum(grs) / len(grs), 4)
    ag.por_caso = [vars(m) for m in metricas]
    return ag


async def _main(args) -> int:
    from app.core.database import AsyncSessionLocal
    casos = _carregar_gold(args.gold)
    if not casos:
        print(f"Nenhum caso em {args.gold}", file=sys.stderr)
        return 2
    metricas: list[CasoMetrica] = []
    async with AsyncSessionLocal() as db:
        for caso in casos:
            m = await _avaliar_caso(db, caso, args.k, args.full, args.judge)
            flag = "ERRO" if m.erro else ("HIT" if m.hit else "miss")
            print(f"  [{flag:4}] {m.id:12} p@{args.k}={m.precision} r@{args.k}={m.recall} rr={m.rr}"
                  + (f" alucin={m.citacoes_nao_confirmadas}/{m.citacoes_total}" if args.full else "")
                  + (f" ground={m.groundedness}" if m.groundedness is not None else "")
                  + (f"  ({m.erro})" if m.erro else ""))
            metricas.append(m)
    ag = _agregar(metricas)
    print("\n== AGREGADO ==")
    print(f"casos={ag.n}  hit@{args.k}={ag.hit}  precision@{args.k}={ag.precision}  "
          f"recall@{args.k}={ag.recall}  MRR={ag.mrr}")
    if ag.taxa_alucinacao is not None:
        print(f"taxa de citações NÃO confirmadas (alucinação)={ag.taxa_alucinacao}")
    if ag.groundedness is not None:
        print(f"groundedness média (LLM-judge)={ag.groundedness}")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(vars(ag), fh, ensure_ascii=False, indent=2)
        print(f"\nresultados → {args.out}")
    # Gate de regressão opcional (para CI): falha se recall cair abaixo do piso.
    if args.min_recall is not None and ag.recall < args.min_recall:
        print(f"\nFALHA: recall@{args.k}={ag.recall} < piso {args.min_recall}", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="Avaliação do RAG/IA jurídica do EJC (O-4).")
    p.add_argument("--gold", default="app/eval/gold_set.example.jsonl", help="gold set JSONL")
    p.add_argument("--k", type=int, default=6, help="top-k do retrieval")
    p.add_argument("--full", action="store_true", help="roda a IA e mede citações (mais lento/caro)")
    p.add_argument("--judge", action="store_true", help="groundedness via LLM-judge (requer --full)")
    p.add_argument("--out", default=None, help="grava métricas agregadas em JSON (baseline p/ diff)")
    p.add_argument("--min-recall", type=float, default=None, help="piso de recall@k p/ CI (falha abaixo)")
    args = p.parse_args()
    raise SystemExit(asyncio.run(_main(args)))


if __name__ == "__main__":
    main()
