"""scripts/seed_biblia_ejc.py — ingestão idempotente da "Bíblia de Conhecimento EJC".

Carrega o corpus tratado e versionado em seeds/biblia_ejc/*.jsonl (gerado por
scripts/parse_biblia_ejc.py a partir do DOCX "Bíblia de Conhecimento EJC —
Edição Integral v2") na base de conhecimento RAG, via
ingestion_service.upsert_documento.

Governança de IA:
  • Todo documento carrega extra.ficticio=True + aviso no conteúdo — o material
    é DIDÁTICO/FICTÍCIO (o próprio documento manda não usá-lo como caso real).
  • confianca="media": vocabulário de ia_governanca (alta|media|baixa|bloqueado).
    "alta" é reservada a fonte oficial conferida ou material aprovado por sócio
    (checklist de curadoria); "bloqueado" excluiria o material da IA. "media"
    permite o uso como referência metodológica exigindo ponderação do revisor —
    e a Curadoria (Governança da IA) pode reclassificar depois.
  • Categorias: referencia_interna (situações/instruções/governança) e
    modelo_documento_juridico (modelos de peça) — nenhuma entra nos filtros de
    jurisprudência/súmula da busca, então a IA nunca recupera este material ao
    buscar jurisprudência real.

Idempotente: dedup por chave_origem ("biblia_ejc:*"); reexecutar não duplica
("inalterado") e futuras edições do corpus geram novas VERSÕES (histórico
preservado, migration 068).

Uso (dentro do container, WORKDIR /app):  python scripts/seed_biblia_ejc.py
  --sem-vetores    adia a vetorização (docs ficam "pendente"; a busca textual
                   já os encontra; vetorize depois com scripts/vetorizar_documentos.py)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# backend/ no sys.path quando rodado como script avulso.
_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

FONTE_SLUG = "biblia_ejc"
DESCRICAO = "Bíblia de Conhecimento EJC — corpus didático fictício (situações + modelos)"
CORPUS_DIR = _BACKEND / "seeds" / "biblia_ejc"
_LOTE_COMMIT = 25   # commit periódico — limita a transação com embeddings inline


def carregar_corpus(corpus_dir: Path = CORPUS_DIR) -> list[dict]:
    """Lê todos os *.jsonl do corpus (1 documento por linha)."""
    docs: list[dict] = []
    for arquivo in sorted(corpus_dir.glob("*.jsonl")):
        with arquivo.open(encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if linha:
                    docs.append(json.loads(linha))
    if not docs:
        raise SystemExit(f"[seed-biblia] corpus vazio em {corpus_dir} — rode scripts/parse_biblia_ejc.py")
    return docs


async def executar_seed_biblia(db, *, embutir_vetores: bool = True) -> dict:
    """Aplica o corpus na base (idempotente). Comita em lotes."""
    from app.services.ingestion_service import (
        marcar_execucao, registrar_fonte, upsert_documento,
    )

    docs = carregar_corpus()
    await registrar_fonte(db, FONTE_SLUG, DESCRICAO, categoria_rag="referencia_interna")
    await db.commit()

    contagem = {"novo": 0, "atualizado": 0, "inalterado": 0}
    for i, d in enumerate(docs, start=1):
        resultado = await upsert_documento(
            db,
            titulo=d["titulo"],
            categoria=d["categoria"],
            conteudo=d["conteudo"],
            chave_origem=d["chave_origem"],
            fonte=FONTE_SLUG,
            extra={**(d.get("extra") or {}), "rag_status": "aprovado",
                   "uso_autorizado": "estrutura", "ficticio": True},
            confianca="media",   # material didático fictício → exige revisão humana
            embutir_vetores=embutir_vetores,
        )
        contagem[resultado] = contagem.get(resultado, 0) + 1
        if i % _LOTE_COMMIT == 0:
            await db.commit()

    novos = contagem.get("novo", 0) + contagem.get("atualizado", 0)
    await marcar_execucao(db, FONTE_SLUG, status="sucesso", novos=novos, total=len(docs))
    await db.commit()
    return {"total": len(docs), **{f"{k}s": v for k, v in contagem.items()}}


async def main(embutir_vetores: bool) -> None:
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        resumo = await executar_seed_biblia(db, embutir_vetores=embutir_vetores)
    print(
        f"[seed-biblia] total={resumo['total']} novos={resumo['novos']} "
        f"atualizados={resumo['atualizados']} inalterados={resumo['inalterados']}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed da Bíblia de Conhecimento EJC (idempotente)")
    parser.add_argument(
        "--sem-vetores", action="store_true",
        help="não gera embeddings agora (docs ficam pendentes de vetorização)",
    )
    args = parser.parse_args()
    asyncio.run(main(embutir_vetores=not args.sem_vetores))
