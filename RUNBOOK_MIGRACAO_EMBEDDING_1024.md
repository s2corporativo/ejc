# Runbook — migração de embedding para BGE-M3 (1024d) · Auditoria IA O-2

> ⚠️ **DESTRUTIVO PARA OS VETORES.** A migration 096 recria
> `knowledge_chunks.embedding` como `vector(1024)` e **descarta os embeddings
> 768d** existentes (mpnet). Até o **reindex** concluir, a busca semântica fica
> indisponível e o RAG usa o **fallback textual** (recall menor) — sem erro, mas
> com qualidade reduzida. **Teste em STAGING antes da produção.**

## Por que
Troca o embedding de `paraphrase-multilingual-mpnet-base-v2` (2021, 768d) por
`BAAI/bge-m3` (1024d, multilíngue forte) — recall superior no RAG jurídico.
Dimensões diferentes são incompatíveis: a coluna precisa ser recriada e todo o
corpus reindexado.

## Passos (produção)

1. **Backup** do banco (pg_dump) — ver `RUNBOOK_BACKUP.md`.
2. **Deploy** do código (já traz `EMBEDDINGS_MODEL=BAAI/bge-m3`, `EMBEDDINGS_DIM=1024`).
3. **Migrations** (recria a coluna vazia + índice HNSW):
   ```bash
   docker exec -it ejc_backend python -m alembic upgrade head
   ```
4. **Reindex** (regenera todos os embeddings com o BGE-M3 — baixa o modelo ~2GB no 1º uso):
   - **Automático (default):** com `ENABLE_SCHEDULER=true` e `RAG_AUTO_REEMBED_ENABLED=true`
     (default), o job `reembed_rag_orfaos` roda de hora em hora (:20) e reembeda os
     órfãos sozinho — **nenhum passo manual necessário**. A busca semântica volta
     gradualmente conforme os lotes concluem.
   - **Manual (mais rápido, opcional):** para forçar o reindex imediato:
     ```bash
     docker exec -it ejc_backend python -m scripts.reembedar_chunks_orfaos --batch-size 20
     ```
5. **Validar** com o harness de avaliação (comparar recall com o baseline):
   ```bash
   docker exec -it ejc_backend python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6
   ```

## Pré-requisito
Confirme que a versão instalada do `fastembed` suporta `BAAI/bge-m3` (senão a
geração de embeddings degrada para o fallback textual — silencioso). Teste:
```bash
docker exec -it ejc_backend python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-m3'); print('ok 1024')"
```
Se não suportar, ajuste `EMBEDDINGS_MODEL`/`EMBEDDINGS_DIM` para um modelo
suportado da MESMA dimensão da coluna (ou 768 + downgrade da migration).

## Reverter
```bash
docker exec -it ejc_backend python -m alembic downgrade 095_rag_fts_gin_index
# defina EMBEDDINGS_MODEL=sentence-transformers/paraphrase-multilingual-mpnet-base-v2 e EMBEDDINGS_DIM=768
docker exec -it ejc_backend python -m scripts.reembedar_chunks_orfaos --batch-size 20
```
