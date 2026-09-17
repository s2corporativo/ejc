# Woodpecker CI — CI/CD self-hosted (substituto do GitHub Actions)

Contexto: desde ~22/08/2026 o GitHub Actions da conta não aloca runner
(`startup_failure` em 1s, sem job, em todos os repositórios — inclusive nos
workflows que já rodavam no runner self-hosted `ejc-vps`, porque o bloqueio é
na conta, antes da alocação). O Woodpecker roda inteiro na nossa VPS e recebe
os webhooks do GitHub, que continuam funcionando normalmente; o billing do
Actions deixa de ser dependência.

Os repositórios ativos já têm pipeline versionado (`.woodpecker.yml` na raiz),
replicando o portão local obrigatório de cada um:

| repo | portões do pipeline |
|---|---|
| `ejc` | backend: ruff + alembic heads/upgrade + pytest (Postgres pgvector de serviço); frontend: lint + vitest + build |
| `verdelimpclaude` | `npm run verificar:db` (todos os portões, com banco descartável) |
| `s2licit` | `pnpm check` + `pnpm test` + `pnpm build` |
| `cuidar-vet-plataforma` | `pnpm install --frozen-lockfile` + `check` + `test` + `build` |

Os demais (`anifarm`, `clovis-fitness-tracker`, `skills-manus`, …) aparecem na
UI e podem ser habilitados quando ganharem um `.woodpecker.yml`.

## Ativação (uma vez, ~15 min)

1. **OAuth App no GitHub** — github.com → Settings da organização
   `s2corporativo` → Developer settings → OAuth Apps → *New OAuth App*:
   - Homepage URL: `https://ci.depaulateixeira.adv.br`
   - Authorization callback URL: `https://ci.depaulateixeira.adv.br/authorize`
   Guarde Client ID e gere um Client Secret.

2. **DNS** — registro A `ci.depaulateixeira.adv.br` → IP da VPS.

3. **Nginx + TLS** no host da VPS:

   ```nginx
   server {
       server_name ci.depaulateixeira.adv.br;
       listen 80;
       location / {
           proxy_pass http://127.0.0.1:8100;
           proxy_set_header Host $host;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection "upgrade";
           proxy_read_timeout 3600;
       }
   }
   ```

   `nginx -t && systemctl reload nginx`, depois
   `certbot --nginx -d ci.depaulateixeira.adv.br`.

4. **Preparar segredos e permissões** nesta pasta da VPS:

   ```bash
   umask 077
   cp .env.example .env
   chmod 600 .env
   openssl rand -hex 32  # valor exclusivo de WOODPECKER_AGENT_SECRET
   openssl rand -hex 32  # valor diferente para WOODPECKER_GRPC_SECRET
   ```

   Preencha o `.env` sem colar valores em Issue, PR, chat ou logs. Os dois
   segredos devem ser independentes. O Compose falha antes de subir se host,
   OAuth ou qualquer segredo obrigatório estiver vazio.

5. **Validar e subir**:

   ```bash
   docker compose config --quiet
   docker compose up -d
   docker compose ps
   ```

6. **Habilitar os repositórios** — abra `https://ci.depaulateixeira.adv.br`,
   entre com a conta GitHub (`s2corporativo`), Repositories → *Enable* em
   `ejc`, `verdelimpclaude`, `s2licit` e `cuidar-vet-plataforma`. O Woodpecker
   cria o webhook em cada repo automaticamente. A partir daí, push em `main`
   e PR interno do próprio repositório executam o pipeline automaticamente;
   PR vindo de fork continua exigindo aprovação humana e reporta o status no GitHub.

7. Em cada repositório, confirme no painel: modo de aprovação `forks`,
   repositório não confiável (`trusted` desligado) e nenhum volume privilegiado
   liberado. O Compose também desativa registro de agentes por usuários.

### Repositório já habilitado: aplicar o modo `forks` via API

