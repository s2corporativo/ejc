# Atualização — Merge e Deploy Disponível — 2026-08-24 BRT

## Autorização

O titular autorizou expressamente nesta sessão a integração e o deploy das frentes tecnicamente disponíveis, preservados os blockers obrigatórios de segurança, integridade de banco e governança dos próprios repositórios.

## S2 / s2corporativo/s2licit

### Merge executado

- PR: #160
- Head integrado: `289e7cfbf30ac3ba365617509782254071dc33dc`
- Merge commit em `main`: `10bcb6c80c16e0cc10fc4eeb848ee6de1b1b6e8e`
- Conteúdo: quatro correções órfãs preservadas após a corrida de merges, incluindo deduplicação, porta local, bootstrap VPS e journal/migration RAG.
- Revisões conhecidas: threads tratadas antes da integração.
- Política do repositório: validação local documentada é a contingência oficial enquanto GitHub Actions não aloca runners.

### Deploy acionado, não executado

O push da `main` acionou o fluxo oficial `deploy-vps.yml`, porém o GitHub Actions encerrou o run antes de iniciar qualquer job:

- run: `32799148374`
- head: `10bcb6c80c16e0cc10fc4eeb848ee6de1b1b6e8e`
- conclusão: `startup_failure`

Resultado objetivo: código integrado na `main`; produção **não pode ser declarada atualizada** por esse canal.

## Verdelimp / s2corporativo/verdelimpclaude

### Merge funcional executado

- PR: #169
- Head integrado: `6e6678407bcb451ad20905cbaca6b7a0bc5e2857`
- Merge commit em `main`: `9d153a5cf905c160573fe5de5d33d9dd9e92ca4f`
- Todas as threads P1/P2 conhecidas da revisão foram verificadas contra o HEAD corrigido e resolvidas antes do merge.
- Correções incluem regras de sanções/certidões, confidencialidade GED, backfill cronológico, mutações em fornecedor arquivado, paginação, papéis e datas civis.

### Trigger oficial de produção executado

Como `deploy-vps.yml` do Verdelimp só dispara por `workflow_dispatch` ou por mudança em `.github/deploy-trigger/production.txt`, foi usado o caminho versionado e auditável:

- branch: `ops/deploy-production-169-20260824`
- commit do trigger: `1b9ba1bee9d80d2f30f74c4d1648283e88b2e8dd`
- PR de deploy: #172
- merge do trigger em `main`: `958491e83f2354d84102b8a6072748e42a0831b7`

### Deploy acionado, não executado

O push do trigger criou o run oficial, mas o GitHub Actions encerrou antes de executar jobs:

- run: `32799280615`
- head: `958491e83f2354d84102b8a6072748e42a0831b7`
- conclusão: `startup_failure`

Resultado objetivo: PR funcional e trigger de produção integrados; produção **não pode ser declarada atualizada** por esse canal.

## Frentes não integradas nesta autorização

Não foram forçados merges das seguintes classes de PR:

- EJC com gate obrigatório de revisão independente/security-auditor ou Release Gate pendente, incluindo #1285;
- Verdelimp #170, que precisa ser reconciliada com o schema/RBAC resultante da #169 antes de integração;
- Verdelimp #144/#149/#132 com drift ou operação de produção sensível;
- CuidarVet #47/#49 com colisão de migration `0020` e cadeia Drizzle desatualizada;
- S2 #159 e demais branches comprovadamente divergentes/sobrepostas;
- PRs empilhadas do Banco de Teses EJC sem os gates exigidos.

## Bloqueio operacional atual

O bloqueio comum comprovado nos dois deploys é externo ao código aplicado: GitHub Actions finaliza os runs com `startup_failure` antes de alocar/executar jobs. Repetir o deploy sem corrigir a alocação/conta/runner não acrescenta evidência e não foi feito em loop.

Para concluir publicação é necessário restabelecer a capacidade de execução do GitHub Actions aplicável à conta/repositórios ou disponibilizar acesso operacional autorizado à VPS por outro mecanismo já aprovado. Depois disso, executar novamente os workflows oficiais e comprovar health/readiness, migrations e commit publicado.

---

# Atualização incremental — 2026-08-25 BRT

Esta seção **substitui o estado operacional** das frentes citadas acima quando houver divergência; o trecho de 24/08 permanece como registro histórico do momento em que foi escrito.

## CI/CD self-hosted — diagnóstico consolidado

O GitHub Actions foi confirmado em `startup_failure` antes da criação de jobs nos runs de S2 e Verdelimp: ambos retornaram lista de jobs vazia. O repositório EJC já contém o Woodpecker self-hosted como contingência oficial fora do billing/alocação do Actions.

