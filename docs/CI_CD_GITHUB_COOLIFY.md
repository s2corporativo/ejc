# CI/CD canônico — GitHub Actions + Coolify

Data de adoção: 2026-09-28.

## Objetivo

Migrar o EJC de Woodpecker self-hosted para uma esteira com separação rígida entre validação e produção:

1. Pull Requests e pushes na `main` são validados em runners GitHub-hosted `ubuntu-latest`.
2. Código de PR nunca executa na VPS de produção.
3. Deploy passa a ser responsabilidade do Coolify, conectado somente à branch `main`.
4. Produção nunca recebe deploy de branch de PR.
5. O Woodpecker permanece somente como fallback temporário até o primeiro ciclo verde do GitHub Actions + prova de deploy/rollback no Coolify.

## Critérios para promoção definitiva

- GitHub Actions inicia e conclui no SHA exato do PR;
- nenhum job de `pull_request` usa runner self-hosted;
- todos os gates obrigatórios equivalentes ao CI anterior passam;
- Coolify instalado e acessível;
- Coolify configurado com proxy `Custom (None)` enquanto o Nginx do host ocupar 80/443;
- repositório GitHub conectado por GitHub App com acesso apenas a `s2corporativo/ejc`;
- aplicação de homologação implantada a partir de `main`;
- healthcheck aprovado;
- rollback para a imagem/deploy anterior comprovado;
- somente após essas evidências o Woodpecker pode ser desativado/removido.

## Rollback

Enquanto a migração não for homologada, não alterar o fluxo produtivo atual. Em caso de falha do novo CI ou Coolify:

- interromper promoção do novo fluxo;
- manter o SHA de produção vigente;
- usar o mecanismo de deploy já homologado;
- não desabilitar Woodpecker antes da equivalência comprovada.

## Segurança

A VPS não deve possuir runner de Pull Request. Coolify recebe apenas a branch `main` já integrada. Secrets de produção permanecem fora do Git e não são disponibilizados a workflows de PR.


## Mapa definitivo de responsabilidades

### GitHub Actions

O workflow `.github/workflows/ci.yml` substitui funcionalmente os gates que antes dependiam do Woodpecker:

- detecção de escopo por diff;
- Gitleaks;
- contratos de backup, RAG, deploy e rollback;
- DAG/compatibilidade Alembic;
- Ruff, migrations e pytest em PostgreSQL 16 + pgvector efêmero;
- gold sets e trajetória de IA/RAG offline;
- lint, testes e build do frontend;
- contratos dos agentes;
- Semgrep SAST;
- Trivy HIGH/CRITICAL;
- check agregador `EJC Gate — Actions`.

Jobs pesados independentes executam em paralelo. Em PR, `cancel-in-progress` cancela execuções obsoletas do mesmo ref. Gates não afetados pelo diff ficam `skipped` e o agregador aceita somente `success` ou `skipped`; falha, cancelamento ou estado desconhecido reprova o SHA.

### Coolify

Responsável exclusivamente por CD após integração na `main`:

`PR → EJC Gate — Actions → merge main → Coolify → Docker Compose → healthcheck → produção`.

O Coolify não substitui CI e não deve receber branches de PR.

### Woodpecker

Estado de transição: fallback operacional somente até a homologação completa da nova cadeia. Não receberá novos gates, novas integrações nem novas dependências. Depois de Actions verde + deploy e rollback comprovados no Coolify, remover o check obrigatório `ci/woodpecker/pr/woodpecker`, desativar os agentes e revogar credenciais legadas.

## Eficiência

A nova esteira elimina a fila centralizada na VPS, usa runners efêmeros GitHub-hosted, executa jobs independentes em paralelo, reaproveita caches de Python/npm e cancela execuções antigas da mesma PR. Código de PR não recebe segredos de produção e nunca roda no host produtivo.

## Estado da migração (2026-09-29) — BLOQUEIO EXTERNO

`BLOQUEIO EXTERNO — migração adiada; sistema continua operando com Woodpecker.`

- A conta GitHub permanece bloqueada por billing: nenhum job do GitHub Actions
  chega a executar (0 steps em todos os runs), afetando inclusive runners
  self-hosted. Documentação de 22/08/2026 em infra/woodpecker e memorando
  ALTERNATIVA_CI_SEM_BILLING registram a causa antes da alocação de runner.
- O Woodpecker permanece o CI canônico de fato e de direito (ruleset da main:
  `ci/woodpecker/pr/woodpecker` required, política STRICT). Nenhum bypass.
- Os workflows deste PR (.github/.gitea ci.yml) permanecem DORMANTES e são
  mantidos versionados para retomada imediata quando o billing for resolvido.
  Os testes de governança (test_governanca_workflow.py,
  test_workflows_yaml_carregavel.py, test_self_hosted_runner_isolation.py)
  travam o contrato deles: 20/20 no head atual.
- Critérios de substituição (gates equivalentes + comprovação de deploy +
  rollback) continuam válidos e só serão aplicados na retomada.
