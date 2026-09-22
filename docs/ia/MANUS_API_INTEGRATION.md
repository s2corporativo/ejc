# Integração Manus API — EJC

## Status

A integração foi criada como um **MVP desativado por padrão**. Ela não envia dados para a Manus enquanto `MANUS_API_ENABLED=false` ou enquanto `MANUS_API_KEY` estiver vazia.

## Escopo implementado

O EJC expõe um fluxo assíncrono para análise de inteligência jurídica de um caso. O backend sanitiza o texto, rejeita PII estrutural residual, cria uma tarefa na Manus API v2 com `structured_output_schema` e persiste o ciclo de vida em `manus_tasks`. A conclusão chega pelo webhook assinado e só é persistida como resultado quando a Manus informa uma saída estruturada válida.

Rotas autenticadas:

- `POST /api/manus/analises` — inicia uma análise e retorna HTTP 202;
- `GET /api/manus/analises/{task_id}` — consulta status e resultado para o proprietário ou gestão.

Webhook interno:

- `POST /api/manus/webhook` — recebe `task_created` e `task_stopped`; exige `X-Webhook-Signature`, `X-Webhook-Timestamp`, chave pública RSA e janela temporal de cinco minutos.

## Segurança

A integração é externa e, portanto, não deve ser usada para casos com sigilo reforçado. O serviço também exige `AI_EXTERNAL_PROVIDERS_ALLOWED=true`, sanitiza a entrada e executa uma segunda validação com `validar_sem_pii` antes da chamada. A chave Manus nunca é registrada em log ou persistida na tabela de tarefas.

O resultado é sempre um rascunho sujeito a revisão humana. Nenhuma ação de escrita no EJC é executada pelo agente Manus. A tarefa é privada (`share_visibility=private`) e oculta da lista geral de tarefas Manus (`hide_in_task_list=true`).

## Configuração

Defina no ambiente do backend, sem commitar valores reais:

```env
MANUS_API_ENABLED=false
MANUS_API_BASE_URL=https://api.manus.ai
MANUS_API_KEY=
MANUS_WEBHOOK_PUBLIC_KEY=
MANUS_CONNECT_TIMEOUT=10
MANUS_READ_TIMEOUT=30
MANUS_WRITE_TIMEOUT=30
```

Antes de habilitar em homologação, aplicar a migration `162_manus_tasks`, registrar o webhook HTTPS na Manus e obter sua chave pública pelo endpoint oficial. A URL assinada deve ser exatamente a URL pública recebida pelo webhook; diferenças de proxy, host ou esquema podem invalidar a assinatura.

## Rollout recomendado

1. Aplicar a migration em ambiente de homologação.
2. Manter `MANUS_API_ENABLED=false` e validar importação, OpenAPI e testes.
3. Habilitar somente para equipe jurídica autorizada e casos sem sigilo reforçado.
4. Executar um piloto com dados anonimizados.
5. Medir tempo, custo, taxa de saída estruturada válida e correções humanas.
6. Só ampliar o uso após decisão de transferência internacional, política de retenção e homologação jurídica.

## Limitações conhecidas

A entrada textual da API Manus possui limite aproximado de 5.000 tokens; documentos grandes ainda precisam de um próximo incremento que use `file.upload` com política explícita de confidencialidade. A integração não faz polling automático: produção deve depender do webhook; o endpoint de consulta do EJC apenas lê o estado persistido. A chave pública é fornecida por configuração nesta primeira versão; o cache/refresh automático da chave pública deve ser adicionado antes de operar com rotação automática de chaves.

## Rollback

Desabilitar `MANUS_API_ENABLED`, remover a chave do ambiente e reiniciar o backend interrompe novas análises. A migration é aditiva e pode ser revertida com `alembic downgrade 161_manus_tasks` somente se não houver necessidade de preservar o histórico das tarefas Manus.