O servidor Woodpecker recebe webhooks e cria pipelines, mas os pipelines permanecem `pending`, indicando indisponibilidade do agente self-hosted. Foi criado o issue EJC **#1288 — P0: reativar agente Woodpecker na VPS e destravar CI/deploy**, com o procedimento do host para atualizar/reiniciar `woodpecker-server`/`woodpecker-agent`. Não há acesso SSH/terminal da VPS pelo conector atual, portanto não foi simulada execução remota nem feito loop de retries.

## S2 — consolidação da antiga #159

A #159 foi reavaliada contra a `main` atual. As migrations 0024/0025 e parte do vínculo de fornecedor já haviam sido absorvidas por integrações posteriores; reaplicar a branch antiga reintroduziria journal/schema antigos.

Foi criada a sucessora canônica **#163 — `fix(modulo06): consolidar backfills pendentes sobre a main atual`**, branch `reconcile/modulo06-backfills-20260825`, diretamente da `main`, contendo somente:

- `0028_proposal_items_supplier_backfill.sql`, conservadora/idempotente, sem reescrever 0025;
- `scripts/backfill-price-history.mjs`, dry-run por padrão e transacional quando aplicado;
- entrada correspondente no journal.

A #159 foi comentada e fechada como supersedida. A #163 permanece draft até `pnpm check`, `pnpm test`, `pnpm build` e integridade do journal serem executados no SHA atual.

## CuidarVet — colisão 0020 eliminada sem tocar banco

A antiga #47 acumulava mais de uma centena de commits/frentes e não era segura para merge em bloco. A frente estrutural de banco foi extraída para a sucessora limpa **#54 — `fix(db): formalizar schemas operacionais e remover DDL do runtime`**, branch `reconcile/operational-migrations-20260825`, diretamente da `main` atual.

A #54:

- remove criação/alteração de schema de `getDb()`;
- remove os quatro bootstraps runtime de Compras/Fiscal/Internação/Pet Shop;
- formaliza os módulos na migration aditiva `0027_formalize_operational_modules`;
- mantém Drizzle ciente dos schemas modulares;
- adiciona teste de governança;
- não executou migration nem acessou banco real.

A antiga #49 NuvemVet foi integralmente classificada (21 arquivos) e substituída pela PR empilhada **#55 — `feat(nuvemvet): reconciliar arquivo e importação sobre migrations atuais`**, base #54.

A #55:

- renumera `0020_nuvemvet_report_rows` para **`0028_nuvemvet_report_rows`**, após a 0027;
- preserva o schema atual da `main` em `schemaCore.ts` e adiciona NuvemVet modularmente;
- não porta o lockfile antigo ligado ao pacote `xlsx`;
- remove `xlsx` do caminho funcional; tickets entram no adaptador por JSON/CSV;
- registra `/arquivo-nuvemvet` com `settings.manage` no frontend e exige a mesma permissão no backend;
- preserva os 18.766 registros da validação antiga apenas como referência histórica, não como certificação do novo SHA;
- não executou migration/importação real.

A #49 foi comentada e fechada como supersedida. #54 e #55 permanecem draft até os gates do SHA reconciliado; a #47 segue aberta apenas para classificação das demais frentes ainda acumuladas.

## Verdelimp — #170 reconciliada, validada e integrada

A #170 incorporou por merge commit a `main` pós-#169/#172, ficando 0 commits atrás. A composição foi revista nos eixos de migrations, Prisma, RBAC/guards, seed, alçada e rotinas.

No SHA reconciliado `2b067e1663b02a0ab7ecce50b4619ec1ca98f684`, `npm run verificar:db` foi reexecutado e aprovou **13/13 portões oficiais**, incluindo:

- secrets/dados pessoais;
- Prisma íntegro;
- TypeScript/lint;
- testes unitários;
- auditoria estrutural e vulnerabilidades;
- build de produção;
- migrations em PostgreSQL real descartável;
- drift zero;
- seed;
- 137 testes de integração em 20 arquivos.

CodeRabbit reportou `success`; o único check remoto pendente era Woodpecker, explicado pela indisponibilidade do agente. Como o `CLAUDE.md` do Verdelimp define o portão local como fonte oficial durante essa indisponibilidade, a PR foi promovida e integrada.

- PR: **#170**
- head validado: `2b067e1663b02a0ab7ecce50b4619ec1ca98f684`
- merge commit em `main`: **`0e5dda3fe063908c292cc8b39091d3a21745a43b`**

A integração de código está concluída. **Produção ainda não pode ser declarada atualizada**; não foi criado novo trigger de deploy enquanto o agente self-hosted permanece indisponível.

## Estado objetivo após esta atualização

- S2: #160/#161 integradas; #159 substituída pela #163 draft; produção da leva recente não comprovada.
- Verdelimp: #169 e #170 integradas; #172 foi trigger anterior; produção pós-#170 ainda não comprovada.
- CuidarVet: colisão de migration resolvida em arquitetura de PRs #54→#55; nenhuma migration/importação real executada.
- EJC: gates sensíveis continuam preservados; #1288 registra o P0 do agente Woodpecker; não foi usado bypass de security-auditor.
