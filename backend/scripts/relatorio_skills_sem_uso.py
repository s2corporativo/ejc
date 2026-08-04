#!/usr/bin/env python
# ── scripts/relatorio_skills_sem_uso.py ──────────────────────────────────────
# Relatório de AI Skills sem uso registrado (Bloco 4 do plano de lançamento —
# "AS 163 SKILLS DE IA: mantenha no catálogo apenas as que têm uso registrado
# nos logs. Arquive o resto.").
#
# Antes da migration 130, isso era irrealizável: `ejc_skills` não tinha
# contador de execução, e AILog não distingue qual skill gerou a chamada — não
# havia como inferir uso a partir do log existente. Este relatório só passa a
# fazer sentido depois que o contador (services/ai_skill_service.py::_marcar_uso)
# tiver acumulado dado real em produção — arquivar com zero dado seria
# arquivar às cegas.
#
# Só LISTA — nunca arquiva nada. Arquivar é `PATCH /ai/skills/{id}` com
# `active=False` (rota existente), decisão humana depois de revisar a lista.
#
# Execução (container ejc_backend, na VPS):
#     docker exec -it ejc_backend python -m scripts.relatorio_skills_sem_uso
#     docker exec -it ejc_backend python -m scripts.relatorio_skills_sem_uso --dias 30
from __future__ import annotations

import argparse
import asyncio
import logging

from app.core.database import AsyncSessionLocal
from app.services.ai_skill_service import skills_sem_uso

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ejc.relatorio_skills_sem_uso")


async def executar(dias_minimos: int) -> None:
    async with AsyncSessionLocal() as db:
        sem_uso = await skills_sem_uso(db, dias_minimos=dias_minimos)

    if not sem_uso:
        logger.info(
            "[relatorio] nenhuma skill ativa há mais de %d dia(s) com zero "
            "execuções — nada a revisar agora.",
            dias_minimos,
        )
        return

    logger.info(
        "[relatorio] %d skill(s) ativa(s) há mais de %d dia(s) sem NENHUMA "
        "execução registrada:",
        len(sem_uso), dias_minimos,
    )
    for skill in sem_uso:
        logger.info(
            "  - %s (%s) — area=%s, criada em %s",
            skill.name, skill.display_name, skill.area,
            skill.created_at.date() if skill.created_at else "?",
        )
    logger.info(
        "[relatorio] NADA foi arquivado. Revisar a lista e, para as que o "
        "escritório decidir tirar do catálogo, PATCH /ai/skills/{id} com "
        "active=false."
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Relatório de AI Skills ativas sem uso registrado — só "
                    "lista, nunca arquiva.")
    ap.add_argument(
        "--dias", type=int, default=90,
        help="Idade mínima da skill para entrar no relatório (default: 90).",
    )
    args = ap.parse_args()
    asyncio.run(executar(args.dias))
