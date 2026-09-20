#!/usr/bin/env python
# ── scripts/reembedar_chunks_orfaos.py ───────────────────────────────────────
# Auditoria RAG: reembeda chunks órfãos (embedding IS NULL) em documentos que
# hoje estão marcados status_indexacao='indexado' (ou qualquer outro status) —
# diferente de scripts/vetorizar_documentos.py, que só enxerga docs SEM NENHUM
# chunk embedado e por isso NUNCA pega estes.
#
# Causa raiz do problema (ver auditoria RAG / PR de correção):
#   1. app/routers/rag.py::_indexar_doc_bg fazia zip(chunks, vetores) sem
#      checar se o provider devolveu menos vetores que chunks pedidos —
#      chunks "sobrando" ficavam com embedding NULL mesmo com o doc marcado
#      "indexado".
#   2. scripts/reconciliar_status_rag.py (e a migration 029) usavam EXISTS
#      (pelo menos um chunk embedado) em vez de exigir TODOS — perpetuando
#      docs parcialmente vetorizados como "indexado".
# Ambos foram corrigidos no código; este script conserta os DADOS que já
# ficaram órfãos antes da correção.
#
# Garantias:
#   • Só reembeda o CHUNK que está com embedding NULL (nunca duplica chunk,
#     nunca toca em chunk já vetorizado).
#   • Só considera documentos VIGENTES e não excluídos (histórico de versão
#     não é retocado).
#   • Ao final de cada doc, só marca status_indexacao='indexado' se TODOS os
#     chunks do doc (não só os reembedados agora) ficarem com embedding
#     não-nulo — reaproveita a mesma regra do reconciliador corrigido.
#   • Contagem de vetores validada (gerar_embeddings já rejeita provider que
#     devolve contagem errada) — falha de um doc nunca aplica embedding
#     parcial; grava status_indexacao='erro' e segue para o próximo.
#   • Idempotente: pode ser interrompido e re-executado sem duplicar trabalho.
#
# Execução (container ejc_backend, na VPS):
#     docker exec -it ejc_backend python -m scripts.reembedar_chunks_orfaos
#     docker exec -it ejc_backend python -m scripts.reembedar_chunks_orfaos --batch-size 10
#     docker exec -it ejc_backend python -m scripts.reembedar_chunks_orfaos --dry-run
from __future__ import annotations

import argparse
import asyncio
import logging

from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.services.embedding_service import gerar_embeddings, disponivel as emb_disponivel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ejc.reembedar_orfaos")

# Documentos VIGENTES/não excluídos com PELO MENOS UM chunk sem embedding —
# não filtra por status_indexacao de propósito: é exatamente o caso de doc já
# rotulado 'indexado' com chunks órfãos que queremos capturar.
_SQL_DOCS_COM_ORFAO = text("""
    SELECT DISTINCT
           kd.id,
           CASE WHEN kd.status_indexacao = 'erro' THEN 1 ELSE 0 END AS bucket
    FROM knowledge_docs kd
    JOIN knowledge_chunks kc ON kc.doc_id = kd.id
    WHERE kd.deleted_at IS NULL AND kd.vigente = true
      AND kc.embedding IS NULL
      AND (
            CASE WHEN kd.status_indexacao = 'erro' THEN 1 ELSE 0 END > :after_bucket
         OR (
                CASE WHEN kd.status_indexacao = 'erro' THEN 1 ELSE 0 END = :after_bucket
            AND kd.id > :after
         )
      )
    ORDER BY bucket, kd.id
    LIMIT :limit
""")

_SQL_CHUNKS_ORFAOS_DO_DOC = text("""
    SELECT id, conteudo FROM knowledge_chunks
    WHERE doc_id = :doc_id AND embedding IS NULL
    ORDER BY chunk_index
""")

_SQL_DOC_TEM_ORFAO_RESTANTE = text("""
    SELECT EXISTS (
        SELECT 1 FROM knowledge_chunks WHERE doc_id = :doc_id AND embedding IS NULL
    )
""")


