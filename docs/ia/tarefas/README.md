# Modelos de tarefa para agentes

Use estes modelos antes de pedir ao Antigravity ou a outro agente para alterar o EJC.

As regras de `docs/GOVERNANCA_IA.md` e `CLAUDE.md` prevalecem. Nao inicie tarefa vaga. Antes de executar, registre repositorio, branch-base, ambiente afetado, problema observado, evidencia, criterio de aceite e plano de validacao.

## Quando usar

| Modelo | Uso |
|---|---|
| `CORRIGIR_BUG_FRONTEND.md` | erro visual, fluxo de tela, validacao de formulario, estado vazio/loading/erro |
| `CORRIGIR_BUG_BACKEND.md` | rota, service, autorizacao, validacao, erro de API |
| `CORRIGIR_BANCO_MIGRATION.md` | Alembic, models, seeds, heads, drift ou dados |
| `AUDITAR_SEGURANCA.md` | auth, RBAC, LGPD, uploads, logs, secrets, IA gateway |
| `PREPARAR_PR.md` | Issue, branch, validacao local e corpo de PR |
| `REVISAR_PR.md` | revisar diff, CI, risco, duplicidade, conflitos e ordem de merge |
| `VALIDAR_DEPLOY.md` | preflight, health check, rollback e observacao pos-deploy |
| `INVESTIGAR_FALHA_CI.md` | reproduzir pipeline localmente e corrigir causa real |
| `CORRIGIR_INTEGRACAO.md` | DataJud, DJEN, Drive, IA, email, storage ou API externa |
| `AUDITAR_FUNCIONALIDADE.md` | revisar fluxo completo sem implementar mudanca imediata |

## Campos obrigatorios

Todo modelo deve preencher: repositorio, branch-base, ambiente, problema, comportamento esperado, evidencia, reproducao, hipotese, arquivos envolvidos, impactos, riscos, fora de escopo, validacao, comandos, testes, resultado antes/depois, rollback, pendencias e criterios de aceite.
