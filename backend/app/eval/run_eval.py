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
import glob
import json
import os
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
    # AI-087 (auditoria máxima 2026-07-26): a média GLOBAL esconde a área ruim —
    # uma média boa puxada por cível não prova nada sobre penal ou trabalhista.
    # Métricas segmentadas pela `area` do gold set, com gate próprio no CI.
    por_area: dict[str, dict] = field(default_factory=dict)
    por_caso: list[dict] = field(default_factory=list)


def _metricas_de(validos: list[CasoMetrica]) -> dict:
    """Bloco de métricas de um conjunto de casos (global ou de uma área)."""
    n = len(validos) or 1
    bloco = {
        "n": len(validos),
        "hit": round(sum(1 for m in validos if m.hit) / n, 4),
        "precision": round(sum(m.precision for m in validos) / n, 4),
        "recall": round(sum(m.recall for m in validos) / n, 4),
        "mrr": round(sum(m.rr for m in validos) / n, 4),
    }
    tot_cit = sum(m.citacoes_total for m in validos)
    if tot_cit:
        bloco["taxa_alucinacao"] = round(
            sum(m.citacoes_nao_confirmadas for m in validos) / tot_cit, 4)
    grs = [m.groundedness for m in validos if m.groundedness is not None]
    if grs:
        bloco["groundedness"] = round(sum(grs) / len(grs), 4)
    return bloco


def _agregar(metricas: list[CasoMetrica]) -> Agregado:
    validos = [m for m in metricas if m.erro is None]
    glob_ = _metricas_de(validos)
    ag = Agregado(
        n=glob_["n"], hit=glob_["hit"], precision=glob_["precision"],
        recall=glob_["recall"], mrr=glob_["mrr"],
        taxa_alucinacao=glob_.get("taxa_alucinacao"),
        groundedness=glob_.get("groundedness"),
    )
    # AI-087: segmentação por área (caso sem `area` cai em "(sem_area)" — e
    # aparece no relatório, em vez de sumir na média).
    areas: dict[str, list[CasoMetrica]] = {}
    for m in validos:
        areas.setdefault((m.area or "").strip().lower() or "(sem_area)", []).append(m)
    ag.por_area = {a: _metricas_de(ms) for a, ms in sorted(areas.items())}
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

    # AI-087: relatório POR ÁREA — a régua que importa para dizer se a IA é
    # confiável em penal, trabalhista, ambiental… uma a uma.
    if ag.por_area:
        print("\n== POR ÁREA ==")
        for area, b in ag.por_area.items():
            print(f"  {area:22} n={b['n']:3}  hit@{args.k}={b['hit']:<6} "
                  f"recall@{args.k}={b['recall']:<6} MRR={b['mrr']}")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(vars(ag), fh, ensure_ascii=False, indent=2)
        print(f"\nresultados → {args.out}")

    falhas: list[str] = []
    # Gate global (legado): falha se o recall MÉDIO cair abaixo do piso.
    if args.min_recall is not None and ag.recall < args.min_recall:
        falhas.append(f"recall@{args.k} global={ag.recall} < piso {args.min_recall}")

    # AI-087 — gate POR ÁREA: nenhuma área crítica pode ficar abaixo do piso, e
    # área crítica AUSENTE do gold set é falha (cobertura zero não é aprovação).
    obrigatorias = [a.strip().lower() for a in (args.areas_obrigatorias or "").split(",") if a.strip()]
    for area in obrigatorias:
        if area not in ag.por_area:
            falhas.append(f"área crítica SEM casos no gold set: {area}")
    # Áreas cujos casos ERRARAM somem de `por_area` (o agregado só conta casos
    # válidos). Sem incluí-las no alvo, uma área com 100% de erro — banco fora,
    # retrieval quebrado — sairia do gate e o resultado ficaria verde (review do
    # Codex no PR #496). Elas entram no alvo e falham explicitamente.
    areas_com_erro: dict[str, int] = {}
    for m in metricas:
        if m.erro is not None:
            chave = (m.area or "").strip().lower() or "(sem_area)"
            areas_com_erro[chave] = areas_com_erro.get(chave, 0) + 1

    if args.min_recall_area is not None:
        alvo = set(obrigatorias) or (set(ag.por_area) | set(areas_com_erro))
        for area in sorted(alvo):
            bloco = ag.por_area.get(area)
            if bloco is None:
                falhas.append(
                    f"área '{area}': nenhuma avaliação válida "
                    f"({areas_com_erro.get(area, 0)} caso(s) com erro) — "
                    "impossível aferir o piso")
            elif bloco["recall"] < args.min_recall_area:
                falhas.append(
                    f"área '{area}': recall@{args.k}={bloco['recall']} "
                    f"< piso {args.min_recall_area} (n={bloco['n']})")
            elif areas_com_erro.get(area):
                falhas.append(
                    f"área '{area}': {areas_com_erro[area]} caso(s) com erro na "
                    "avaliação — resultado parcial não aprova o piso")

    if falhas:
        print("\nFALHA no gate de qualidade jurídica:", file=sys.stderr)
        for f in falhas:
            print(f"  - {f}", file=sys.stderr)
        return 1
    return 0


