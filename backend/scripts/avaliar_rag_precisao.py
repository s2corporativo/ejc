#!/usr/bin/env python
# ── scripts/avaliar_rag_precisao.py ──────────────────────────────────────────
# Auditoria RAG — harness de avaliação de qualidade da recuperação.
#
# A auditoria original apontou: "Não encontrei precisão@k, recall, cobertura
# ou freshness SLO" — não havia como medir se uma mudança no RAG (novo filtro,
# novo chunker, novo modelo de embedding) melhora ou piora a recuperação.
#
# Este harness usa como gabarito as 27 súmulas reconstruídas e individualmente
# reconferidas contra fonte oficial (sumulas_ingestion.py) — cada pergunta
# mapeia para o título EXATO da súmula que deveria aparecer na resposta.
# Métricas:
#   • Hit@k   — fração de perguntas em que a fonte esperada aparece entre os
#               k primeiros resultados.
#   • MRR     — Mean Reciprocal Rank: média de 1/posição da fonte esperada
#               (0 se não aparece nos k primeiros). Penaliza rank pior mesmo
#               quando o documento certo aparece (ex.: 5º lugar pesa menos
#               que 1º).
#
# Execução (container ejc_backend, na VPS, ou local com Postgres+pgvector):
#     docker exec -it ejc_backend python -m scripts.avaliar_rag_precisao
#     docker exec -it ejc_backend python -m scripts.avaliar_rag_precisao --k 3
#
# Também usado como regressão automatizada em
# tests/test_rag_avaliacao_precisao_dblevel.py (RUN_DB_TESTS=1).
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field


@dataclass
class Questao:
    pergunta: str
    titulo_esperado: str   # título EXATO gravado por sumulas_ingestion.py
    categorias: list[str] | None = field(default=None)


# Perguntas jurídicas naturais → súmula esperada (gabarito verificado contra
# fonte oficial em sumulas_ingestion.DATA_CONFERENCIA). Cobre trabalhista,
# consumidor, bancário, civil, ambiental, administrativo e tributário —
# amostra das categorias reais do acervo, não exaustiva.
QUESTOES: list[Questao] = [
    Questao("O Código de Defesa do Consumidor se aplica às instituições financeiras?",
           "Súmula STJ nº 297"),
    Questao("A Caixa Econômica Federal responde como sucessora do Banco Nacional "
           "da Habitação nas ações do Sistema Financeiro da Habitação?",
           "Súmula STJ nº 327"),
    Questao("A decadência do art. 26 do CDC se aplica ao pedido de prestação de "
           "contas sobre tarifas e encargos bancários?",
           "Súmula STJ nº 477"),
    Questao("O trabalho insalubre prestado de forma intermitente afasta o direito "
           "ao adicional de insalubridade?",
           "Súmula TST nº 47"),
    Questao("Como deve ser ajustada a compensação de jornada de trabalho — "
           "acordo individual ou só coletivo?",
           "Súmula TST nº 85"),
    Questao("O adicional de periculosidade pago em caráter permanente integra "
           "o cálculo de horas extras e indenização?",
           "Súmula TST nº 132"),
    Questao("As anotações feitas pelo empregador na carteira de trabalho geram "
           "presunção absoluta ou relativa?",
           "Súmula TST nº 12"),
    Questao("A teoria do fato consumado pode ser aplicada para regularizar "
           "situação de dano ambiental?",
           "Súmula STJ nº 613"),
    Questao("Em ação de degradação ambiental, cabe inversão do ônus da prova?",
           "Súmula STJ nº 618"),
    Questao("As obrigações ambientais de recuperação de área degradada podem "
           "ser cobradas do proprietário atual mesmo que ele não tenha causado "
           "o dano?",
           "Súmula STJ nº 623"),
    Questao("A partir de quando fluem os juros moratórios em caso de "
           "responsabilidade extracontratual por dano?",
           "Súmula STJ nº 54"),
    Questao("É abusiva a cláusula de plano de saúde que limita o tempo de "
           "internação hospitalar?",
           "Súmula STJ nº 302"),
    Questao("O juiz pode reconhecer de ofício a abusividade de cláusula em "
           "contrato bancário?",
           "Súmula STJ nº 381"),
    Questao("É necessário aviso de recebimento (AR) na carta que comunica o "
           "consumidor sobre a negativação do seu nome?",
           "Súmula STJ nº 404"),
    Questao("É válida a penhora do bem de família do fiador em contrato de "
           "locação?",
           "Súmula STJ nº 549"),
    Questao("O Código de Defesa do Consumidor se aplica às entidades abertas "
           "de previdência complementar?",
           "Súmula STJ nº 563"),
    Questao("A contratação de servidor público sem concurso após a "
           "Constituição de 1988 gera direito a quê?",
           "Súmula TST nº 363"),
    Questao("A dispensa de empregado portador do vírus HIV é presumida "
           "discriminatória?",
           "Súmula TST nº 443"),
    Questao("O acordo de adesão da Lei Complementar 110/2001 sobre expurgos "
           "do FGTS pode ser desconsiderado pelo juiz sem análise do caso "
           "concreto?",
           "Súmula Vinculante STF nº 1"),
    Questao("Incidem juros de mora sobre precatório pago dentro do prazo "
           "constitucional?",
           "Súmula Vinculante STF nº 17"),
    Questao("O Poder Judiciário pode aumentar vencimentos de servidores "
           "públicos com base no princípio da isonomia?",
           "Súmula Vinculante STF nº 37"),
]


