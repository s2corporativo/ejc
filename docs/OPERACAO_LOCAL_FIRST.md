# Operação local-first do EJC

## Objetivo

O desenvolvimento do EJC não deve parar porque GitHub, GitHub Actions, DNS ou o remoto `origin` estejam indisponíveis.

A ordem operacional passa a ser:

1. checkout DEV isolado;
2. Git local como fonte imediata do trabalho;
3. checkpoint recuperável fora da árvore do repositório;
4. validação com `scripts/ci-local.sh`;
5. GitHub apenas como sincronização/espelho quando estiver disponível;
6. produção somente pelo mecanismo de deploy seguro existente.

O GitHub continua útil para colaboração, histórico remoto, PRs e espelho. Ele deixa de ser requisito para preservar trabalho, executar testes ou continuar uma tarefa já iniciada.

## Regra de segurança

Não desenvolver no checkout de produção. O script considera `/opt/ejc` como diretório de produção por padrão. Se a topologia da VPS usar outro caminho, configure `EJC_PRODUCTION_DIR` no ambiente operacional.

Nunca colocar no fluxo de contingência:

- `.env`;
- chaves privadas;
- certificados;
- credenciais;
- tokens;
- dumps de banco com dados reais;
- documentos de clientes.

O snapshot local usa `umask 077`, diretórios `0700` e arquivos `0600`. Arquivos não rastreados com nomes sensíveis, symlinks e arquivos acima do limite configurado são deliberadamente excluídos do snapshot.

## Comando canônico

```bash
scripts/ejc-local-first.sh status
scripts/ejc-local-first.sh checkpoint
scripts/ejc-local-first.sh validate full
scripts/ejc-local-first.sh sync
scripts/ejc-local-first.sh work full
```

### `status`

Mostra branch, SHA, working tree e disponibilidade do remoto. A indisponibilidade do remoto é aviso, não falha do trabalho local.

### `checkpoint`

Cria snapshot recuperável fora da árvore do repositório, em:

```text
${EJC_RECOVERY_ROOT:-$HOME/.local/state/ejc-recovery}/<repositorio>/checkpoints/
```

O checkpoint contém:

- SHA base;
- branch;
- `git status`;
- patch binário do working tree rastreado;
- patch do index;
- tar somente de arquivos novos considerados seguros;
- `git bundle` do histórico commitado;
- hashes SHA-256 dos artefatos.

Não executa `reset`, `clean`, rebase, merge, push ou deploy.

### `validate`

Cria checkpoint e chama o CI local já existente:

```bash
scripts/ci-local.sh full
```

Também aceita `backend`, `frontend` e `fast`.

O CI local continua sendo o gate técnico primário quando GitHub Actions estiver indisponível. Ele usa PostgreSQL/pgvector efêmero, Alembic e a suíte do frontend conforme `docs/CI_SEM_GITHUB.md`.

### `sync`

Cria checkpoint antes de qualquer acesso remoto. Depois tenta o remoto por tempo limitado.

Se o GitHub estiver indisponível:

- grava `mode=offline` no estado local;
- não falha a tarefa;
- não perde o checkpoint;
- não executa reset/rebase/merge;
- continua permitindo validação local.

Se o remoto estiver disponível:

- executa `git fetch --prune`;
- nunca faz force push;
- nunca publica `main`/`master`;
- se a branch remota avançou, apenas informa divergência e preserva o trabalho local;
- se a branch não está atrás do remoto, pode publicar a branch normalmente.

O push best-effort pode ser desligado com:

```bash
EJC_LOCAL_FIRST_AUTO_PUSH=0 scripts/ejc-local-first.sh sync
```

### `work`

Executa o ciclo autônomo:

```text
checkpoint -> CI local -> checkpoint -> sync best-effort
```

A queda do GitHub não interrompe o ciclo depois que os testes locais passaram.

## Produção

Este script não faz deploy.

O caminho de produção permanece `scripts/deploy_vps_safe.sh` ou a esteira que o invoque, preservando:

- backup pré-deploy;
- `docker compose config --quiet`;
- build controlado;
- migrations apenas no modo já protegido pelo script;
- healthcheck;
- prova do SHA publicado;
- rollback de imagens;
- checagem pós-deploy.

Quando GitHub/Actions estiver indisponível, a alternativa autorizada é executar o mesmo `scripts/deploy_vps_safe.sh` diretamente no checkout de produção previamente confirmado, nunca copiar arquivos manualmente e nunca editar produção fora desse procedimento. O deploy de contingência deve usar o SHA exato já validado localmente (`TARGET_SHA`) e `REQUIRE_PREDEPLOY_BACKUP=1`.

Não assumir caminhos, credenciais ou estado da VPS: confirmar pelo próprio checkout/ambiente antes de executar. Nenhum segredo deve ser solicitado ou impresso.

## Política para agentes de IA

Quando uma operação do GitHub falhar:

1. não repetir indefinidamente a mesma chamada;
2. classificar se a falha é apenas remota ou se afeta o código local;
3. preservar o estado com `checkpoint`;
4. continuar análise, edição e testes no checkout DEV;
5. usar `scripts/ci-local.sh` como gate;
6. tentar `sync` novamente somente quando for útil para publicação;
7. não pedir ao titular para intervir se existir uma alternativa local segura;
8. só parar quando a alternativa exigiria operação irreversível, segredo não disponível ou violação de LGPD/segurança.

## Rollback do próprio mecanismo local-first

A adoção é reversível porque não altera schema, banco ou runtime. Para deixar de usar o fluxo, basta não chamar `scripts/ejc-local-first.sh`; `scripts/ci-local.sh` e o deploy seguro continuam independentes.