# ── Modo SMOKE (CI, offline) ─────────────────────────────────────────────────
# Valida o FORMATO de todos os gold sets *.jsonl do pacote SEM banco e SEM
# chamada de LLM (as métricas determinísticas offline rodam à parte em
# `python -m app.eval.agent_trajectory`). Objetivo: o CI pega gold set quebrado
# (JSON inválido, campo obrigatório faltando, exemplo "fictício" com cara de
# jurisprudência real) antes de o escritório investir na curadoria.

def _erros_pii_caso(caso: dict) -> list[str]:
    """Detector de PII para gold sets REAIS (não-example): reusa os padrões
    estruturais do sanitizer da casa. Import tardio para o smoke continuar
    utilizável mesmo fora do pacote app completo."""
    try:
        from app.services.sanitizer import validar_sem_pii
    except Exception:
        return []  # sanitizer indisponível neste ambiente — não bloqueia o smoke
    erros: list[str] = []
    for campo in ("fatos", "pedidos"):
        texto = str(caso.get(campo) or "")
        if not texto.strip():
            continue
        tipos = validar_sem_pii(texto)
        if tipos:
            erros.append(
                f"PII detectada em '{campo}' ({', '.join(sorted(set(map(str, tipos))))}) "
                "— gold set real deve ser PSEUDONIMIZADO antes do commit"
            )
    return erros


def _validar_caso_smoke(caso: dict, arquivo: str) -> list[str]:
    """Erros de formato de UM caso, segundo a shape detectada pelos campos."""
    erros: list[str] = []

    def _req_str(campo: str):
        if not str(caso.get(campo) or "").strip():
            erros.append(f"campo obrigatório vazio/ausente: {campo}")

    def _req_lista(campo: str):
        v = caso.get(campo)
        if not isinstance(v, list) or not v or not all(str(x).strip() for x in v):
            erros.append(f"campo obrigatório deve ser lista não vazia: {campo}")

    if "query" in caso:            # gold set de RAG (gold_set*.jsonl)
        _req_str("id")
        _req_str("query")
        _req_lista("expected_titulos")
    elif "fatos" in caso:          # gold set de PEÇAS (gold_set_pecas*.jsonl)
        _req_str("id")
        _req_str("area")
        _req_str("fatos")
        _req_str("tipo_peca_esperado")
        _req_lista("teses_esperadas")
        _req_lista("criterios")
        if not isinstance(caso.get("ficticio"), bool):
            erros.append("campo obrigatório deve ser bool: ficticio")
        if ".example." in os.path.basename(arquivo):
            # Guarda-corpo anti-invenção: exemplo embarcado é SEMPRE fictício e
            # sua "jurisprudência" só pode ser placeholder explícito.
            if caso.get("ficticio") is not True:
                erros.append("exemplo embarcado deve ter ficticio=true")
            for j in caso.get("jurisprudencia_esperada") or []:
                if "FICTICIA" not in str(j).upper():
                    erros.append(
                        f"jurisprudência de exemplo sem marcador FICTICIA: {j!r}"
                    )
        else:
            # Gold set REAL: LGPD — os casos devem estar PSEUDONIMIZADOS.
            # Roda o detector estrutural de PII da casa sobre os campos de
            # texto e FALHA se encontrar CPF/CNPJ/e-mail/telefone etc.
            erros.extend(_erros_pii_caso(caso))
    elif "intencao" in caso:       # cenários de trajetória (agent_scenarios.jsonl)
        _req_str("intencao")       # validação profunda: app.eval.agent_trajectory
        _req_str("mensagem")
    else:
        erros.append("formato desconhecido (esperado campo query, fatos ou intencao)")
    return erros


