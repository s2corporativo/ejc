## Issue vinculada

<!-- Todo PR nasce de uma Issue. -->

Closes #

## Problema reproduzido

<!-- O que estava errado, como foi reproduzido e qual era o impacto técnico, jurídico ou operacional. Sem reprodução possível, explique por quê. -->

## Diagnóstico

- Módulo/camada afetados:
- Arquivos/contratos principais:
- Dependências:
- Risco técnico:
- Risco jurídico/LGPD:
- Risco operacional:

## Solução

<!-- O que foi feito, por quê e quais alternativas foram descartadas. -->

## Arquivos alterados

<!-- Agrupe por backend/frontend/banco/infra/docs. -->

## Migrations

- [ ] Nenhuma migration neste PR
- Número(s) e head resultante:
- Reserva em `backend/alembic/MIGRATION_RESERVATIONS.md`:
- Comportamento em banco novo e banco com dado legado:
- Upgrade/downgrade:

## Testes executados

<!-- Comandos e resultados. Não marque como executado o que não foi rodado. -->

```text
```

## Evidências

<!-- CI, teste, captura de UI, log sanitizado, reprodução/correção. Nunca cole segredo ou PII. -->

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
- [ ] Branch baseada na `main` atual ou divergência explicitamente reconciliada
- [ ] Nenhum PR concorrente conhecido altera o mesmo contrato sem plano de reconciliação

## Riscos residuais

<!-- O que este PR não resolve, o que depende de ambiente ou revisão humana. -->

## Rollback

<!-- Como reverter código, configuração e banco com segurança. -->

## Promoção

- [ ] Merge somente após gates do HEAD exato e revisão exigida
- [ ] Deploy somente pelo mecanismo aprovado do repositório
- [ ] Health/readiness e smoke pós-deploy obrigatórios

A promoção pode ser executada por agente autorizado ou automação aprovada quando esses gates estiverem satisfeitos. Não utilizar bypass da proteção da `main` nem atalho manual de produção.