`WOODPECKER_DEFAULT_APPROVAL_MODE` é valor padrão para novos repositórios; o
modo de aprovação do repositório já habilitado fica persistido no Woodpecker.
A API oficial expõe `PATCH /api/repos/{repo_id}` com o campo
`require_approval`. Para o EJC (`repo_id=2`), use o script versionado:

```bash
cd /opt/woodpecker-ci/infra/woodpecker
export WOODPECKER_TOKEN='defina somente nesta sessão'
bash configure-repo-approval.sh
unset WOODPECKER_TOKEN
```

Obtenha o PAT somente na página de perfil do Woodpecker. Não cole o token em
Issue, PR, chat, README, shell history compartilhado ou logs. O script não
persiste nem imprime o token e só aceita sucesso quando a resposta da API
confirma `require_approval=forks`.

O mesmo ajuste pode ser feito pelo Swagger autenticado com
`PATCH /api/repos/2` e corpo `{"require_approval":"forks"}`. Não altere
`trusted`, volumes, segredos, `allow_pr` ou qualquer outro campo nesse ajuste.

## Operação

- Concorrência é 1 workflow por vez (`WOODPECKER_MAX_WORKFLOWS=1`).
- Cada contêiner de pipeline recebe, por padrão, até 3 GiB, sem swap adicional,
  quota de 1 CPU e `CPU_SHARES=512`. Os valores podem ser reduzidos ou
  aumentados pelas variáveis documentadas no `.env.example`, após medir a VPS.
- Os jobs rodam em contêineres descartáveis; nenhum segredo de produção entra
  nos pipelines.
- O pipeline é o mesmo portão local obrigatório do `CLAUDE.md` de cada repo.
- Pushes para branches diferentes de `main` podem ser descartados por `when`
  antes da criação do pipeline. Isso é esperado; erro real é push em `main`,
  PR interno ou PR de fork já aprovado também ser descartado.
- Verifique semanalmente `docker system df` e o uso do disco. Não automatize
  remoção de imagens/volumes na VPS de produção: uma imagem antiga pode ser o
  artefato de rollback.
- O agente idealmente deve migrar para host/VM próprio. Enquanto compartilhar a
  VPS com produção, mantenha concorrência/limites, `trusted` desligado e
  aprovação obrigatória para PRs vindos de forks. A execução automática fica
  restrita aos PRs internos do próprio repositório.

## Diagnóstico administrativo pela API

O Woodpecker expõe no Swagger os endpoints administrativos de agentes e filas.
Para diagnóstico do P0 de alocação, use `diagnose-api.sh`; ele nunca cria agente,
não repara webhook e não imprime PAT ou token do agente.

O PAT deve existir apenas no ambiente local autorizado. Não coloque PAT em
Issue, PR, chat, histórico de shell, `.env` versionado ou argumento de linha de
comando. Prefira carregar o PAT a partir do gerenciador/cofre local da VPS sem
digitá-lo diretamente após `export`. A ferramenta transfere o Bearer para
arquivo temporário `0600`, remove a variável antes de chamar `curl` e apaga o
arquivo ao sair.

```bash
cd /opt/woodpecker-ci/infra/woodpecker

# WOODPECKER_API_TOKEN deve já existir na sessão por mecanismo seguro local.

# Somente leitura: agentes, fila, repo EJC (id 2) e pipeline 447.
bash diagnose-api.sh check 2 447
```

Interpretação:

- lista de agentes vazia ou `last_contact` antigo: a API não consegue consertar
  o processo ausente; execute a recuperação controlada de server/agent abaixo;
- agente presente, recente e `no_schedule=true`: pode ser liberado sem trocar
  token, preservando o nome atual:

  ```bash
  bash diagnose-api.sh fix-schedule <agent_id>
  ```

- agente presente, recente, `no_schedule=false` e capacidade positiva, mas a fila
  continua pendente: conferir `backend`, `platform`, labels e logs locais antes
  de qualquer mutação adicional;
- depois de o agente ficar realmente apto, um pipeline existente pode ser
  reexecutado preservando o evento original:

  ```bash
  bash diagnose-api.sh restart-pipeline 2 447
  ```

