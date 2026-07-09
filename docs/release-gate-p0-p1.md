# Release Gate P0/P1 — EJC

Este documento registra o gate mínimo de estabilização da árvore do EJC antes de novo desenvolvimento funcional.

## Objetivo

Impedir que regressões críticas entrem na `main`, especialmente:

- conflitos de merge versionados;
- arquivos `.env` ou backups de segredo versionados;
- backend com erro básico de compilação;
- frontend que não compila.

## Gate P0

Executado por `scripts/ci_guard.sh`.

Falha quando encontra:

- marcadores reais de conflito: `<<<<<<<`, `=======`, `>>>>>>>`;
- `.env`, `.env.*`, `.env.bak*` ou `vps-tools/.env` versionados, exceto templates explicitamente marcados como `.example`, `.sample`, `.template` ou `.dist`.

Também emite alerta quando identifica resíduos de release, como:

- `_QUARENTENA/`;
- `_dead_code/`;
- `_deploy_e2e1/`;
- arquivos `.bak`, `.old`, `.orig`;
- `graphify-out/`.

## Gate P1

Executado pelo workflow `.github/workflows/ejc-release-gate.yml`.

Valida:

- instalação das dependências do backend;
- compilação básica de `backend/app` com `python -m compileall`;
- instalação limpa do frontend com `npm ci`;
- build do frontend com `npm run build`.

## O que este gate não substitui

Este gate não substitui:

- testes de integração com banco real;
- `alembic upgrade head` em ambiente controlado;
- smoke test autenticado ponta a ponta;
- revisão de RBAC;
- revisão LGPD de logs e dados pessoais;
- validação manual antes de deploy em produção.

## Regra operacional

Nenhum desenvolvimento funcional novo deve ser priorizado antes de a árvore passar no gate mínimo P0/P1.

## Diagnóstico remoto

O P0 usa checkout manual para reduzir dependência de actions externas. Quando falhar, o workflow deve publicar artifact de diagnóstico `p0-guard-log`.
