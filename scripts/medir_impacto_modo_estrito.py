#!/usr/bin/env python3
"""Mede o que ligar CITACOES_MODO_ESTRITO bloquearia — antes de ligar.

Enviado por STDIN ao Python do container:
    docker exec -i ejc_backend python - < scripts/medir_impacto_modo_estrito.py

O modo estrito transforma "citou súmula/artigo que a base curada não confirma"
(e, desde a Fase 4, "confirma apenas em versão SUPERADA") de aviso em BLOQUEIO.
A dúvida operacional não é se a regra é correta — é se a base curada já está
abrangente o bastante para que o bloqueio recaia sobre invenção da IA e não
sobre norma real ainda não ingerida. Ligar às cegas produz falso-positivo em
peça legítima, e o custo disso é advogado desconfiando do gate.

Este script responde com número: pega as respostas de IA já geradas (ai_logs),
reverifica as citações e compara os bloqueantes com o modo estrito DESLIGADO e
LIGADO. O delta é exatamente o que passaria a barrar.

Nada é gravado — somente leitura. Nenhum trecho de peça é impresso: só a
citação em si (referência normativa, não conteúdo do cliente) e contagens.

Variáveis:
    MODO_ESTRITO_DIAS      Janela em dias (default 90).
    MODO_ESTRITO_MAX_LOGS  Teto de respostas analisadas (default 300) — cada
                           uma custa lookups no banco.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import Counter


async def main() -> int:
    from sqlalchemy import text

    from app.core.database import AsyncSessionLocal
    from app.services.citation_gate import avaliar_bloqueantes
    from app.services.verificador_jurisprudencia import verificar_jurisprudencia

    dias = int(os.getenv("MODO_ESTRITO_DIAS", "90"))
    max_logs = int(os.getenv("MODO_ESTRITO_MAX_LOGS", "300"))

    resultado: dict[str, object] = {"janela_dias": dias, "teto_logs": max_logs}
    status_total: Counter[str] = Counter()
    novos_bloqueios: list[dict[str, str]] = []
    respostas_afetadas = 0
    analisadas = 0

    async with AsyncSessionLocal() as db:
        linhas = (
            await db.execute(
                text(
                    "SELECT id, resposta FROM ai_logs "
                    "WHERE resposta IS NOT NULL AND length(resposta) > 200 "
                    "AND created_at > NOW() - make_interval(days => :dias) "
                    "ORDER BY created_at DESC LIMIT :limite"
                ),
                {"dias": dias, "limite": max_logs},
            )
        ).all()

        for log_id, resposta in linhas:
            try:
                rel = await verificar_jurisprudencia(db, resposta)
            except Exception as exc:  # uma resposta ruim não pode matar a medição
                resultado.setdefault("erros", []).append(  # type: ignore[union-attr]
                    f"{log_id}: {type(exc).__name__}"
                )
                continue
            analisadas += 1
            for c in rel.get("citacoes") or []:
                status_total[str(c.get("status"))] += 1

            atuais = {b["citacao"] for b in avaliar_bloqueantes(rel, modo_estrito=False)}
            estritos = avaliar_bloqueantes(rel, modo_estrito=True)
            novos = [b for b in estritos if b["citacao"] not in atuais]
            if novos:
                respostas_afetadas += 1
                for b in novos:
                    novos_bloqueios.append(
                        {"citacao": b["citacao"], "tipo": b["tipo"], "status": b["status"]}
                    )

    proporcao = (respostas_afetadas / analisadas) if analisadas else 0.0
    # Contagem por citação distinta: 40 ocorrências do mesmo artigo ausente são
    # UM buraco na base curada, não 40 problemas.
    distintas = Counter(b["citacao"] for b in novos_bloqueios)

    resultado.update(
        {
            "respostas_analisadas": analisadas,
            "respostas_que_passariam_a_bloquear": respostas_afetadas,
            "proporcao_afetada": round(proporcao, 4),
            "distribuicao_status_citacoes": dict(status_total),
            "citacoes_distintas_que_bloqueariam": distintas.most_common(50),
            "total_novos_bloqueios": len(novos_bloqueios),
        }
    )
    # Critério explícito para não deixar a leitura do número virar opinião.
    if not analisadas:
        resultado["recomendacao"] = (
            "sem dados na janela — amplie MODO_ESTRITO_DIAS antes de decidir"
        )
    elif proporcao <= 0.02:
        resultado["recomendacao"] = (
            "LIGAR: menos de 2% das respostas seriam afetadas; a base curada "
            "cobre o que a IA cita"
        )
    else:
        resultado["recomendacao"] = (
            "MANTER DESLIGADO e ingerir primeiro as citações listadas em "
            "citacoes_distintas_que_bloqueariam — elas são candidatas a "
            "lacuna da base, não a alucinação"
        )

    print(json.dumps(resultado, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
