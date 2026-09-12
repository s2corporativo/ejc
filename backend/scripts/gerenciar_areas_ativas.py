#!/usr/bin/env python
# ── scripts/gerenciar_areas_ativas.py ────────────────────────────────────────
# Simplificação de menu (parecer arquitetural — "26 áreas → efetivamente
# praticadas"): a tabela canônica `areas` (migration 083, coluna `ativo`) já é
# a fonte real do dropdown do frontend (GET /areas — WHERE ativo = true,
# `app/routers/areas.py`). Desativar uma área aqui tira-a do menu SEM alterar
# o enum `CaseArea` nem nenhum caso já cadastrado — reversível a qualquer
# momento (basta reativar).
#
# POR QUE ESTE SCRIPT, E NÃO UMA MIGRATION COM A LISTA JÁ DECIDIDA: a auditoria
# de julho/2026 mediu "casos reais em consumidor (7) e civil (2)" — mas isso
# envelheceu, e adivinhar hoje quais áreas o escritório pratica arriscaria
# esconder do advogado a área que ele realmente usa agora. Este script mostra
# a CONTAGEM REAL de casos por área NO MOMENTO DA EXECUÇÃO e deixa a decisão
# de quais manter para quem tem o dado atual — nunca decide sozinho.
#
# Garantias de segurança:
#   - Sem argumento: só LISTA (slug, nome, ativo, nº de casos vivos).
#   - --desativar/--ativar: SOMENTE UPDATE de `ativo` — nunca DELETE, nunca
#     toca em `cases` nem no enum.
#   - RECUSA desativar uma área com casos vivos (deleted_at IS NULL) sem
#     --forcar-com-casos — casos existentes continuam acessíveis (a área só
#     some do dropdown de NOVOS casos), mas a recusa evita o "cadê minha área"
#     por engano.
#
# Execução (container ejc_backend, conecta pelo DATABASE_URL do ambiente):
#     docker exec -it ejc_backend python -m scripts.gerenciar_areas_ativas
#     docker exec -it ejc_backend python -m scripts.gerenciar_areas_ativas --desativar eleitoral,agrario,agronegocio
#     docker exec -it ejc_backend python -m scripts.gerenciar_areas_ativas --ativar eleitoral
from __future__ import annotations

import argparse
import asyncio
import logging

from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ejc.gerenciar_areas")


async def _listar(db) -> list[dict]:
    rows = (
        await db.execute(
            text(
                "SELECT a.slug, a.nome, a.ativo, a.ordem, "
                "       COUNT(c.id) FILTER (WHERE c.deleted_at IS NULL) AS casos_vivos "
                "FROM areas a "
                "LEFT JOIN cases c ON c.area::text = a.slug "
                "GROUP BY a.slug, a.nome, a.ativo, a.ordem "
                "ORDER BY casos_vivos DESC, a.ordem"
            )
        )
    ).mappings().all()
    return [dict(r) for r in rows]


def _imprimir(linhas: list[dict]) -> None:
    print(f"{'slug':<16} {'ativo':<7} {'casos vivos':<12} nome")
    print("-" * 70)
    for r in linhas:
        print(f"{r['slug']:<16} {str(r['ativo']):<7} {r['casos_vivos']:<12} {r['nome']}")
    total_ativas = sum(1 for r in linhas if r["ativo"])
    print(f"\n{total_ativas} de {len(linhas)} áreas ativas no menu hoje.")


async def _alterar(db, slugs: list[str], ativo: bool, forcar_com_casos: bool) -> None:
    for slug in slugs:
        row = (
            await db.execute(
                text(
                    "SELECT a.ativo, COUNT(c.id) FILTER (WHERE c.deleted_at IS NULL) AS casos_vivos "
                    "FROM areas a LEFT JOIN cases c ON c.area::text = a.slug "
                    "WHERE a.slug = :slug GROUP BY a.ativo"
                ),
                {"slug": slug},
            )
        ).first()
        if row is None:
            logger.warning("slug '%s' não existe na tabela areas — ignorado", slug)
            continue
        ativo_atual, casos_vivos = row
        if not ativo and casos_vivos > 0 and not forcar_com_casos:
            logger.warning(
                "'%s' tem %s caso(s) vivo(s) — recusado sem --forcar-com-casos "
                "(casos existentes continuam acessíveis; só o dropdown de NOVOS casos seria afetado)",
                slug, casos_vivos,
            )
            continue
        await db.execute(
            text("UPDATE areas SET ativo = :ativo WHERE slug = :slug"),
            {"ativo": ativo, "slug": slug},
        )
        logger.info("'%s': ativo %s → %s", slug, ativo_atual, ativo)
    await db.commit()


async def _main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--desativar", help="slugs separados por vírgula")
    ap.add_argument("--ativar", help="slugs separados por vírgula")
    ap.add_argument(
        "--forcar-com-casos", action="store_true",
        help="permite desativar área com casos vivos (eles continuam acessíveis; só some do menu de novos casos)",
    )
    args = ap.parse_args()

    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        if args.desativar:
            await _alterar(db, [s.strip() for s in args.desativar.split(",") if s.strip()], False, args.forcar_com_casos)
        if args.ativar:
            await _alterar(db, [s.strip() for s in args.ativar.split(",") if s.strip()], True, True)
        _imprimir(await _listar(db))


if __name__ == "__main__":
    asyncio.run(_main())
