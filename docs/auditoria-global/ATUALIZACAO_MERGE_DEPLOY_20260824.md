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