def _smoke(areas_obrigatorias: str | None = None, min_casos_area: int = 0) -> int:
    base = os.path.dirname(os.path.abspath(__file__))
    arquivos = sorted(glob.glob(os.path.join(base, "*.jsonl")))
    if not arquivos:
        print("SMOKE: nenhum gold set *.jsonl encontrado", file=sys.stderr)
        return 2
    falhas = 0
    # AI-087: cobertura por área, contada só sobre gold sets REAIS (os
    # *.example.* são amostras de formato — não provam cobertura de nada).
    cobertura: dict[str, int] = {}
    for arq in arquivos:
        casos = _carregar_gold(arq)
        eh_exemplo = ".example." in os.path.basename(arq)
        ids_vistos: set[str] = set()
        erros_arq: list[str] = []
        for i, caso in enumerate(casos, 1):
            for e in _validar_caso_smoke(caso, arq):
                erros_arq.append(f"caso {i} ({caso.get('id', '?')}): {e}")
            cid = str(caso.get("id") or "").strip()
            if cid:
                if cid in ids_vistos:
                    erros_arq.append(f"caso {i}: id duplicado: {cid}")
                ids_vistos.add(cid)
            # Cobertura conta só GOLD SET (RAG: `query`; peças: `fatos`) —
            # cenários de trajetória do agente (`intencao`) medem outra coisa.
            if not eh_exemplo and ("query" in caso or "fatos" in caso):
                area = str(caso.get("area") or "").strip().lower() or "(sem_area)"
                cobertura[area] = cobertura.get(area, 0) + 1
        status = "OK " if not erros_arq else "ERRO"
        print(f"[{status}] {os.path.basename(arq)}: {len(casos)} caso(s)"
              + ("  (exemplo — não conta como cobertura)" if eh_exemplo else ""))
        for e in erros_arq:
            print(f"       - {e}")
        falhas += len(erros_arq)

    print("\n== COBERTURA POR ÁREA (gold sets reais) ==")
    if cobertura:
        for area, n in sorted(cobertura.items()):
            print(f"  {area:22} {n} caso(s)")
    else:
        print("  (nenhum gold set real — só exemplos de formato)")

    # Gate de cobertura: área crítica exigida precisa existir com um mínimo de
    # casos. Sem isso, "smoke verde" seguiria significando apenas JSON válido.
    obrigatorias = [a.strip().lower() for a in (areas_obrigatorias or "").split(",") if a.strip()]
    for area in obrigatorias:
        n = cobertura.get(area, 0)
        if n < max(1, min_casos_area):
            print(f"       - cobertura insuficiente na área crítica '{area}': "
                  f"{n} caso(s) (mínimo {max(1, min_casos_area)})")
            falhas += 1

    if falhas:
        print(f"\nSMOKE FALHOU: {falhas} problema(s).", file=sys.stderr)
        return 1
    print("\nSMOKE OK: gold sets com formato válido e cobertura exigida atendida.")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="Avaliação do RAG/IA jurídica do EJC (O-4).")
    p.add_argument("--gold", default="app/eval/gold_set.example.jsonl", help="gold set JSONL")
    p.add_argument("--k", type=int, default=6, help="top-k do retrieval")
    p.add_argument("--full", action="store_true", help="roda a IA e mede citações (mais lento/caro)")
    p.add_argument("--judge", action="store_true", help="groundedness via LLM-judge (requer --full)")
    p.add_argument("--out", default=None, help="grava métricas agregadas em JSON (baseline p/ diff)")
    p.add_argument("--min-recall", type=float, default=None, help="piso de recall@k GLOBAL p/ CI (falha abaixo)")
    # AI-087 — gate por área (a média global esconde a área ruim).
    p.add_argument("--min-recall-area", type=float, default=None,
                   help="piso de recall@k aplicado a CADA área (falha se qualquer uma cair abaixo)")
    p.add_argument("--areas-obrigatorias", default=None,
                   help="áreas críticas separadas por vírgula (ex.: penal,trabalhista,consumidor). "
                        "Área ausente do gold set é FALHA — cobertura zero não é aprovação.")
    p.add_argument("--smoke", action="store_true",
                   help="só valida o FORMATO dos gold sets *.jsonl (offline: sem banco/LLM; p/ CI)")
    p.add_argument("--min-casos-area", type=int, default=0,
                   help="no --smoke: mínimo de casos por área crítica (usa --areas-obrigatorias)")
    args = p.parse_args()
    if args.smoke:
        raise SystemExit(_smoke(args.areas_obrigatorias, args.min_casos_area))
    raise SystemExit(asyncio.run(_main(args)))


if __name__ == "__main__":
    main()
