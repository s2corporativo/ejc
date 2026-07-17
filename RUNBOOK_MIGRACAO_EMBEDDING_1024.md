# Runbook — migração de embedding para 1024d (multilingual-e5-large) · Auditoria IA O-2

> ⚠️ **DESTRUTIVO PARA OS VETORES.** A migration 096 recria
> `knowledge_chunks.embedding` como `vector(1024)` e **descarta os embeddings
> 768d** existentes (mpnet). Até o **reindex** concluir, a busca semântica fica
> indisponível e o RAG usa o **fallback textual** (recall menor) — sem erro, mas
> com qualidade reduzida. **Teste em STAGING antes da produção.**

## Por que
Troca o embedding de `paraphrase-multilingual-mpnet-base-v2` (2021, 768d) por
`intfloat/multilingual-e5-large` (1024d, multilíngue forte) — recall superior no
RAG jurídico. Dimensões diferentes são incompatíveis: a coluna precisa ser
recriada e todo o corpus reindexado.

> Nota (verificação prática 2026-07-17): o candidato original `BAAI/bge-m3`
> **não é suportado** pelo `fastembed==0.8.0` pinado — com ele configurado, a
> geração de embeddings falha silenciosamente e o RAG opera só no fallback
> textual. O default do código já é o e5-large; só volte ao bge-m3 depois de
> atualizar o fastembed para uma versão que o suporte (mesma dimensão 1024,
> sem nova migration).

## Passos (produção)

1. **Backup** do banco (pg_dump) — ver `RUNBOOK_BACKUP.md`.
2. **Deploy** do código (já traz `EMBEDDINGS_MODEL=intfloat/multilingual-e5-large`, `EMBEDDINGS_DIM=1024`).
3. **Migrations** (recria a coluna vazia + índice HNSW):
   ```bash
   docker exec -it ejc_backend python -m alembic upgrade head
   ```
4. **Reindex** (regenera todos os embeddings — baixa o modelo ~1GB no 1º uso):
   - **Automático (default):** com `ENABLE_SCHEDULER=true` e `RAG_AUTO_REEMBED_ENABLED=true`
     (default), o job `reembed_rag_orfaos` roda de hora em hora (:20) e reembeda os
     órfãos sozinho — **nenhum passo manual necessário**. A busca semântica volta
     gradualmente conforme os lotes concluem.
   - **Manual (mais rápido, recomendado no go-live):** para forçar o reindex imediato:
     ```bash
     docker exec -it ejc_backend python -m scripts.reembedar_chunks_orfaos --batch-size 20
     ```
5. **Validar** com o harness de avaliação (comparar recall com o baseline):
   ```bash
   docker exec -it ejc_backend python -m app.eval.run_eval --gold app/eval/gold_set.jsonl --k 6
   ```

## Pré-requisito
Confirme que a versão instalada do `fastembed` suporta o modelo configurado
(senão a geração de embeddings degrada para o fallback textual — silencioso). Teste:
```bash
docker exec -it ejc_backend python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='intfloat/multilingual-e5-large'); print('ok 1024')"
```
Se não suportar, ajuste `EMBEDDINGS_MODEL`/`EMBEDDINGS_DIM` para um modelo
suportado da MESMA dimensão da coluna (ou 768 + downgrade da migration).
O mesmo vale para o reranker: `RAG_RERANK_MODEL=jinaai/jina-reranker-v2-base-multilingual`
(o `BAAI/bge-reranker-v2-m3` também não é suportado pelo fastembed 0.8.0).

## Reverter
```bash
docker exec -it ejc_backend python -m alembic downgrade 094_case_area_taxonomia
# defina EMBEDDINGS_MODEL=sentence-transformers/paraphrase-multilingual-mpnet-base-v2 e EMBEDDINGS_DIM=768
docker exec -it ejc_backend python -m scripts.reembedar_chunks_orfaos --batch-size 20
```
