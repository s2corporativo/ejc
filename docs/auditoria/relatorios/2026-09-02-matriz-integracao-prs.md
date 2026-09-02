# Matriz de integração dos PRs — EJC — 02/09/2026

Baseline de referência: `main@802c8edd39dd30fc18a4396b6013ff3317fd0e15`.

Objetivo: impedir merge fora de ordem e distinguir `mergeable=true`, revisão automatizada e CI realmente executado. Esta matriz registra somente PRs conferidos diretamente nesta rodada.

## Regra de promoção

Nenhum PR funcional deve ser promovido se ocorrer qualquer um dos estados abaixo:

- Woodpecker `failure`;
- Woodpecker `pending` sem steps executados;
- ausência do status Woodpecker;
- branch empilhada cujo pai ainda não integrou;
- branch divergente/atrás da `main` sem revalidação após rebase;
- migration concorrente não reconciliada;
- review thread bloqueante aberta;
- ausência de teste PostgreSQL para migration.

`mergeable=true` não substitui esses gates.

## P0 externo — CI

A PR #1296 já foi mesclada e contém a correção de configuração/backup do Woodpecker. A Issue #1295 permanece aberta porque a aplicação operacional na VPS ainda não foi comprovada. Enquanto o agente não executar jobs reais, o CI continua P0.

## Matriz verificada

| PR | Domínio | Base | Draft | Migration | Woodpecker no HEAD consultado | Situação de consolidação |
|---:|---|---|:---:|---|---|---|
| #1381 | RBAC análise bancária | `main` | não | não | **failure** | Bloqueada pelo CI; candidata pequena/prioritária após recuperação |
| #1382 | RAG governança/vigência | `main` | não | não | **failure** | Bloqueada pelo CI; fail-closed |
| #1383 | RAG autoaprovação jurídica | `main` | não | não | **failure** | Bloqueada pelo CI; integrar/rebasear em série com #1382 |
| #1375 | Clientes/Ficha Mestra | `main` | não | não | **failure** | Bloqueada pelo CI |
| #1376 | Peças canônico/hardening | `main` | não | não | **failure** | Bloqueada pelo CI; pai de #1384 |
| #1384 | Peças ↔ Teses | `#1376` | não | não | **failure** | Não promover antes de #1376 + retarget/retest |
| #1378 | Financeiro | `main` | não | não | **failure** | Bloqueada pelo CI; reconhece #1333 como reserva 156 |
| #1380 | Casos consolidado | `main` | sim | não | **failure** | Bloqueada pelo CI; deve preceder reconciliação de #1333 em Casos |
| #1357 | Documentos — base E2E | `main` | não | não | **failure** | Primeiro elo da stack Documentos |
| #1368 | Documentos — governança | `#1357` | sim | `156_documentos_governanca_outbox` | **failure** | Não promover; migration concorrente |
| #1377 | Documentos — workflow backend | `#1368` | sim | não própria | **failure** | Filho de #1368 |
| #1379 | Documentos — UX | `#1377` | sim | não própria | **failure** | Último elo confirmado da stack Documentos |
| #1343 | Prazos P0 | `main` | sim | não | **failure** | Primeiro elo da stack Prazos |
| #1344 | Prazos P1 | `#1343` | sim | não | **failure** | Filho; não promover isoladamente |
| #1345 | Prazos auditáveis/DJEN | `#1344` | sim | `156_prazos_auditaveis_regime` | **failure** | Migration concorrente; renumerar só após rebase real |
| #1346 | Prazos quatro olhos | `#1345` | sim | não própria | **sem Woodpecker registrado** | Bloqueada: ausência de check não é verde |
| #1347 | Agenda intervalos | `#1346` | sim | não | **failure** | Filho; não reserva 157 deliberadamente |
| #1371 | Atividades simplificada | `#1347` | sim | não | **failure** | Último elo confirmado da stack Agenda/Prazos |
| #1374 | Validação isolada Atividades | `main` | sim | não | não promovível por desenho | PR temporária: `Não mesclar`; fechar somente após cumprir sua validação |
| #1333 | Casos — despesas processuais | `main` antiga | sim | `156_case_despesas_processuais` | **success no HEAD antigo** | **Não mergear ainda**: branch divergiu da main atual (13 à frente / 3 atrás); rebase + novo CI obrigatório |
| #1386 | Eval/gold attestation | `main` | não | não | **failure** | Independente; não ativa gate sem chave pública/manifesto externos reais |
| #1387 | Auditoria de consolidação | `main` | sim | não | **failure** | Control plane desta rodada; não promover até CI voltar |

## Colisão Alembic

Três migrations usam o mesmo prefixo 156:

1. #1333 — `156_case_despesas_processuais`;
2. #1345 — `156_prazos_auditaveis_regime`;
3. #1368 — `156_documentos_governanca_outbox`.

A regra segura é serial:

1. reconciliar a candidata 156 sobre a `main` resultante;
2. executar single-head + upgrade/downgrade PostgreSQL;
3. mesclar;
4. rebasear a próxima stack sobre o novo head;
5. só então reservar o próximo número real e ajustar `down_revision`/ledger;
6. repetir para a terceira migration.

Não pré-renumerar branches empilhadas sobre bases antigas.

## Evidência específica da #1333

Comparação direta entre `main` e `4f1f9be0fc0abbf6f2799248c1f00f226a27f997`:

- status: `diverged`;
- ahead: 13 commits;
- behind: 3 commits;
- merge-base: `8c61f3a786f98b72295e717accdcd2cea6250119`;
- arquivos de alto conflito potencial: `backend/app/main.py`, `backend/alembic/MIGRATION_RESERVATIONS.md`, guards de Alembic/rotas e `frontend/src/pages/CasoDetalhe/TabTimeline.tsx`.

Portanto o Woodpecker verde desse head não certifica o merge resultante contra a `main` atual.

## Ordem operacional após a recuperação do CI

A ordem final deve ser recalculada por conflito de arquivos no momento da recuperação, mas a precedência lógica mínima é:

1. gates de infraestrutura e proteção da `main`;
2. PRs pequenas de segurança/fail-closed independentes;
3. Clientes #1375;
4. Casos #1380;
5. Peças #1376 → #1384;
6. Financeiro #1378;
7. Documentos #1357;
8. Prazos #1343 → #1344;
9. reconciliar a fila Alembic #1333 / #1345 / #1368 em sequência real;
10. completar Prazos #1346 → #1347 → #1371;
11. completar Documentos #1377 → #1379;
12. governança de avaliação #1386 quando a infraestrutura externa de atestação existir;
13. regenerar inventários canônicos e executar homologação global.

Cada merge invalida o verde anterior das branches seguintes até novo rebase e novo pipeline.

## Gates finais de sistema

- backend: import/ruff/pytest completos;
- PostgreSQL 16 + pgvector: single-head, upgrade, downgrade focal, re-upgrade e drift;
- frontend: typecheck, Vitest, build;
- OpenAPI/registro explícito de rotas;
- links internos/redirects/query strings;
- navegação por papel + RBAC/ownership negativo;
- jornada fictícia Cliente → Caso → Atividade/Prazo → Documento → RAG → Peça → Financeiro → Portal;
- logs sem PII/segredos;
- backup/restore;
- staging;
- deploy por SHA aprovado + `/api/health` + `/api/health/ready` + smoke.

Até esses gates, o estado correto do EJC é **em consolidação**, não “release certificado”.