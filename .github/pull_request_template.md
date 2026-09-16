## Issue vinculada

<!-- Todo PR nasce de uma Issue. -->

Closes #

## Relação com outros PRs

- [ ] PR independente baseado na `main`
- [ ] Stacked PR — depende de PR/branch pai:
- Base atual:
- Ordem de merge esperada:

<!-- Em stacked PR: o filho nunca é promovido antes do pai. Após o merge do pai, retarget/rebase para main e rerode os gates no novo HEAD. -->

## Problema reproduzido

<!-- O que estava errado, como foi reproduzido e qual era o impacto técnico, jurídico ou operacional. Sem reprodução possível, explique por quê. -->

## Diagnóstico

- Módulo/camada afetados:
- Arquivos/contratos principais:
- Dependências:
- Risco técnico:
- Risco jurídico/LGPD:
- Risco operacional:

## Agente de IA e instruções locais

- [ ] `docs/GOVERNANCA_IA.md`, `CLAUDE.md`, `AGENTS.md` e `.agent/rules/*.md` foram lidos
- [ ] `docs/ia/README.md` foi consultado quando o PR foi produzido ou revisado por agente
- [ ] `docs/ia/tarefas/README.md` foi consultado e o modelo usado foi informado:
- [ ] `docs/ia/PROBLEMAS_CONHECIDOS.md` foi consultado/atualizado quando aplicável
- [ ] `docs/ia/VALIDACOES_IDE.md` ou `.vscode/tasks.json` orientou as validações locais
- [ ] O agente confirmou branch, remoto, estado do Git e PRs concorrentes antes de escrever
- [ ] O agente revisou `git diff` antes de concluir
- [ ] Nenhuma afirmação jurídica, técnica ou de teste foi feita sem evidência

## Escopo e coesão

- Decisão técnica única deste PR:
- O que ficou deliberadamente para PR posterior:
- [ ] Não mistura lifecycle/segurança com redesign ou refatoração não necessária
- [ ] Mudanças dependentes da mesma atomicidade permaneceram juntas
- [ ] Integrações sensíveis estão atrás de flag quando isso aumenta reversibilidade sem reduzir segurança

## Solução

<!-- O que foi feito, por quê e quais alternativas foram descartadas. -->

## Arquivos alterados

<!-- Agrupe por backend/frontend/banco/infra/docs. -->

## Migrations

- [ ] Nenhuma migration neste PR
- Tipo: [ ] expand-only  [ ] backfill  [ ] contract/remove
- Número(s) e head resultante:
- Reserva em `backend/alembic/MIGRATION_RESERVATIONS.md`:
- Comportamento em banco novo e banco com dado legado:
- Upgrade/downgrade:
- [ ] Nenhum DROP/contração no mesmo passo de introdução do substituto, salvo justificativa explícita

## Testes dirigidos executados

<!-- Rode primeiro os testes do módulo/contratos tocados. Não marque como executado o que não foi rodado. -->

```text
```

- [ ] Teste dirigido do módulo verde
- [ ] RBAC/ownership/cofre testado quando aplicável
- [ ] Alembic/single-head testado quando aplicável
- [ ] Frontend TypeScript/build testado quando aplicável

## Suíte completa / CI

<!-- Somente depois dos testes dirigidos. -->

```text
```

## Evidências

<!-- CI, teste, captura de UI, log sanitizado, reprodução/correção. Nunca cole segredo ou PII. -->

## Flags e ativação gradual

- [ ] Não se aplica
- Flag(s):
- Estado default:
- Comportamento com flag OFF:
- Comportamento com flag ON:
- Preflight de infraestrutura necessário:

<!-- Nunca usar flag para desligar autenticação, RBAC, auditoria, sanitização LGPD ou validação crítica. -->

## Impacto jurídico

- [ ] Não se aplica
- Fonte oficial/vigência:
- Revisão humana necessária:
- Risco de erro e mitigação:

## Impacto LGPD

- [ ] Não se aplica
- Dados pessoais tocados e necessidade:
- Minimização/retention:
- Logs/telemetria sem PII:
- Ownership/RBAC:

## Segurança e dados

- [ ] Ownership/RBAC/ABAC revisados quando aplicável
- [ ] Logs e erros não revelam segredos ou PII
- [ ] Indisponibilidade crítica falha de forma segura
- [ ] HITL, gate de citações e sanitização permanecem íntegros quando aplicável
- [ ] Nenhum segredo, `.env`, credencial ou documento real foi versionado

## Evidências de CI

- [ ] CI completo aprovado no HEAD exato
- [ ] P0 Guard aprovado
- [ ] Release/continuity gates aplicáveis aprovados
- [ ] Evidência humana anexada quando o critério não for automatizável
- [ ] `mergeable=true` não foi usado como substituto de checks verdes

## Banco e continuidade

- [ ] `alembic upgrade head` validado quando aplicável
- [ ] Backup/restore considerado antes de alteração destrutiva
- [ ] Nenhum `DROP`, exclusão física ou cutover irreversível sem plano aprovado

## Definition of Done

Referência: `docs/engineering/DEFINITION_OF_DONE.md`.

- [ ] DoD revisada para o escopo deste PR
- [ ] Testes compatíveis com o escopo executados
- [ ] Riscos jurídicos/LGPD avaliados
- [ ] Rollback definido
- [ ] Loading/erro/vazio tratados quando houver UI
- [ ] Autorização validada no backend quando houver restrição de acesso
- [ ] Auditoria prevista quando houver impacto jurídico/financeiro/documental/processual/cadastral/segurança
- [ ] Sem quebra conhecida de módulo existente

## WIP e conflitos

Referência: `docs/engineering/WIP_AND_RELEASE_POLICY.md`.

- [ ] Alteração coesa e dentro da Issue
- [ ] Branch baseada na `main` atual ou em PR pai explicitamente declarado
- [ ] Nenhum PR concorrente conhecido altera o mesmo contrato sem plano de reconciliação
- [ ] Se stacked, dependência e ordem de merge estão registradas

## Riscos residuais

<!-- O que este PR não resolve, o que depende de ambiente ou revisão humana. -->

## Rollback

<!-- Como reverter código, configuração e banco com segurança. -->

## Promoção

- [ ] Merge somente após gates do HEAD exato e revisão exigida
- [ ] Stacked PR só promove depois do pai e após rerun dos gates contra a nova base
- [ ] Deploy somente pelo mecanismo aprovado do repositório
- [ ] Health/readiness e smoke pós-deploy obrigatórios

A promoção pode ser executada por agente autorizado ou automação aprovada quando esses gates estiverem satisfeitos. Não utilizar bypass da proteção da `main` nem atalho manual de produção.
