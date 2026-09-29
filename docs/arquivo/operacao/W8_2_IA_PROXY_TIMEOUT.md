# W8.2 — timeout do proxy para IA

## Implementação incremental — 2026-09-21

Foi adicionada uma porta experimental `POST /ai/analisar-caso/async` com polling em `GET /ai/analisar-caso/async/{task_id}`. A porta retorna `202`, usa `request_id` idempotente por usuário, valida ownership antes do job e está desligada por padrão com `IA_ANALISE_ASYNC_ENABLED=false`.

**Não ativar em produção ainda.** O store atual é em memória e não é seguro para múltiplos workers. Antes da ativação, substituir por Redis/Celery com expiração compartilhada, garantir vínculo auditável com AILog, validar retry e cancelamento, testar a UI de progresso e executar smoke cronometrado contra o serviço real. O endpoint síncrono e o Nginx não foram alterados nesta etapa.

## Procedimento de ativação futura

1. Implantar o backend compartilhado de jobs e validar com mais de um worker.
2. Confirmar que cada job possui usuário, caso, `request_id`, status e referência de auditoria.
3. Habilitar `IA_ANALISE_ASYNC_ENABLED=true` somente em staging.
4. Executar polling, refresh da página, erro, retry e concorrência com o mesmo `request_id`.
5. Medir duração p95 e verificar se o proxy ainda encerra chamadas síncronas longas.
6. Promover gradualmente; manter rollback em `IA_ANALISE_ASYNC_ENABLED=false`.

A elevação permanente de `proxy_read_timeout` não substitui a porta assíncrona e não deve ser aplicada como correção isolada.
