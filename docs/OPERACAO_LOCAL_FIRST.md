# Operação local-first do EJC

Decisão do titular: 2026-08-09. Registro: Issue #1000.

## Objetivo

O GitHub deixa de ser dependência operacional. Ele pode continuar como repositório remoto, histórico e espelho de auditoria, mas indisponibilidade de GitHub, GitHub Actions, runner, PR ou checks remotos **não interrompe** edição, validação, build, migration segura, deploy ou rollback.

O caminho operacional canônico passa a ser:

```text
cópia/worktree isolado
  → edição
  → snapshot local sem segredos/dados
  → scripts/ci-local.sh
  → backup pré-deploy obrigatório
  → scripts/deploy_vps_safe.sh
  → /api/health + /api/health/ready
  → rollback automático se falhar
  → sincronização com GitHub quando disponível
```

## Comando único

Use `scripts/operacao-local-first.sh`.

```bash
# Diagnóstico do diretório e identidade local
scripts/operacao-local-first.sh status

# Cria worktree Git local sem acessar remoto; sem .git, cria cópia isolada via rsync
scripts/operacao-local-first.sh prepare p01-vigencia

# Snapshot de código sem .env, uploads, dados, backups, caches ou build
scripts/operacao-local-first.sh snapshot /opt/ejc-worktrees/p01-vigencia

# Validação completa fora do GitHub Actions
scripts/operacao-local-first.sh validate /opt/ejc-worktrees/p01-vigencia

# Snapshot + CI local + backup obrigatório + deploy seguro
scripts/operacao-local-first.sh deploy /opt/ejc-worktrees/p01-vigencia
```

`EJC_CI_MODE=full` é o padrão. Para uma validação intermediária rápida:

```bash
EJC_CI_MODE=fast scripts/operacao-local-first.sh validate <worktree>
```

Deploy deve usar `full`, salvo contingência documentada.

## Identidade de versão sem GitHub

A prova do código publicado não depende de GitHub.

1. Se existe `.git` e a árvore está limpa, usa o SHA local do commit.
2. Se não existe `.git` ou há alteração não commitada, calcula um fingerprint SHA-256 determinístico do código/configuração versionável e o expõe como `local-<40 hex>`.
3. Esse valor é enviado ao deploy como `TARGET_SHA` e passa a ser conferido pelo `/api/health` do mesmo modo que um SHA Git.

O fingerprint exclui deliberadamente:

- `.env` e variantes;
- `uploads/`, `data/`, `backups/`;
- `node_modules/`, venvs, caches, `dist/` e `build/`.

Assim, nenhuma credencial, PII, documento de cliente ou artefato operacional entra na identidade nem no snapshot.

## GitHub indisponível

Quando GitHub/conector/Actions falhar:

1. **não aguardar** runner/check remoto;
2. continuar no worktree/cópia isolada;
3. gerar snapshot antes de mudanças de risco e antes do deploy;
4. rodar `scripts/ci-local.sh`;
5. usar `scripts/operacao-local-first.sh deploy` para produção;
6. registrar localmente a identidade publicada e o resultado dos testes;
7. sincronizar commits/PR/issues depois, quando GitHub voltar.

Falha do GitHub não pode ser tratada como falha do código. Falha da CI local, backup, migration, health/readiness ou rollback **continua bloqueante**.

## Segurança e LGPD

O modo local-first não reduz controles:

- não versiona nem copia `.env`;
- não inclui dados/PII em snapshot;
- mantém RBAC, HITL, citation gate, sanitização de PII e auditoria;
- exige backup pré-deploy no comando `deploy`;
- migrations destrutivas continuam proibidas sem backup, estratégia e rollback;
- não usa `docker compose down -v`, `git reset --hard`, `git clean -fd` ou remoção de volumes;
- não expõe Postgres, Redis ou Ollama.

## Rollback

O wrapper não reimplementa rollback. Ele reutiliza `scripts/deploy_vps_safe.sh`, que preserva as imagens anteriores, restaura backend/worker/frontend em falha e executa `scripts/post_deploy_check.sh`.

Além disso, cada deploy local-first cria um snapshot do código em `EJC_SNAPSHOT_ROOT` (padrão `/opt/ejc-snapshots`) com checksum SHA-256.

## GitHub como espelho

Quando disponível, GitHub continua útil para:

- backup remoto do código;
- histórico de commits;
- Issues/PRs/reviews;
- auditoria e colaboração.

Mas nenhum desses serviços é requisito técnico para a aplicação continuar sendo desenvolvida, validada e publicada com segurança.

## Checklist operacional

- [ ] trabalho em cópia/worktree isolado
- [ ] snapshot sem segredo/PII
- [ ] `scripts/ci-local.sh full` verde
- [ ] `docker compose config --quiet` verde no deploy seguro
- [ ] backup pré-deploy comprovado
- [ ] migration somente se necessária e compatível com rollback
- [ ] backend/frontend build concluído
- [ ] `/api/health` responde e identifica exatamente a versão/fingerprint publicada
- [ ] `/api/health/ready` verde
- [ ] logs sem segredo/PII
- [ ] rollback automático disponível
- [ ] sincronização GitHub é posterior e não bloqueante