async def avaliar(k: int = 5) -> dict:
    """Roda todas as QUESTOES contra buscar_contexto_rag e calcula Hit@k/MRR.

    Retorna {"k", "hit_rate", "mrr", "detalhes": [...]} — detalhes traz, por
    pergunta, se acertou e em que posição (None = não encontrada nos top-k).
    """
    from app.services.ai_service import buscar_contexto_rag
    from app.core.database import AsyncSessionLocal

    detalhes = []
    async with AsyncSessionLocal() as db:
        for q in QUESTOES:
            resultados = await buscar_contexto_rag(
                db, q.pergunta, limite=k, categorias=q.categorias, modo_or=True,
            )
            posicao = None
            for i, r in enumerate(resultados, start=1):
                if r.get("titulo") == q.titulo_esperado:
                    posicao = i
                    break
            detalhes.append({
                "pergunta": q.pergunta,
                "titulo_esperado": q.titulo_esperado,
                "posicao": posicao,
                "acertou": posicao is not None,
            })

    total = len(detalhes)
    acertos = sum(1 for d in detalhes if d["acertou"])
    hit_rate = acertos / total if total else 0.0
    mrr = sum((1 / d["posicao"]) if d["posicao"] else 0.0 for d in detalhes) / total if total else 0.0

    return {"k": k, "total": total, "acertos": acertos,
           "hit_rate": hit_rate, "mrr": mrr, "detalhes": detalhes}


def _imprimir_relatorio(resultado: dict) -> None:
    print(f"\n=== Avaliação RAG — Hit@{resultado['k']} / MRR ===")
    print(f"Perguntas: {resultado['total']} | Acertos: {resultado['acertos']} "
         f"| Hit@{resultado['k']}: {resultado['hit_rate']:.1%} | MRR: {resultado['mrr']:.3f}\n")
    for d in resultado["detalhes"]:
        marca = f"OK  (pos {d['posicao']})" if d["acertou"] else "MISS"
        print(f"  [{marca:14}] {d['pergunta'][:70]}")
    print()


async def _main(k: int) -> None:
    resultado = await avaliar(k=k)
    _imprimir_relatorio(resultado)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Avalia Hit@k/MRR da recuperação RAG "
                                            "contra o gabarito de súmulas.")
    ap.add_argument("--k", type=int, default=5)
    args = ap.parse_args()
    asyncio.run(_main(args.k))