async def _reembedar_doc(db, doc_id: str, dry_run: bool) -> str:
    """Reembeda os chunks órfãos de um doc. Retorna 'ok' | 'erro' | 'dry-run'."""
    chunks = (await db.execute(_SQL_CHUNKS_ORFAOS_DO_DOC, {"doc_id": doc_id})).all()
    if not chunks:
        return "ok"   # outro processo já resolveu entre a listagem e agora

    if dry_run:
        logger.info("[dry-run] doc %s: %d chunk(s) órfão(s) seriam reembedados",
                    doc_id, len(chunks))
        return "dry-run"

    textos = [c.conteudo for c in chunks]
    vetores = await gerar_embeddings(textos)
    if not vetores:
        # gerar_embeddings já garante contagem 1:1 quando não é None — se veio
        # None, é falha total (provider indisponível/contagem errada/erro).
        await db.execute(text(
            "UPDATE knowledge_docs SET status_indexacao='erro' WHERE id=:id"
        ), {"id": doc_id})
        return "erro"

    for chunk, vetor in zip(chunks, vetores):
        # Formato texto do pgvector — mesma convenção de app/routers/rag.py
        # (":.6f" evita notação científica, que o parser do pgvector rejeita).
        vec = "[" + ",".join(f"{x:.6f}" for x in vetor) + "]"
        await db.execute(text(
            "UPDATE knowledge_chunks SET embedding = CAST(:v AS vector) WHERE id=:id"
        ), {"v": vec, "id": chunk.id})

    tem_orfao_restante = (await db.execute(
        _SQL_DOC_TEM_ORFAO_RESTANTE, {"doc_id": doc_id}
    )).scalar()
    novo_status = "erro" if tem_orfao_restante else "indexado"
    await db.execute(text(
        "UPDATE knowledge_docs SET status_indexacao=:s WHERE id=:id"
    ), {"s": novo_status, "id": doc_id})
    return "ok"


async def reembedar(
    batch_size: int = 20,
    dry_run: bool = False,
    max_docs: int | None = None,
) -> dict:
    """Reembeda chunks órfãos em lotes, com teto total opcional por rodada.

    batch_size limita cada iteração; max_docs limita a execução inteira.
    O scheduler sempre usa teto conservador; CLI/seed mantêm None por
    compatibilidade e execução supervisionada.
    """
    if not emb_disponivel():
        logger.error("Embeddings indisponíveis (EMBEDDINGS_ENABLED off ou "
                     "provider ausente). Abortando sem alterar nada.")
        return {
            "ok": 0, "erros": 0, "dry_run": 0, "processados": 0,
            "disponivel": False,
        }

    batch_size = max(1, int(batch_size))
    limite_total = None if max_docs is None else max(1, int(max_docs))
    total_ok = total_erro = total_dry = processados = 0
    # Cursor composto por bucket+id: docs que falham migram para bucket=1 e
    # deixam os ainda não tentados (bucket=0) avançarem nas rodadas seguintes.
    # Isso evita starvation sem abandonar retentativas.
    after_bucket = -1
    after = ""
    while True:
        if limite_total is not None and processados >= limite_total:
            break
        limite_lote = batch_size
        if limite_total is not None:
            limite_lote = min(limite_lote, limite_total - processados)

        async with AsyncSessionLocal() as db:
            lote = (await db.execute(
                _SQL_DOCS_COM_ORFAO,
                {
                    "limit": limite_lote,
                    "after_bucket": after_bucket,
                    "after": after,
                },
            )).all()
            if not lote:
                break

            for doc_id, _bucket in lote:
                try:
                    async with db.begin_nested():
                        resultado = await _reembedar_doc(db, doc_id, dry_run)
                except Exception as e:
                    logger.warning(
                        "[reembedar] doc %s falhou: %s", doc_id, str(e)[:200]
                    )
                    await db.execute(text(
                        "UPDATE knowledge_docs SET status_indexacao='erro' WHERE id=:id"
                    ), {"id": doc_id})
                    resultado = "erro"

                processados += 1
                if resultado == "ok":
                    total_ok += 1
                elif resultado == "dry-run":
                    total_dry += 1
                else:
                    total_erro += 1

            await db.commit()
            logger.info(
                "[reembedar] lote commitado — processados=%s ok=%s erro=%s dry-run=%s",
                processados, total_ok, total_erro, total_dry,
            )

        after = str(lote[-1][0])
        after_bucket = int(lote[-1][1])

    limitado = limite_total is not None and processados >= limite_total
    logger.info(
        "[reembedar] concluído — processados=%s ok=%s erros=%s dry-run=%s limitado=%s",
        processados, total_ok, total_erro, total_dry, limitado,
    )
    return {
        "ok": total_ok,
        "erros": total_erro,
        "dry_run": total_dry,
        "processados": processados,
        "limitado": limitado,
        "disponivel": True,
    }

if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Reembeda chunks orfaos (embedding NULL) em docs vigentes, "
                    "mesmo que ja marcados status_indexacao='indexado'.")
    ap.add_argument("--batch-size", type=int, default=20)
    ap.add_argument("--dry-run", action="store_true",
                    help="Só lista quantos chunks seriam reembedados, sem gravar nada.")
    args = ap.parse_args()
    asyncio.run(reembedar(args.batch_size, args.dry_run))
