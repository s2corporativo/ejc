# Wave 5B — W8.2: porta assíncrona experimental de análise de IA

## Escopo executado

Foi criada a primeira fatia do contrato assíncrono para `/ai/analisar-caso`, sem alterar o endpoint síncrono nem o proxy reverso. A nova porta é `POST /ai/analisar-caso/async`, retorna `202` quando habilitada e expõe `GET /ai/analisar-caso/async/{task_id}` para polling.

O contrato inclui os estados `queued`, `running`, `completed` e `failed`, `request_id` idempotente por usuário, vínculo opcional com `case_id`, TTL e isolamento de ownership no polling. Erros internos não são devolvidos ao cliente.

## Guardrails

A porta está desligada por padrão com `IA_ANALISE_ASYNC_ENABLED=false`. A validação de tamanho, autenticação e ownership ocorre antes da criação do job. O endpoint síncrono `/ai/analisar-caso` permanece inalterado.

O armazenamento atual é em memória e, por isso, **não está homologado para múltiplos workers ou produção**. A própria documentação do código registra Redis/Celery como próxima etapa obrigatória antes de ativar a flag em ambiente distribuído. Não houve alteração de `proxy_read_timeout`, Nginx, deploy ou roteamento de modelo.

## Evidências

A suíte `tests/test_ai_async_jobs_w82.py` cobre idempotência, isolamento por usuário, conflito de `request_id` para outro caso, flag desligada, criação única de background task e sanitização de erro interno. Resultado: **6 testes aprovados**.

As regressões `tests/test_ai_idor_case_id_gates.py`, `tests/test_ia_motor_canonico_w8.py` e `tests/test_migracao_gateway_fase1b.py` terminaram com **34 testes aprovados**. A compilação Python e `git diff --check` também foram aprovados.

Permanece o warning de ambiente sobre `VAULT_MASTER_KEYS` ausente; ele não é alterado nesta etapa porque a correção exige configuração de segredo estável, não mudança no fluxo de IA.

## Próxima etapa obrigatória

Antes de ativar `IA_ANALISE_ASYNC_ENABLED`, substituir o store em memória por backend compartilhado com expiração atômica, persistir ou referenciar o AILog de forma auditável, adicionar cancelamento/retry controlado, validar execução com múltiplos workers e integrar a UI de progresso. Somente depois disso deve ser executado o teste cronometrado contra o serviço real e tomada a decisão sobre o timeout do proxy.
