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
   cria o webhook em cada repo automaticamente. A partir daí, todo push e todo
   PR executa o pipeline e reporta o status no GitHub (checks no PR).

## Operação

- Concorrência é 1 workflow por vez (`WOODPECKER_MAX_WORKFLOWS=1`) para não
  disputar recursos com a produção. Aumente no compose se a VPS aguentar.
- Os jobs rodam em containers descartáveis via Docker do host; nenhum segredo
  de produção entra nos pipelines (e os pipelines versionados não usam
  segredos).
- O pipeline é o MESMO portão local obrigatório do CLAUDE.md de cada repo —
  verde no Woodpecker e verde local devem coincidir. Divergência é bug do
  pipeline, corrija no `.woodpecker.yml` do repo.
- Se um dia o GitHub Actions voltar, os dois convivem sem conflito (o
  Woodpecker usa webhooks próprios). A decisão registrada nos CLAUDE.md
  continua valendo: o portão local/self-hosted é a fonte de verdade.

## Atualização

```bash
docker compose pull && docker compose up -d
```

## Solução de problemas

### Agente em `Restarting` e o log do servidor diz `WOODPECKER_GRPC_SECRET is not set`

Na v3 o servidor lê `WOODPECKER_GRPC_SECRET` (na v2 era `WOODPECKER_AGENT_SECRET`).
Sem ele o servidor gera um segredo aleatório a cada boot e o agente nunca
autentica. O `docker-compose.yml` já mapeia `WOODPECKER_GRPC_SECRET` a partir
do mesmo `WOODPECKER_AGENT_SECRET` do `.env` — o agente continua usando
`WOODPECKER_AGENT_SECRET`, então o `.env` segue com as mesmas 4 variáveis.

Depois de atualizar o compose:

```bash
cd /opt/woodpecker-ci && git pull
cd infra/woodpecker && docker compose up -d && docker compose ps
```
