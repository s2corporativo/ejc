# Runbook — migração segura de embedding para multilingual-e5-large (1024d)

> A migration 096 preserva a coluna 768d como `embedding_legacy_768` e cria
> `knowledge_chunks.embedding` como `vector(1024)`. Até o **reindex** concluir, a busca semântica fica
> indisponível e o RAG usa o **fallback textual** (recall menor) — sem erro, mas
> com qualidade reduzida. **Teste em STAGING antes da produção.**

## Por que
Troca o embedding 768d por `intfloat/multilingual-e5-large` (1024d,
multilíngue), modelo listado nativamente pelo FastEmbed 0.8.0.
Dimensões diferentes são incompatíveis: a coluna precisa ser recriada e todo o
corpus reindexado.

## Passos (produção)

1. **Backup** do banco (pg_dump) — ver `RUNBOOK_BACKUP.md`.
2. **Validar runtime antes da migration:**
   ```bash
   docker exec -it ejc_backend python -c "from app.services.embedding_service import validar_modelo_local; ok,msg=validar_modelo_local(); print(msg); raise SystemExit(0 if ok else 1)"
   ```
3. **Deploy** do código (`EMBEDDINGS_MODEL=intfloat/multilingual-e5-large`, `EMBEDDINGS_DIM=1024`).
4. **Migrations** (preserva a coluna 768d e cria a 1024d + HNSW):
   ```bash
   docker exec -it ejc_backend python -m alembic upgrade head
   ```
5. **Reindex** (regenera todos os embeddings com multilingual-e5-large):
   - **Automático (default):** com `ENABLE_SCHEDULER=true` e `RAG_AUTO_REEMBED_ENABLED=true`
     (default), o job `reembed_rag_orfaos` roda de hora em hora (:20) e reembeda os
     órfãos sozinho — **nenhum passo manual necessário**. A busca semântica volta
     gradualmente conforme os lotes concluem.
   - **Manual (mais rápido, opcional):** para forçar o reindex imediato:
     ```bash
     docker exec -it ejc_backend python -m scripts.reembedar_chunks_orfaos --batch-size 20
     ```
6. **Validar** com o harness de avaliação e confirmar zero órfãos:
   ```bash
   docker exec -it ejc_backend python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6
   docker exec -it ejc_db psql -U ejc_user -d ejc_db -c "SELECT count(*) FROM knowledge_chunks WHERE embedding IS NULL;"
   ```

## Pré-requisito
O CI compara `EMBEDDINGS_MODEL`/`EMBEDDINGS_DIM` com
`TextEmbedding.list_supported_models()` sem baixar pesos. O deploy deve repetir
o mesmo gate no container, antes de aplicar migrations.

## Reverter
```bash
docker exec -it ejc_backend python -m alembic downgrade -1
# defina EMBEDDINGS_MODEL=sentence-transformers/paraphrase-multilingual-mpnet-base-v2 e EMBEDDINGS_DIM=768
# a coluna embedding_legacy_768 é renomeada de volta para embedding; não há reindex
```
