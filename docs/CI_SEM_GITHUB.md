# CI local e fallback autônomo — EJC

## Princípio operacional

O GitHub continua sendo o repositório remoto, a superfície de Pull Request e a confirmação final dos gates exigidos pela proteção da `main`. Ele **não deve ser usado como ambiente de diagnóstico iterativo** quando a mesma falha pode ser reproduzida em cópia local isolada.

A regra operacional é:

1. **diagnosticar e corrigir localmente** em branch/worktree separado;
2. executar `scripts/ci-local.sh` no modo adequado;
3. usar o GitHub para sincronização, revisão, checks finais e integração quando estiver disponível;
4. se GitHub/API/runner falhar de forma transitória, acionar o fallback local automaticamente, sem pedir ao titular qual caminho seguir;
5. nunca usar indisponibilidade do GitHub como justificativa para trabalhar na `main`, operar produção, desabilitar gate ou fazer deploy de branch não integrada.

## O que é proibido como diagnóstico

Não criar commits temporários ou alterar `package.json`, `postinstall`, workflows, dependências, hooks ou código de produto **apenas para fazer o GitHub imprimir um diff/log**. Também não criar falha deliberada de CI para obter informação que possa ser produzida localmente.

Quando um check remoto falhar:

- leia o diagnóstico remoto se ele estiver disponível;
- reproduza a etapa equivalente localmente;
- aplique a correção real na branch;
- rode o gate local novamente;
- só então sincronize e use o GitHub como confirmação final.

## Fallback automático quando o GitHub falhar

Falhas transitórias incluem, por exemplo: HTTP 5xx, timeout, rate limit, runner indisponível, job cancelado por infraestrutura e erro de API sem relação com o código.

Fluxo obrigatório dos agentes:

1. repetir a operação remota no máximo duas vezes quando a falha for claramente transitória;
2. persistindo a falha, continuar imediatamente em worktree/cópia local isolada;
3. executar o menor modo local que reproduz o problema (`frontend`, `backend`, `release`, etc.);
4. corrigir até esse modo ficar verde;
5. executar `full`; para fechamento de integração de maior risco, executar `parity`;
6. registrar o SHA local e o diretório de relatório;
7. quando o GitHub voltar, atualizar a base, sincronizar a branch e executar os checks finais exigidos pela proteção da `main`.

**Não é necessário pedir autorização ao titular para escolher esse fallback.** A exceção continua sendo operação irreversível, produção, segredo/credencial, dado real ou conflito material de escopo.

## Gate local canônico

`scripts/ci-local.sh` usa dependências travadas pelo próprio projeto e banco efêmero. Por padrão os logs ficam em `/tmp/ejc-ci-local/<timestamp>`, fora do repositório.

```bash
scripts/ci-local.sh fast
scripts/ci-local.sh frontend
scripts/ci-local.sh backend
scripts/ci-local.sh eval
scripts/ci-local.sh release
scripts/ci-local.sh governance
scripts/ci-local.sh architecture
scripts/ci-local.sh continuity
scripts/ci-local.sh browser
scripts/ci-local.sh full
scripts/ci-local.sh parity
```

### `fast`

Guardas locais de governança + release P0 + testes backend sem DB-level. Destinado a ciclo rápido/pre-push quando as dependências já estão instaladas.

### `frontend`

Executa:

- `npm ci` usando `package-lock.json`;
- Prettier bloqueante;
- Vitest;
- `npm audit --audit-level=high`;
- ESLint;
- typecheck + Vite build.

O formatter vem do `package-lock`; **não** é criada dependência temporária de diagnóstico.

### `backend`

Executa em PostgreSQL 16 + pgvector efêmero:

- sintaxe dos scripts críticos;
- validação dos modelos RAG;
- extensões `vector`, `pg_trgm`, `pgcrypto`;
- Ruff;
- `pip-audit`;
- `alembic upgrade head`;
- pytest completo com `RUN_DB_TESTS=1` e cobertura mínima de 65%.

### `eval`

Executa o smoke dos gold sets e a avaliação offline de trajetória do agente.

### `release`

Executa `scripts/ci_guard.sh` e as provas de wrapper cifrado, rollback de deploy e recuperação do runner.

### `governance`

Verifica localmente arquivos alterados, reserva de migration, padrões de segredo e proteção contra escrita direta na `main`. Metadados de PR e reviews continuam sendo verificados remotamente quando o GitHub estiver disponível.

### `architecture`

Executa testes, geração e refinamento do inventário arquitetural em diretório temporário.

### `continuity`

Executa `alembic upgrade head` e o `restore_drill.py` contra banco efêmero, gerando relatório de restauração fora do repositório.

### `browser`

Executa ESLint/build e os smokes responsivos em Chromium para login e dashboard premium. A instalação do Playwright é `--no-save --package-lock=false`, sem alterar dependências versionadas.

### `full`

Gate local normal antes de sincronização/PR: governança + release + arquitetura + backend + eval + frontend.

### `parity`

Gate local máximo: `full` + continuidade + browser. É o equivalente operacional mais próximo da soma dos workflows remotos atuais.

## Banco efêmero e isolamento

O script usa Docker com `pgvector/pgvector:pg16` quando disponível. Sem Docker, pode usar PostgreSQL local efêmero. As credenciais são fixas **apenas para o banco descartável de teste** e nunca apontam para produção.

O procedimento deve ocorrer em cópia de trabalho/worktree separado. Não executar desenvolvimento no diretório de produção e não reutilizar `DATABASE_URL` de produção.

## Dependências e modo offline

O fallback elimina a dependência do GitHub Actions para diagnóstico, mas algumas verificações dependem dos registries oficiais para instalar/auditar pacotes ou do download do Chromium. Se a rede externa também estiver indisponível:

- reutilize venv/node_modules já instalados com `CI_SKIP_PIP=1` e `EJC_SKIP_NPM_CI=1`, quando íntegros;
- reutilize Playwright já instalado com `EJC_SKIP_BROWSER_INSTALL=1`;
- **não marque `full`/`parity` como verde** se uma auditoria obrigatória não puder ser executada.

A indisponibilidade pode adiar apenas a confirmação daquele gate; não exige intervenção manual para continuar análise/correção que seja reproduzível localmente.

## Pre-push

Ative uma vez na cópia de desenvolvimento:

```bash
git config core.hooksPath .githooks
```

O hook usa `full` por padrão. Para uma rodada específica de paridade máxima:

```bash
EJC_PREPUSH_MODE=parity git push
```

No fluxo autônomo, não burlar o hook para acelerar integração.

## Relação com os workflows remotos

Os workflows do GitHub permanecem como defesa independente e confirmação final quando disponíveis. A diferença é de função:

- **local:** diagnóstico, correção, repetição rápida e prova antes do push;
- **GitHub:** revisão remota independente, branch protection, histórico de PR e integração.

Assim, uma pane do GitHub não paralisa o trabalho técnico, mas também não reduz as proteções da `main` nem autoriza deploy fora da esteira aprovada.
