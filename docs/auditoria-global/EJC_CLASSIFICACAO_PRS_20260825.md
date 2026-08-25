# EJC — classificação operacional das PRs abertas — 2026-08-25 BRT

## Regra de promoção

PR aberta/mergeable não equivale a PR aprovada. O EJC exige preservar os gates locais de conteúdo jurídico, segurança, CI/CD, banco e revisão independente previstos em `AGENTS.md`/governança do repositório. A autorização geral do titular para merge/deploy não substitui uma revisão independente expressamente exigida.

## Bloqueio humano/independente

### #1285 — remoção do bridge temporário Verdelimp

- tecnicamente mergeable;
- diff: remoção de um único workflow privilegiado;
- revisão Codex registrou thread P1 não resolvida exigindo `security-auditor` antes do merge;
- **não mesclar** até essa evidência existir.

### #1282 — correções da coleta de fontes do gold set

- tecnicamente mergeable;
- `ruff` e suíte local completos registrados na PR (`6274 passed`, focused `41 passed`);
- CodeRabbit: success; Woodpecker: pending;
- nenhuma revisão GitHub submetida/independente encontrada;
- impacto é indireto, mas jurídico: a ferramenta certifica fontes do gold set;
- permanecer draft até revisão independente/jurídica compatível com a governança.

### #1214 — fail-closed normativo no RAG

- tecnicamente mergeable;
- CodeRabbit: success;
- nenhuma revisão submetida encontrada;
- a própria PR ainda marca CI do HEAD e `EJC Legal Quality Certification` como pendentes;
- permanecer draft.

## Bloqueio de verificação de UI

### #1283 — calculadoras jurídicas no frontend

- tecnicamente mergeable;
- gate local registrado: TypeScript limpo, 621 testes, build verde;
- CodeRabbit: success; Woodpecker: pending;
- nenhuma revisão submetida encontrada;
- a própria PR registra que a verificação manual no navegador não foi concluída;
- permanecer draft até esse passo ou decisão formal conforme a governança de UI.

## Branch antiga com valor exclusivo — não mesclar diretamente

### #1198 — `DELETE_RECUSADO`

- tecnicamente mergeable pelo GitHub, porém a branch está **116 commits atrás da `main`**;
- ainda contém valor exclusivo: a `main` atual grava auditoria na mesma transação da operação e não possui uma trilha independente para recusas que terminam em `HTTPException`/rollback;
- patch original adiciona `registrar_trilha_recusa()` e dois pontos no `DELETE /cases/{id}`;
- CodeRabbit: success, mas nenhuma revisão submetida/independente encontrada;
- decisão: não mesclar a branch histórica diretamente; reconstruir sobre a `main` atual preservando as evoluções de minimização LGPD/auditoria e do router de casos.

## Banco de Teses

PRs #1264 → #1267 → #1269 → #1275 permanecem uma cadeia empilhada/draft. Possuem evolução de schema, evidência jurídica, seed candidato e Radar Jurisprudencial. Não promover individualmente sem reconciliar a cadeia contra a `main`, migrations atuais, Postgres real e gates jurídico/HITL.

## Dependabot

As PRs de dependência não são simplesmente obsoletas: os manifests atuais ainda mantêm diversas versões anteriores (SQLAlchemy 2.0.30, Tenacity 8.2.3, Anthropic 0.120.2, qrcode 7.4.2, fpdf2 2.7.9 e versões frontend anteriores). Não fechar como stale nem mesclar em lote sem testes, pois há upgrades major e dependências sensíveis de ORM/PDF/RAG/estado de frontend.

## Infraestrutura

Woodpecker continua `pending` em PRs recentes e o GitHub Actions tem histórico de `startup_failure` antes da alocação de jobs. Esses estados não são aprovação nem reprovação do código. O P0 do agente self-hosted permanece rastreado em #1288.
