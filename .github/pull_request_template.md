## Issue vinculada

<!-- Todo PR nasce de uma Issue (docs/FLUXO_DE_DESENVOLVIMENTO.md). -->

Closes #

## Problema reproduzido

<!-- O que estava errado, como foi reproduzido (passos, request, log) e qual era o impacto
     jurídico/operacional. Sem reprodução possível, explique por quê. -->

## Solução

<!-- O que foi feito e por quê. Decisões de desenho e alternativas descartadas. -->

## Arquivos alterados

<!-- Agrupados por área (backend/frontend/banco/infra/docs), uma linha por grupo. -->

## Migrations

- [ ] Nenhuma migration neste PR
- Número(s) e head resultante:
- Reserva registrada em `backend/alembic/MIGRATION_RESERVATIONS.md`:
- Comportamento em banco novo **e** em banco existente com dado legado:

## Testes executados

<!-- Comandos e resultado: pytest, ruff, vitest, tsc --noEmit, npm run build.
     Cole os números (passed/failed) e explique falhas preexistentes. -->

```
```

## Evidências

<!-- Saída de teste, captura de tela (mudança de UI), log da reprodução e da correção. -->

## Impacto jurídico

- [ ] Não se aplica
- Fonte oficial (lei/artigo, súmula, precedente):
- Vigência e versão da regra:
- Aviso de revisão humana visível ao usuário:
- Homologação necessária antes de o resultado virar documento formal:

## Impacto LGPD

- [ ] Não se aplica
- Dados pessoais tocados e base legal:
- Log, erro e telemetria sem PII:
- Retenção, minimização e acesso do titular:

## Escopo

- [ ] Alteração coesa e dentro do escopo da Issue
- [ ] Sem credenciais, dados pessoais ou documentos reais
- [ ] Sem deploy direto ou mudança manual não registrada
- [ ] Nenhum arquivo em conflito com outro PR aberto

## Segurança e dados

- [ ] Ownership/RBAC/ABAC revisados
- [ ] LGPD e exposição de metadados avaliadas
- [ ] Logs e erros não revelam segredos ou PII
- [ ] Comportamento fail-closed em indisponibilidade (Redis, provedor, flag ausente)
- [ ] `security-auditor` executado (auth, RBAC, upload, portal ou configuração)
- [ ] HITL, gate de citações e sanitização de PII intactos
- [ ] Migração possui estratégia de rollback/compatibilidade

## Evidências de CI

- [ ] CI completo aprovado no head exato
- [ ] P0 Guard aprovado
- [ ] Continuity and UI Gates aprovado
- [ ] Evidência manual anexada quando a mudança exigir interação humana

## Banco e continuidade

- [ ] `alembic upgrade head` validado
- [ ] Backup/restore considerado antes de alteração destrutiva
- [ ] Nenhum `DROP`, exclusão física ou cutover irreversível sem plano aprovado

## Riscos residuais e limitações

<!-- O que este PR não resolve, o que pode quebrar, o que depende de ambiente. -->

## Rollback

<!-- Como reverter código, configuração e banco com segurança. -->

## Checklist de aceite

- [ ] Correção técnica (`docs/CRITERIOS_DE_ACEITE.md`, camada A)
- [ ] Segurança (camada B)
- [ ] Validade jurídica (camada C), quando aplicável
- [ ] Fluxo funcional (camada D)
- [ ] Regressão (camada E)
- [ ] Relatório final do executor presente neste PR
- [ ] **Sem merge pelo executor** — merge e deploy são atos humanos autorizados pelo titular