Não use `POST /agents` como tentativa de recuperação: ele gera novo token e cria
outra identidade. O agente existente deve preservar sua identidade e
`WOODPECKER_AGENT_SECRET`; se ele não conecta, a correção é operacional no host.

## Backup antes de atualizar ou recriar

O banco do Woodpecker fica no volume `woodpecker-server-data`; copiar arquivos
com o servidor gravando não produz backup consistente. Execute:

```bash
cd /opt/woodpecker-ci/infra/woodpecker
bash backup.sh
```

Antes de parar os serviços, o script renderiza o Compose sem exibir o conteúdo
e bloqueia segredos vazios ou iguais. Depois, interrompe apenas servidor/agente,
copia os dois volumes em modo somente leitura para
`/var/backups/woodpecker`, grava e confere SHA-256, inspeciona os tarballs,
testa a extração em volumes temporários e religa os serviços. Um manifesto
registra o HEAD Git, volumes e IDs locais das imagens. O `.env` não é copiado.

Confirme que os dois arquivos, checksums e manifesto foram criados; não deve
restar volume temporário do teste. Mantenha pelo menos o último conjunto
anterior a cada atualização e preserve separadamente o `.env` em custódia
segura, fora do repositório e dos backups de volume.

## Atualização controlada

As imagens são fixadas em `v3.18.0`. Não troque para `v3`/`latest`.

```bash
cd /opt/woodpecker-ci
git pull --ff-only
cd infra/woodpecker
chmod 600 .env
bash backup.sh
docker compose config --quiet
docker compose pull
docker compose up -d --force-recreate woodpecker-server woodpecker-agent
docker compose ps
docker compose logs --since=2m woodpecker-server woodpecker-agent
```

Mudança de versão exige leitura das release notes, novo backup consistente e
janela de rollback. Servidor e agente permanecem sempre na mesma versão.

## Solução de problemas

### Agente em `Restarting` com `individual agent not found by token`

No Woodpecker v3, os dois segredos do servidor têm finalidades diferentes:

- `WOODPECKER_AGENT_SECRET`: autentica o agente e permite seu registro;
- `WOODPECKER_GRPC_SECRET`: assina os JWTs usados nas conexões gRPC.

O agente também lê `WOODPECKER_AGENT_SECRET`. O mesmo valor de
`WOODPECKER_AGENT_SECRET` precisa chegar ao servidor e ao agente; o segredo
gRPC deve ser outro valor. Configurar apenas `WOODPECKER_GRPC_SECRET` não
autentica o agente.

Para corrigir uma instalação antiga que ainda não possui
`WOODPECKER_GRPC_SECRET`, gere um valor novo e independente no `.env`, faça
o backup e siga a atualização controlada. Não substitua o
`WOODPECKER_AGENT_SECRET` existente, pois isso desregistra os agentes atuais.

O aceite exige servidor saudável, agente estável em `Up` e ausência de novas
mensagens `individual agent not found by token`.

### `when filters filtered out all steps`

Os pipelines versionados rodam em push para `main` e em pull requests.
Portanto, pushes diretos para branches de trabalho são intencionalmente
ignorados. Investigue somente se o evento descartado for push em `main`, PR
interno ou PR de fork já aprovado; nesse caso, habilite log `debug`
temporário e confronte `event`, `branch` e `ref` recebidos com o `when` do
repositório.

## Rollback

1. Não remova volumes e nunca use `docker compose down -v`.
2. Pare servidor e agente.
3. Volte o Compose para a versão exata anteriormente registrada.
4. Se a versão nova migrou o banco, restaure **os dois volumes** a partir do
   conjunto de backups correspondente, com os serviços parados.
5. Suba primeiro o servidor, confira os logs, depois o agente.
6. Valide um pipeline sintético antes de liberar os quatro repositórios.

A restauração sobrescreve estado e exige decisão humana específica. O backup
não autoriza restauração automática.
