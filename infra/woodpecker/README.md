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
           # UI usa streaming de logs:
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection "upgrade";
           proxy_read_timeout 3600;
       }
   }
   ```

   `nginx -t && systemctl reload nginx`, depois
   `certbot --nginx -d ci.depaulateixeira.adv.br`.

4. **Subir o Woodpecker** (nesta pasta, na VPS):

   ```bash
   cp .env.example .env   # preencher CLIENT/SECRET e AGENT_SECRET
   docker compose up -d
   docker compose logs -f woodpecker-server   # conferir boot
   ```

5. **Habilitar os repositórios** — abra `https://ci.depaulateixeira.adv.br`,
   entre com a conta GitHub (`s2corporativo`), Repositories → *Enable* em
   `ejc`, `verdelimpclaude`, `s2licit` e `cuidar-vet-plataforma`. O Woodpecker
   cria o webhook em cada repo automaticamente. A partir daí, todo push em
   `main` e todo PR executam o pipeline e reportam o status no GitHub.

## Operação

- Concorrência é 1 workflow por vez (`WOODPECKER_MAX_WORKFLOWS=1`) para não
  disputar recursos com a produção. Aumente no compose se a VPS aguentar.
- Os jobs rodam em containers descartáveis via Docker do host; nenhum segredo
  de produção entra nos pipelines (e os pipelines versionados não usam
  segredos).
- O pipeline é o MESMO portão local obrigatório do `CLAUDE.md` de cada repo —
  verde no Woodpecker e verde local devem coincidir. Divergência é bug do
  pipeline, corrija no `.woodpecker.yml` do repo.
- Webhooks de push para branches diferentes de `main` podem ser descartados
  por `when` antes da criação do pipeline. Isso é esperado; erro real é um
  push em `main` ou PR também ser descartado.
- Se um dia o GitHub Actions voltar, os dois convivem sem conflito (o
  Woodpecker usa webhooks próprios). A decisão registrada nos `CLAUDE.md`
  continua valendo: o portão local/self-hosted é a fonte de verdade.

## Atualização

```bash
docker compose pull && docker compose up -d
```

## Solução de problemas

### Agente em `Restarting` com `individual agent not found by token`

No Woodpecker v3, os dois segredos do servidor têm finalidades diferentes:

- `WOODPECKER_AGENT_SECRET`: autentica o agente e permite seu registro;
- `WOODPECKER_GRPC_SECRET`: assina os JWTs usados nas conexões gRPC.

O agente também lê `WOODPECKER_AGENT_SECRET`. O `docker-compose.yml` fornece
o mesmo segredo aleatório e persistente às duas funções nesta instalação de
réplica única, preservando o `.env` existente. Configurar apenas
`WOODPECKER_GRPC_SECRET` não autentica o agente.

Depois de atualizar o compose:

```bash
cd /opt/woodpecker-ci
git pull --ff-only
cd infra/woodpecker
docker compose config --quiet
docker compose up -d --force-recreate woodpecker-server woodpecker-agent
docker compose ps
docker compose logs --since=2m woodpecker-server woodpecker-agent
```

O aceite exige servidor saudável, agente estável em `Up` e ausência de novas
mensagens `individual agent not found by token`. Não remova volumes e não use
`docker compose down -v`: o volume do servidor contém o banco do Woodpecker.

### `when filters filtered out all steps`

Os pipelines versionados rodam em push para `main` e em pull requests.
Portanto, pushes diretos para branches de trabalho são intencionalmente
ignorados. Investigue somente se o evento descartado for push em `main` ou
pull request; nesse caso, habilite log `debug` temporário e confronte
`event`, `branch` e `ref` recebidos com o `when` do repositório.
