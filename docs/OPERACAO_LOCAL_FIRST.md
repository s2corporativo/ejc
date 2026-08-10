# Operação local-first do EJC

## Objetivo

O desenvolvimento do EJC não deve parar porque GitHub, GitHub Actions, DNS ou o remoto `origin` estejam indisponíveis.

A ordem operacional passa a ser:

1. checkout DEV isolado;
2. Git local como fonte imediata do trabalho;
3. registro local da tarefa quando Issue não puder ser criada;
4. checkpoint recuperável fora da árvore do repositório;
5. validação com `scripts/ci-local.sh`;
6. GitHub apenas como sincronização/espelho quando estiver disponível;
7. produção somente pelo mecanismo de deploy seguro existente.

O GitHub continua útil para colaboração, histórico remoto, PRs e espelho. Ele deixa de ser requisito para preservar trabalho, executar testes ou continuar uma tarefa autorizada.

## Regra de segurança

Não desenvolver no checkout de produção. O script considera `/opt/ejc` como diretório de produção por padrão. Se a topologia da VPS usar outro caminho, configure `EJC_PRODUCTION_DIR` no ambiente operacional.

Nunca colocar no fluxo de contingência:

- `.env`;
- chaves privadas;
- certificados;
- credenciais;
- tokens;
- dumps de banco com dados reais;
- documentos de clientes;
- PII real em registro técnico de tarefa.

O snapshot local usa `umask 077`, diretórios `0700` e arquivos `0600`. Arquivos não rastreados com nomes sensíveis, symlinks e arquivos acima do limite configurado são deliberadamente excluídos do snapshot.

**Proteção de dados sensíveis no checkpoint:**
- Arquivos rastreados/staged que correspondam a padrões sensíveis (`.env`, chaves `.pem`/`.key`, etc.) têm seus diffs **filtrados** e substituídos por marcador `# FILTERED` nos patches, garantindo que conteúdo sensível nunca seja persistido mesmo quando o arquivo estiver no index ou working tree.
- Se o histórico commitado contiver nomes de arquivos sensíveis, o git bundle é **bloqueado** para evitar vazamento de segredos através de commits históricos.
- A filtragem cobre: arquivos rastreados modificados, arquivos staged, arquivos não rastreados, branches, tags e histórico commitado — não apenas `sensitive_path` para arquivos não rastreados.

## Comando canônico

Use `bash` explicitamente para que o procedimento não dependa da preservação do bit executável ao transportar o repositório:

```bash
bash scripts/ejc-local-first.sh status
bash scripts/ejc-local-first.sh register "titulo tecnico" "escopo sem segredo ou PII real"
bash scripts/ejc-local-first.sh checkpoint
bash scripts/ejc-local-first.sh validate full
bash scripts/ejc-local-first.sh sync
bash scripts/ejc-local-first.sh work full
```

### `status`

Mostra branch, SHA, working tree, quantidade de registros locais pendentes e disponibilidade do remoto. A indisponibilidade do remoto é aviso, não falha do trabalho local.

### `register`

É usado somente quando a tarefa autorizada precisa começar e o GitHub não permite criar Issue.

O registro fica em:

```text
${EJC_RECOVERY_ROOT:-$HOME/.local/state/ejc-recovery}/<repositorio>/pending-tasks/
```

Ele contém título técnico, escopo, branch, SHA e data. Não deve conter segredo, PII real ou documento de cliente. O script rejeita padrões óbvios de segredo antes de gravar.

Quando `sync` detecta o GitHub disponível, tenta converter os registros pendentes em Issues usando `gh` **somente se** o CLI já estiver instalado e autenticado. Se `gh` estiver ausente, desautenticado ou falhar, os registros permanecem intactos para tentativa posterior; não há perda nem exclusão silenciosa.

Esse é o mecanismo **store-and-forward** da rastreabilidade: indisponibilidade externa não bloqueia a escrita autorizada, mas a rastreabilidade permanente é reconciliada quando o serviço volta.

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
- não perde checkpoint nem registro de tarefa;
- não executa reset/rebase/merge;
- continua permitindo validação local.

Se o remoto estiver disponível:

- executa `git fetch --prune`;
- nunca faz force push;
- nunca publica `main`/`master`;
- se a branch remota avançou, apenas informa divergência e preserva o trabalho local;
- se a branch não está atrás do remoto, pode publicar a branch normalmente;
- tenta sincronizar os registros locais pendentes como Issues sem transformar falha dessa etapa em perda do trabalho.

O push best-effort pode ser desligado com:

```bash
EJC_LOCAL_FIRST_AUTO_PUSH=0 bash scripts/ejc-local-first.sh sync
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

Quando GitHub/Actions estiver indisponível, a entrega deve ser preservada via checkpoint e CI local. Sem canal automatizado disponível, o trabalho permanece validado localmente (checkpoint + CI local verde) e a sincronização (push/sync) é feita quando o GitHub voltar. O deploy ocorre **somente pela esteira automatizada** normal após CI verde na main.

**Não há canal autorizado de deploy manual em contingência.** A orientação deve ser preservar a entrega (checkpoint + CI local verde) e aguardar a esteira automatizada após CI verde na main. Essa contingência não autoriza um agente sem acesso operacional seguro à VPS a inventar caminho, credencial ou estado. O agente deve usar o acesso já conectado/disponível; se não houver canal operacional, mantém a entrega validada e sincroniza quando houver canal seguro, sem solicitar ou expor segredo.

## Política para agentes de IA

Quando uma operação do GitHub falhar:

1. não repetir indefinidamente a mesma chamada;
2. classificar se a falha é apenas remota ou se afeta o código local;
3. registrar a tarefa localmente se ainda não houver Issue;
4. preservar o estado com `checkpoint`;
5. continuar análise, edição e testes no checkout DEV;
6. usar `scripts/ci-local.sh` como gate;
7. tentar `sync` novamente somente quando for útil para publicação;
8. não pedir ao titular para intervir se existir uma alternativa local segura;
9. só parar quando a alternativa exigiria operação irreversível, segredo não disponível ou violação de LGPD/segurança.

## Rollback do próprio mecanismo local-first

A adoção é reversível porque não altera schema, banco ou runtime. Para deixar de usar o fluxo, basta não chamar `scripts/ejc-local-first.sh`; `scripts/ci-local.sh` e o deploy seguro continuam independentes. Registros/checkpoints locais podem ser mantidos para auditoria ou removidos posteriormente por rotina controlada, nunca por limpeza destrutiva automática.
