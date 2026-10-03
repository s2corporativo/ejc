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

1. **Backup** do banco (pg_dump) — ver `RUNBOOK_BACKUP.md`. Confirme também
   espaço para a coluna vetorial antiga + nova e ~2,3 GB do modelo ONNX.
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

> ⚠️ **Não use `alembic downgrade` para reverter o modelo de embeddings.**
> (auditoria RAG 04/09, A-17)
> - `downgrade -1` desfaz a migration mais recente do repositório (o head
>   atual), não a 096.
> - Descer até antes da `096` **destrói os vetores 1024d**: a `145` já removeu
>   `embedding_legacy_768`, o downgrade dela recria a coluna **vazia**, e o
>   downgrade da `096` dropa a coluna 1024d populada e renomeia a vazia para
>   `embedding`. A promessa antiga ("não há reindex") deixou de valer.

Caminho seguro, se for preciso voltar a 768d:

1. Backup antes de qualquer passo (`scripts/backup.sh`; confira o dump).
2. A volta a 768d é uma **nova** migration expand/contract, revisada e
   reservada em `backend/alembic/MIGRATION_RESERVATIONS.md`:
   - adicionar `vector(768)`;
   - reembutir com o modelo 768;
   - trocar a coluna;
   - remover a 1024.
   Nunca reaproveitar o downgrade da 096.
3. Durante a troca, a busca semântica degrada para o fallback textual, como no
   reindex de ida (nota no topo deste runbook).
4. Em incidente com perda de dados, restaurar o dump do passo 1. Não tentar
   reconstruir os vetores por downgrade.
