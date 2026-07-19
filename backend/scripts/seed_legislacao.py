"""scripts/seed_legislacao.py — CLI de seed da LEGISLAÇÃO (lei seca) do Planalto.

Wrapper FINO sobre o ingestor unificado `app.services.ingestors.planalto`
(escritor único do corpus categoria='legislacao', chaves `planalto:<slug>`) —
toda a lógica de download/parse/chunk-por-artigo/upsert vive lá; este script
só adiciona a interface de linha de comando e o relatório de execução:

  • MESMAS chaves do job semanal do scheduler (`planalto:<slug>`): rodar o
    seed e o job em qualquer ordem NUNCA duplica documentos (upsert por
    chave_origem, hash sobre o conteúdo, versionamento migration 068);
  • doc vigente gravado com chunking antigo (extra sem divisao='por_artigo')
    é re-chunkado UMA vez em nova versão (ver planalto._rechunk_pendente);
  • falha de uma lei NÃO aborta as demais (relatório final; exit code 1 se
    alguma falhou).

Uso (WORKDIR backend/):
    python -m scripts.seed_legislacao [--apenas cdc,lgpd] [--dry-run]
                                      [--com-embeddings] [--cache-dir DIR]

  --apenas          ingere só os slugs listados (vírgula; case-insensitive)
  --dry-run         baixa e parseia, mostra artigos/chunks, NÃO grava no banco
  --com-embeddings  vetoriza inline (default: adia — o auto-reembed do
                    scheduler indexa os docs 'pendente' depois)
  --cache-dir       diretório com <slug>.html — usa o arquivo local em vez de
                    baixar (reexecução offline / testes / rede bloqueada)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# backend/ no sys.path quando rodado como script avulso.
_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from app.services.ingestors import planalto as pl  # noqa: E402

logger = logging.getLogger("ejc.seed_legislacao")

FONTE_SLUG = "legislacao_planalto"
DESCRICAO = "Legislação federal (lei seca) — texto compilado do Planalto, dividido por artigo"

# Reexports p/ conveniência (testes e chamadores legados importam daqui).
CATALOGO = pl.CATALOGO
CATEGORIA = pl.CATEGORIA
PREFIXO_CHAVE = pl.PREFIXO_CHAVE


def _filtrar_catalogo(apenas: str | None) -> list[dict]:
    if not apenas:
        return pl.CATALOGO
    slugs = {s.strip().lower() for s in apenas.split(",") if s.strip()}
    sel = [l for l in pl.CATALOGO if l["slug"] in slugs]
    desconhecidos = slugs - {l["slug"] for l in sel}
    if desconhecidos:
        raise SystemExit(f"[seed-legislacao] slugs desconhecidos: {sorted(desconhecidos)} "
                         f"(válidos: {[l['slug'] for l in pl.CATALOGO]})")
    return sel


async def executar_seed_legislacao(
    db, *, apenas: str | None = None, embutir_vetores: bool = False,
    cache_dir: Path | None = None,
) -> dict:
    """Ingere o catálogo (idempotente). Falha de uma lei não aborta as demais."""
    from app.services.ingestion_service import marcar_execucao, registrar_fonte

    leis = _filtrar_catalogo(apenas)
    await registrar_fonte(db, FONTE_SLUG, DESCRICAO, categoria_rag=pl.CATEGORIA)
    await db.commit()

    sucessos: dict[str, dict] = {}
    falhas: dict[str, str] = {}
    for lei in leis:
        try:
            r = await pl.ingerir_diploma(db, lei, embutir_vetores=embutir_vetores,
                                         cache_dir=cache_dir)
            await db.commit()   # commit por lei — uma lei grande não trava as demais
            sucessos[lei["slug"]] = r
            print(f"[seed-legislacao] {lei['slug']:6s} {r['resultado']:10s} "
                  f"artigos={r['artigos']:5d} chunks={r['chunks']:5d} chars={r['chars']}")
        except Exception as e:
            await db.rollback()
            falhas[lei["slug"]] = f"{type(e).__name__}: {e}"
            print(f"[seed-legislacao] {lei['slug']:6s} FALHA — {falhas[lei['slug']]}",
                  file=sys.stderr)

    novos = sum(1 for r in sucessos.values() if r["resultado"] in ("novo", "atualizado"))
    status = "sucesso" if not falhas else ("parcial" if sucessos else "erro")
    await marcar_execucao(
        db, FONTE_SLUG, status=status, novos=novos, total=len(leis),
        erro="; ".join(f"{s}: {e}" for s, e in falhas.items()) or None,
    )
    await db.commit()
    return {"sucessos": sucessos, "falhas": falhas, "total": len(leis)}


async def dry_run(apenas: str | None, cache_dir: Path | None) -> dict:
    """Baixa e parseia sem tocar no banco — relatório de artigos/chunks."""
    sucessos: dict[str, dict] = {}
    falhas: dict[str, str] = {}
    for lei in _filtrar_catalogo(apenas):
        try:
            prep = pl.preparar_diploma(lei, await pl.obter_html(lei, cache_dir))
            sucessos[lei["slug"]] = prep
            print(f"[seed-legislacao] {lei['slug']:6s} DRY-RUN    "
                  f"artigos={prep['artigos']:5d} chunks={len(prep['chunks']):5d} "
                  f"chars={len(prep['texto'])}")
        except Exception as e:
            falhas[lei["slug"]] = f"{type(e).__name__}: {e}"
            print(f"[seed-legislacao] {lei['slug']:6s} FALHA — {falhas[lei['slug']]}",
                  file=sys.stderr)
    return {"sucessos": sucessos, "falhas": falhas}


async def main(args) -> int:
    cache = Path(args.cache_dir) if args.cache_dir else None
    if args.dry_run:
        rel = await dry_run(args.apenas, cache)
    else:
        from app.core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            rel = await executar_seed_legislacao(
                db, apenas=args.apenas,
                embutir_vetores=args.com_embeddings, cache_dir=cache,
            )
    ok, falhas = len(rel["sucessos"]), rel["falhas"]
    print(f"[seed-legislacao] concluído — {ok} ok / {len(falhas)} falha(s)"
          + (f": {sorted(falhas)}" if falhas else ""))
    return 1 if falhas else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Seed de legislação federal (Planalto, por artigo, idempotente)")
    parser.add_argument("--apenas", help="slugs separados por vírgula (ex.: cdc,lgpd)")
    parser.add_argument("--dry-run", action="store_true",
                        help="parseia e reporta sem gravar no banco")
    parser.add_argument("--com-embeddings", action="store_true",
                        help="vetoriza inline (default: adia p/ auto-reembed do scheduler)")
    parser.add_argument("--cache-dir", help="diretório com <slug>.html locais (offline)")
    sys.exit(asyncio.run(main(parser.parse_args())))
