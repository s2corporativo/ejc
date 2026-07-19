# Runner self-hosted — CI do GitHub de graça (roda no seu VPS)

Mantém os **checks de PR do GitHub** (a UI bonita, o gate de merge), mas a
computação passa a ser do **seu VPS** → **GitHub Actions minutes = 0**. Roda a
mesma `ci.yml` de antes.

> Repo **privado** → seguro para self-hosted (só colaboradores disparam
> workflows). O aviso do GitHub sobre self-hosted vale para repos **públicos**
> (PRs de forks executariam código arbitrário) — não é o seu caso.

## Passo a passo (uma vez)

### 1. Pegue o token de registro
No GitHub: **repo `s2corporativo/ejc` → Settings → Actions → Runners →
“New self-hosted runner” → Linux**. Copie o token que aparece no comando
`./config.sh … --token XXXXXXXX` (é curto, ~1h — use logo).

### 2. Rode o instalador no VPS (como root)
```bash
cd /caminho/do/ejc
git pull
sudo RUNNER_TOKEN="XXXXXXXX" scripts/setup-selfhosted-runner.sh
```
O script faz tudo: instala as dependências nativas do CI (postgresql-client,
libmagic, poppler, tesseract, pango/cairo…), garante **Docker** (para o service
container `pgvector/pgvector:pg16`) e **Node 20**, cria um usuário `ghrunner`,
baixa e registra o runner e o instala como **serviço systemd** (sobe no boot,
reinicia sozinho).

Verifique que ficou **online**: GitHub → Settings → Actions → Runners (deve
aparecer `ejc-vps` verde), ou no VPS:
```bash
( cd /opt/actions-runner && sudo ./svc.sh status )
```

### 3. Mergeie este PR
Os workflows (`ci.yml`, `ejc-release-gate.yml`) já vêm apontados para
`runs-on: [self-hosted, ejc-vps]` e com os gatilhos de push/PR restaurados.
**Mergeie só DEPOIS do runner aparecer online** — senão os checks ficam
“aguardando runner”. Depois de mergeado, todo push/PR roda o CI **no seu VPS**,
sem custo.

## Operação

- **Ver o runner:** `( cd /opt/actions-runner && sudo ./svc.sh status )`
- **Logs:** `sudo journalctl -u actions.runner.* -f`
- **Parar/começar:** `sudo ./svc.sh stop` / `sudo ./svc.sh start`
- **Atualizar o agente:** rode o instalador de novo (idempotente, usa `--replace`).

## Recursos do VPS

O CI sobe um Postgres efêmero (container) e roda a suíte + build do frontend.
Precisa de folga de CPU/RAM e disco durante a execução. Se o VPS for apertado,
rode o CI **fora do horário** ou use o **CI local sob demanda**
(`scripts/ci-local.sh`, ver `docs/CI_SEM_GITHUB.md`) em vez do runner.

## Reverter

- **Voltar para a nuvem paga do GitHub:** troque `runs-on: [self-hosted, ejc-vps]`
  por `runs-on: ubuntu-latest` nos dois workflows (e garanta billing do Actions).
- **Desligar o CI na nuvem de novo (só local):** volte os gatilhos para
  `on: workflow_dispatch` (ver `docs/CI_SEM_GITHUB.md`).
- **Remover o runner do VPS:**
  ```bash
  ( cd /opt/actions-runner && sudo ./svc.sh stop && sudo ./svc.sh uninstall )
  sudo -u ghrunner bash -c 'cd /opt/actions-runner && ./config.sh remove --token <TOKEN_DE_REMOCAO>'
  ```
  (o token de remoção sai no mesmo painel Settings → Actions → Runners.)
