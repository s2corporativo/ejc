# EJC — Auditoria de infraestrutura (2026-09-06)

**Escopo.** Infraestrutura de execução e operação do EJC conforme versionada no
repositório no commit `3c4f938` (branch `main`): orquestração Docker Compose,
imagens, Nginx do host e do container, esteira de CI (Woodpecker) e de deploy
(host-automation + `deploy_vps_safe.sh` + `deploy_manual.sh`), backup e
continuidade, monitoramento, gestão de segredos e documentação operacional.

**Método.** Leitura integral dos artefatos de infra listados na §7, com
verificação cruzada entre o que o código faz e o que os runbooks declaram.
**Sem acesso à VPS, ao banco ou ao runtime de produção** (regra 9 do
`CLAUDE.md`; porta 22 bloqueada a partir deste ambiente, como já registrado
em `parte-01-analise-nao-autenticada.md`). Tudo o que depende do estado real do
host está na §6 como "não verificável" e vem com o comando que o titular deve
rodar para fechar a lacuna.

**Classificação.** P0 = risco imediato a dado ou disponibilidade; P1 = alto,
corrigir no próximo ciclo; P2 = médio; P3 = higiene/dívida. Cada achado traz
arquivo e linha, o efeito prático e a correção mínima.

---

## 1. Resumo executivo

A infraestrutura está **substancialmente melhor do que a auditada em
27/08/2026**: os dois achados de incidente daquela rodada (AUD27-P1-3 e
AUD27-P1-4, containers sem teto de memória) estão fechados no
`docker-compose.yml`, a esteira migrou do GitHub Actions para Woodpecker
self-hosted sem privilégio de produção, e o deploy é transacional (mutex,
backup obrigatório com prova offsite, migration expand-only, verificação do
SHA no `/api/health`, rollback automático).

O que esta rodada encontrou é, na maior parte, **deriva entre partes do
sistema que foram endurecidas em momentos diferentes**: a lição do incidente
de 04/09 (sonda HTTP sem teto de tempo) foi aplicada ao watchdog e ao deploy
manual, mas não à transação de deploy nem ao serviço automático; o runbook de
backup proíbe dump em claro, mas um script legado ainda o faz; o README
descreve gates de um CI que não existe mais.

| Sev. | Qtd. | Achados |
|---|---|---|
| P0 | 0 | — |
| P1 | 4 | INF-01 sondas sem `--max-time` na esteira automática · INF-02 logs de container sem rotação · INF-03 scripts legados que contornam os gates · INF-04 offsite como cópia única do backup |
| P2 | 8 | INF-05 a INF-12 (rede/Redis, Postgres `shm`, Nginx host×container, `curl -k`, passo fatal de RAG no deploy, dois caminhos de deploy, retenção divergente, observabilidade do host) |
| P3 | 5 | INF-13 a INF-17 (imagens, override versionado, documentação, CI, credencial de acesso) |

Nenhum achado exige janela de manutenção. Os quatro P1 são corrigíveis em
scripts e no compose, sem migration e sem tocar o banco.

---

## 2. O que está correto (e deve ser preservado)

Registrado para que uma correção futura não desfaça por engano:

- **Superfície de rede mínima.** Backend e frontend publicam só em
  `127.0.0.1` (`docker-compose.yml:66-68`, `:196-204`); Postgres e Redis não
  publicam porta; Ollama fica em rede própria `ia` sem porta no host
  (`:268-275`); Langfuse só no loopback (`:240-243`).
- **Nginx do host** com TLS via certbot, HSTS de 2 anos, redirect 301 de
  `:80`, `real_ip` restrito a `127.0.0.1` e **allowlist de `Upgrade`**
  (só `websocket`) que fecha o smuggling h2c (`nginx/ejc.conf:126-141`).
- **CSP restritiva** no container do frontend (`script-src 'self'`,
  `frame-ancestors 'none'`, `base-uri 'self'`) e `server_tokens off`
  (`frontend/nginx.conf:20-24`).
- **Tetos de memória** em todos os serviços, inclusive os opt-in
  (`docker-compose.yml:16,34,60,144,214,235,298`).
- **Migrations fail-closed**: `RUN_MIGRATIONS` default `0` no compose e no
  entrypoint (`docker-compose.yml:79`, `backend/entrypoint.sh:35-46`), decisão
  derivada de `check_migration_compatibility.py` sob mutex, bloqueio se a
  migration pendente não for expand-only.
- **Deploy transacional**: snapshot do `.env` com `mktemp` 0600, tags
  imutáveis de rollback, `.deployed_sha` gravado atomicamente, SHA conferido
  no `/api/health` antes de trocar o worker
  (`scripts/deploy_vps_safe.sh:186-282`).
- **CI sem privilégio de produção**: o Woodpecker não recebe `docker.sock`
  de produção nem `/opt/ejc`; o gate host-level exige pipeline `push/main`
  `success` para o SHA exato e revalida `origin/main` após o mutex e após o
  rsync (TOCTOU coberto) (`infra/host-automation/ejc-deploy-approved.sh:59-62,
  116-119`). PRs de fork exigem aprovação humana; registro de agente por
  usuário desligado (`infra/woodpecker/docker-compose.yml:24-25`).
- **Ferramentas de segurança pinadas** (semgrep 1.172.0, trivy 0.74.0,
  gitleaks v8.30.1, Woodpecker v3.18.0, rclone 1.75.0) e secret scanning
  bloqueante (`.woodpecker.yml:64-83`).
- **Watchdog** reescrito com `--max-time`, `flock`, cooldown e coleta
  forense antes do restart (`scripts/monitor_health.sh`).
- **Segredos**: `.gitignore` cobre `.env*`, `/secrets/`, `/backups/`,
  `/data/`; nenhuma credencial encontrada no repositório (varredura por IP da
  VPS, senha e `sshpass` só retornou documentação histórica em
  `docs/arquivo/`).
- **Runbooks honestos**: `RUNBOOK_DEPLOY_MANUAL.md` e `RUNBOOK_BACKUP.md`
  declaram explicitamente o que não foi exercitado contra produção.

---

## 3. Achados P1

### INF-01 — Sondas HTTP sem teto de tempo na esteira automática de deploy

**Evidência.**

| Arquivo | Linha | Chamada |
|---|---|---|
| `scripts/deploy_vps_safe.sh` | 255 | `curl -fsS http://127.0.0.1:8000/api/health` (laço de 12×5 s) |
| `scripts/deploy_vps_safe.sh` | 262 | `curl -fsS http://127.0.0.1:8000/api/health` (leitura do `commit`) |
| `infra/host-automation/ejc-deploy-approved.sh` | 36 | idempotência por SHA |
| `infra/host-automation/ejc-deploy-approved.sh` | 134-135 | health local e público pós-deploy |
| `scripts/backup/ativar_backup.sh` | 167-168 | espera do health após recreate |
| `scripts/smoke_staging.sh` | 26, 29, 32, 37 | smoke de staging |

**Por que importa.** É exatamente a classe de defeito que o incidente de
04/09/2026 expôs (backend aceita TCP e nunca responde; Nginx só devolve 504
após 120 s) e que foi corrigida em `monitor_health.sh`, `deploy_manual.sh:169`
e `post_deploy_check.sh:19-21`. A correção **não chegou** ao caminho que roda
sozinho a cada 5 minutos por timer systemd (`ejc-deploy-approved.timer`).
Efeito concreto: se o backend novo travar no boot, o laço de
`deploy_vps_safe.sh:253-260` não expira em 60 s como o log promete
("Backend não respondeu em 60s") — cada iteração fica pendurada, o rollback
automático não dispara, o mutex host-level permanece tomado e o serviço só
morre pelo `TimeoutStartSec=120min` do systemd, com produção quebrada nesse
intervalo.

**Correção mínima.** `--connect-timeout 5 --max-time 15` em todas as chamadas
acima (o valor de 15 s já é o adotado em `deploy_manual.sh:169`). Estender
`scripts/tests/test_deploy_rollback.sh` com um stub de `curl` que simula
resposta pendurada e afirmar que o script reprova dentro do teto.

### INF-02 — Logs de container sem rotação declarada

**Evidência.** Nenhum bloco `logging:` em `docker-compose.yml`,
`docker-compose.staging.yml`, `infra/woodpecker/docker-compose.yml` ou
`infra/monitoring/uptime-kuma/docker-compose.yml`. Nenhum script de
provisionamento (`scripts/vps_setup.sh`, `infra/selfhosted/bootstrap.sh`) grava
`/etc/docker/daemon.json`. Nenhum runbook menciona `log-opts`, `max-size` ou
`logrotate`.

**Por que importa.** O driver padrão `json-file` não limita tamanho. O backend
loga em `INFO` com uvicorn access log, o worker Celery em `INFO`, e a
reindexação do RAG (82 mil trechos em 27/08) gera volume proporcional. A VPS
hospeda seis sistemas; disco cheio em `/var/lib/docker` derruba o Postgres de
todos eles, não só do EJC. O incidente de 27/08 foi de memória; o próximo
candidato por omissão é disco.

**Correção mínima.** Por serviço no compose (não depende do host e não afeta
os outros sistemas):

```yaml
logging:
  driver: json-file
  options: { max-size: "50m", max-file: "5" }
```

Adicionar `df -h /var/lib/docker` e `docker system df` ao
`scripts/status_check.sh`. Confirmar na VPS o estado atual com
`docker info --format '{{.LoggingDriver}}'` e `du -sh /var/lib/docker/containers`.

### INF-03 — Scripts legados que contornam os gates permanecem executáveis

**Evidência.**

| Script | O que faz | Regra violada |
|---|---|---|
| `scripts/deploy.sh:21-31` | `docker compose build` + `up -d` + `alembic upgrade head` direto, sem backup, sem mutex | `CLAUDE.md` regra 9; `RUNBOOK_DEPLOY_MANUAL.md` ("nunca chame `deploy_vps_safe.sh` direto" — este nem o chama) |
| `scripts/deploy-vps.sh:71` | `docker compose up -d --build` | idem |
| `scripts/atualizar-vps.sh:48-58,68-86` | `pg_dump` **em claro** para `backups/*.sql.gz`, `git reset --hard origin/main` em `/opt/ejc`, `build --no-cache`, `up --force-recreate` | `RUNBOOK_BACKUP.md` ("artefato de backup em claro não é permitido"); `CLAUDE.md` regra 6 (`reset --hard`) |
| `scripts/vps_setup.sh:25-31` | `ufw --force reset` e regras só para 22/80/443 | VPS compartilhada com Verde Limp, S2, Evolution API, Woodpecker, Kuma: reexecutar apaga as regras dos outros sistemas; `:37-49` é interativo (`read -p`); `:72-76` aplica migration direto |

O `README.md` ainda descreve o fluxo antigo ("runner GitHub Actions próprio",
"aguardar todos os workflows obrigatórios", gates `pip-audit`/Prettier/
`npm audit` que não existem no `.woodpecker.yml`), o que aumenta a chance de um
operador escolher o script errado.

**Correção mínima.** Mover os quatro para `docs/arquivo/scripts-legados/` (a
mesma solução adotada para os workflows do Actions) **ou** inserir no topo de
cada um um guard que encerra com mensagem apontando `deploy_manual.sh`, salvo
`EJC_LEGACY_SCRIPT_OK=1`. Atualizar README §"Infraestrutura", §"Fluxo
obrigatório" e §"Gates automatizados" para o Woodpecker. O
`scripts/vps_setup.sh` merece reescrita como "adicionar regras" (`ufw allow`)
em vez de `reset`, com checagem de que o Nginx/certbot de outros domínios não
é sobrescrito.

### INF-04 — O destino offsite é a única cópia recuperável do backup, e é também pré-condição do deploy

**Evidência.** `backend/app/services/backup_service.py:486` gera os `.enc` em
`tempfile.TemporaryDirectory` e os descarta ao fim do ciclo; o volume
`backups_data` está montado (`docker-compose.yml:99`) mas o motor canônico não
persiste nele. `scripts/backup.sh:9-14` e `RUNBOOK_BACKUP.md` §"Estado
transitório" reconhecem isso e, por consequência, o gate pré-deploy exige
`offsite_ok=true` (`scripts/deploy_vps_safe.sh:172-181`). A Issue **#1236**
(aberta) registra o efeito: token rclone/OneDrive expirado reprovou o backup
pré-deploy 22 execuções seguidas e **bloqueou todo deploy**.

**Por que importa.** Dois riscos acoplados no mesmo ponto: (a) continuidade —
se o provedor offsite indisponibilizar ou a credencial expirar, não existe
cópia cifrada local para restaurar; (b) disponibilidade da esteira — a
mesma condição congela a publicação de correções, inclusive de segurança.
A Issue #1030 (fechada) resolveu a exclusão mútua, não a retenção local.

**Correção mínima.** Persistir os `.enc` do ciclo em `BACKUP_DIR` com rotação
por `BACKUP_RETENTION_DAYS` (variável já existe: `config.py:919`) antes do
upload; então relaxar o gate pré-deploy para "artefato cifrado local gerado
**e** (offsite OK **ou** offsite falhou com alerta)", mantendo
`BACKUP_OFFSITE_OBRIGATORIO` como a chave de política. Agendar
`scripts/backup/restore_drill.py` mensal e registrar a data do último drill
no `/admin/backup/status`. Fechar #1236 com renovação automática do token
(o `rclone.conf` já é montado gravável para isso, `docker-compose.yml:104-111`)
e alerta quando `offsite_ok=false` em dois ciclos seguidos.

---

## 4. Achados P2

### INF-05 — Redis sem autenticação alcançável pelo container do frontend

`redis` roda sem `requirepass` (`docker-compose.yml:36`) na rede `default`,
que o `frontend` também integra (serviço sem bloco `networks:`, `:191-206`).
Um comprometimento do Nginx do frontend dá acesso ao broker e ao result
backend do Celery: enfileirar tarefas registradas (indexação, IA, backup) e ler
resultados. O serializer JSON (`celery_app.py:40-42`) impede execução de
código arbitrário, mas não o abuso das tarefas legítimas. **Correção:**
`command: ["redis-server","--appendonly","yes","--requirepass","${REDIS_PASSWORD}"]`
e `REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0` no backend/worker;
alternativamente, rede `web` exclusiva frontend↔backend e `frontend` fora da
`default`. Efeito colateral a testar: `healthcheck` do Redis passa a precisar
de `-a`.

### INF-06 — PostgreSQL sem `shm_size` nem parâmetros de memória

`db` não declara `shm_size` (`docker-compose.yml:2-27`); o `/dev/shm` padrão do
Docker é 64 MB. Consultas paralelas e construção de índices `ivfflat`/`hnsw`
do pgvector podem falhar com "could not resize shared memory segment". O
container tem teto de 3 GB, mas o Postgres sobe com `shared_buffers=128MB`
default. **Correção:** `shm_size: 256m`; medir e então
`command: postgres -c shared_buffers=512MB -c effective_cache_size=2GB -c maintenance_work_mem=256MB`.
Não verificável daqui se o erro já ocorreu; `docker logs ejc_db | grep -i "shared memory"` responde.

### INF-07 — Redis com teto de container mas sem `maxmemory`; nenhum teto de CPU

Sem `--maxmemory`, o Redis cresce até o `mem_limit` de 512 MB e é morto por
OOM (perde o que a AOF não sincronizou) em vez de recusar escritas com erro
claro. **Correção:** `--maxmemory 400mb --maxmemory-policy noeviction`
(semântica correta para broker). Nenhum serviço do EJC declara `cpus:`; numa
VPS de seis sistemas, a reindexação do RAG pode monopolizar CPU mesmo contida
em memória. Sugestão inicial: `cpus: "2.0"` em backend e worker, ajustado após
medição.

### INF-08 — Divergências entre o Nginx do host e o do container

| Item | Host `nginx/ejc.conf` | Container `frontend/nginx.conf` | Efeito |
|---|---|---|---|
| `X-Frame-Options` | `SAMEORIGIN` (`:55`) | `DENY` (`:15`) | O host repassa o header do upstream **e** acrescenta o seu: a resposta sai com dois valores conflitantes. Padronizar em `DENY` (a CSP já tem `frame-ancestors 'none'`) ou usar `proxy_hide_header` no host. |
| `client_max_body_size` | `50m` (`:59`) | `60M` (`:83`) | Inofensivo em produção (o host manda), mas confunde diagnóstico. Alinhar a `MAX_UPLOAD_MB`. |
| `proxy_read_timeout` em `/api/` | `120s` (`:105`) | `300s` (`:84`) | Geração longa de peça ou análise de IA acima de 120 s recebe 504 do host. Os endpoints de streaming em `peca_geracao.py:350` e `bank_analysis.py:344` enviam `X-Accel-Buffering: no` (correto); os `StreamingResponse` de `legal_docs.py`, `raio_x.py`, `export.py` e `users.py` não — conferir se algum é SSE. |
| Rate limit de borda | ausente | ausente | O anti-brute-force do login é por processo e em memória (`entrypoint.sh:52-58`). Um `limit_req_zone` para `/api/auth/` no host é defesa em profundidade barata. |
| OCSP stapling | depende de `options-ssl-nginx.conf` do certbot | — | Conferir com `openssl s_client -status`. |

### INF-09 — Verificação pós-deploy ignora o certificado TLS

`scripts/post_deploy_check.sh:19` e `:44` usam `curl -k` contra
`https://ejc.depaulateixeira.adv.br`. Um certificado expirado ou de domínio
errado passa no gate. Não há monitor de validade de certificado configurado
(o README do Kuma apenas sugere). **Correção:** remover `-k`; criar monitor de
certificado no Uptime Kuma com aviso a 14 dias; acrescentar
`certbot renew --dry-run` ao runbook mensal.

### INF-10 — Passo fatal e sem teto de tempo dentro da transação de deploy

`scripts/deploy_vps_safe.sh:325`:
`docker compose exec -T backend python -m scripts.reparar_conhecimento_rag --batch-size 50`
roda **sem** `|| true`, sob o mutex, antes da troca do frontend e sem limite de
duração. Envolve embeddings e possivelmente provedores externos de IA. Uma
falha de rede com o provedor faz o rollback de um deploy cujo backend já foi
verificado saudável; uma execução longa estende a janela em que frontend
antigo e backend novo coexistem. **Correção:** tornar não fatal como os
seeds (`:305-320`), ou mover para tarefa Celery disparada após o
`post_deploy_check.sh`, com `timeout` explícito.

### INF-11 — Dois caminhos de deploy com paridade parcial

| | `scripts/deploy_manual.sh` | `infra/host-automation/ejc-deploy-approved.sh` |
|---|---|---|
| Checkout de origem | `/opt/ejc-deploy-src` (runbook) | `/opt/s2-automation/source/ejc` |
| Gate de vigência do RAG (`.rag_vigencia_activated_v1`) | sim (`:105-112`) | **não** |
| Marcador de versão | `.deployed_sha` | `.deployed_sha` **e** `.deploy_last_sha` (`:137`) |
| Teste de paridade | `test_deploy_manual_paridade.py` (contra o YAML aposentado) | `test_gate.sh` cobre só `woodpecker-approved-sha.sh` |

O caminho automático é o que roda a cada 5 minutos e é o que **não** tem o
gate de vigência. **Correção:** extrair pré-voo e classificação de migration
para `scripts/lib/deploy_preflight.sh` consumido pelos dois; apontar o teste
de paridade para os dois scripts vivos em vez do YAML arquivado; consolidar
um único checkout de origem e um único marcador.

### INF-12 — Retenção de backup com três valores distintos

`BACKUP_RETENCAO_DIAS`: 30 (`.env.example:796`, `config.py:942`), 14
(`scripts/backup/ativar_backup.sh:54`), e `BACKUP_RETENTION_DAYS=7`
(`config.py:919`, `.env.example:819`) para um "backup legado local (job
02h00)" que o `Dockerfile:24-27` ainda descreve como existente. A decisão
registrada é 30 dias (`decisoes-bloco0-2026-08-08.md`). **Correção:** um único
default em `config.py`, `ativar_backup.sh` lendo dele, e remoção ou
documentação clara da variável legada.

### INF-13 — Observabilidade do host

Sentry (opt-in por DSN) e o watchdog cobrem a aplicação; o Uptime Kuma roda
**na mesma VPS** e não vê queda total (o README admite). Não há alerta de
disco, memória ou swap do host — o incidente de 27/08 foi detectado por um
humano olhando `free`. O `monitor_health.sh` registra restarts só em arquivo
local. **Correção mínima sem nova stack:** monitor externo (UptimeRobot, já
documentado) em `/api/health`; cron de 5 min que envia `df`/`free` a um
monitor "push" do Kuma quando ultrapassar limiar; notificação do Kuma por
canal externo (e-mail/WhatsApp); heartbeat do backup diário como monitor
push (o scheduler já produz resultado por ciclo, `scheduler.py:1272-1315`).

---

## 5. Achados P3

### INF-14 — Imagens e hardening de container

- `backend/Dockerfile:34` mantém `build-essential` na imagem final (imagem
  única, sem estágio de build) — superfície e tamanho maiores.
- Container do backend roda como **root** com o `rclone.conf` do root do host
  montado **gravável** (`docker-compose.yml:104-111`) e
  `--forwarded-allow-ips '*'` (`entrypoint.sh:85-86`). Cada item está
  documentado e justificado; o conjunto (processo exposto à internet, root,
  token OAuth do host) é o risco residual mais alto do compose. Rastreado em
  **#1192**. Mitigação sem código: `RCLONE_CONFIG_DIR` apontando para um
  diretório com **apenas** o remote do backup, não o `~/.config/rclone` do root.
- Nenhum serviço do EJC usa `security_opt: [no-new-privileges:true]`,
  `cap_drop` ou `read_only` (o Kuma usa).
- Frontend em `nginx:1.27-alpine` como root do container; alternativa
  `nginxinc/nginx-unprivileged`.
- Tags flutuantes sem digest: `pgvector/pgvector:pg16`, `redis:7-alpine`,
  `python:3.11-slim`, `node:22.22-slim`, `nginx:1.27-alpine`. O Renovate cobre
  atualização; pin por digest é opcional, mas `pg16` sem minor significa que um
  `pull` pode trocar a versão do Postgres sem PR.
- O Trivy do CI varre o **filesystem** (`.woodpecker.yml:71`), não as imagens
  construídas: CVEs do sistema base (`python:3.11-slim`, `nginx:alpine`) não
  são cobertas. Acrescentar `trivy image` sobre `ejc-backend`/`ejc-frontend`,
  inicialmente não bloqueante.

### INF-15 — `docker-compose.override.yml` versionado

O override está rastreado no Git com conteúdo igual ao `.example` mais uma
duplicação de `ports` do backend (`docker-compose.override.yml:8-9`). Por ser
carregado automaticamente por qualquer `docker compose up`, cria `./secrets`
vazio (dono root) em toda máquina de desenvolvimento e torna o `.example`
redundante. Decidir: ou o override é ambiente-específico (destravar e ignorar)
ou é padrão (apagar o `.example` e a duplicação).

### INF-16 — Documentação e metadados desatualizados

- `README.md`: "runner GitHub Actions próprio"; gates `pip-audit`, Prettier,
  ESLint, `npm audit` (não estão no Woodpecker; `npm run lint` é só `tsc`,
  `frontend/package.json:10`); "Node.js 20" (Dockerfile e `CLAUDE.md` exigem
  22.22).
- `.github/CODEOWNERS:10-11` referencia `/.github/workflows/` e `/deploy/`,
  inexistentes.
- `.github/pull_request_template.md` §"Evidências de CI" ainda pede "P0
  Guard" e "CI completo aprovado" (checks do Actions).
- `.env.example` com 315 variáveis e 59 KB: contrato de provisionamento
  difícil de auditar; `scripts/migrar_env_obsoletos.sh` existe, mas não há
  inventário do que é vivo.
- `RUNBOOK_MONITORAMENTO.md` não cita o Uptime Kuma nem o
  `monitor_health.sh`.

### INF-17 — CI Woodpecker: lacunas menores

ESLint e Prettier prometidos no README não rodam (`.woodpecker.yml:47-54`);
`security-misconfig-audit` é não bloqueante por decisão registrada; o agente
monta `docker.sock` do host de produção (inerente ao backend Docker,
mitigado por aprovação de forks, `MAX_WORKFLOWS=1` e limites de recurso).
Nenhuma ação obrigatória; registrar a decisão sobre ESLint/Prettier.

### INF-18 — Credencial de acesso à VPS

O repositório está limpo, mas o acesso operacional documentado é `root` por
**senha** (`vps-tools/.env.example`, `set-vps-password.ps1`). O relatório
`RELATORIO_FASE0_CONTENCAO_2026-06-29.md:64` já recomendava chave SSH e
`PasswordAuthentication no`; não há evidência de que foi aplicado. Além disso,
essa senha foi transmitida em texto claro num canal de chat durante esta
rodada, o que a caracteriza como **exposta** independentemente do canal:
rotacionar imediatamente, migrar para chave SSH com passphrase, desabilitar
login por senha e root direto (`PermitRootLogin prohibit-password`), e
instalar `fail2ban`/`sshguard`. Ver §6 para os comandos de verificação.

---

## 6. Não verificável nesta rodada — checklist para o titular executar na VPS

Cada linha fecha uma lacuna desta auditoria. Nenhum comando altera estado.

```bash
# INF-02 — rotação de logs
docker info --format '{{.LoggingDriver}}'; cat /etc/docker/daemon.json 2>/dev/null
du -sh /var/lib/docker/containers; df -h / /var/lib/docker

# INF-06 — shm do Postgres
docker logs ejc_db 2>&1 | grep -ci "shared memory"
docker exec ejc_db df -h /dev/shm

# INF-08 — headers duplicados e TLS
curl -sI https://ejc.depaulateixeira.adv.br/ | grep -i x-frame-options
openssl s_client -connect ejc.depaulateixeira.adv.br:443 -status </dev/null 2>/dev/null | grep -A2 "OCSP Response Status"
certbot certificates

# INF-04 — estado do backup e do offsite
curl -s -H "Authorization: Bearer <token-admin>" http://127.0.0.1:8000/api/admin/backup/status
ls -la /var/lib/docker/volumes/ejc_backups_data/_data/

# INF-11 — qual caminho de deploy está ativo
systemctl list-timers | grep -E "ejc|s2"; cat /opt/ejc/.deployed_sha /opt/ejc/.deploy_last_sha 2>/dev/null

# INF-18 — SSH
grep -E "^(PasswordAuthentication|PermitRootLogin)" /etc/ssh/sshd_config /etc/ssh/sshd_config.d/* 2>/dev/null
systemctl is-active fail2ban sshguard 2>/dev/null
ufw status numbered
```

---

## 7. Artefatos examinados

`docker-compose.yml`, `docker-compose.override.yml`,
`docker-compose.override.example.yml`, `docker-compose.staging.yml`,
`backend/Dockerfile`, `backend/entrypoint.sh`, `frontend/Dockerfile`,
`frontend/nginx.conf`, `nginx/ejc.conf`, `.dockerignore`, `.gitignore`,
`.gitleaksignore`, `.semgrepignore`, `.woodpecker.yml`, `renovate.json`,
`.github/CODEOWNERS`, `.github/pull_request_template.md`, `.githooks/pre-push`,
`infra/woodpecker/*`, `infra/host-automation/*` (scripts, systemd, testes),
`infra/monitoring/uptime-kuma/*`, `infra/renovate/*`,
`infra/selfhosted/bootstrap.sh`, `scripts/deploy_manual.sh`,
`scripts/deploy_vps_safe.sh`, `scripts/deploy.sh`, `scripts/deploy-vps.sh`,
`scripts/atualizar-vps.sh`, `scripts/vps_setup.sh`, `scripts/monitor_health.sh`,
`scripts/post_deploy_check.sh`, `scripts/backup.sh`,
`scripts/backup/ativar_backup.sh`, `scripts/smoke_staging.sh`,
`scripts/reanimar_ejc.sh` (parcial), `vps-tools/*`, `.env.example`,
`frontend/.env.example`, `backend/app/core/config.py` (blocos de ambiente,
CORS, backup, Redis), `backend/app/main.py` (middlewares, health,
`FORWARDED_ALLOW_IPS`), `backend/app/core/celery_app.py`,
`backend/app/services/backup_service.py:486`,
`backend/app/services/scheduler.py:1272-1315`, `backend/app/routers/auth.py:84-86`,
`backend/tests/test_deploy_manual_paridade.py`, `README.md`,
`RUNBOOK_DEPLOY_MANUAL.md`, `RUNBOOK_BACKUP.md`, `RUNBOOK_MONITORAMENTO.md`,
`RUNBOOK_ROTINA_BACKUP_DIARIA_GDRIVE.md` (§1-2), `docs/seguranca/SAST_BASELINE.md`,
`docs/auditoria/relatorios/2026-08-27-verificacao-e-novos-achados.md`,
`docs/PLANO_MESTRE_STATUS.md` (linhas AUD27-P1-3/4), Issues #1030, #1192, #1236.

## 8. Ordem sugerida de execução

1. INF-18 (rotação da credencial) — imediato, fora do repositório.
2. INF-01 + INF-02 — um PR de infra, sem migration, com teste de shell.
3. INF-03 + INF-16 — um PR docs/scripts (arquivar legados, corrigir README,
   CODEOWNERS, template de PR).
4. INF-04 + INF-12 — PR de backend (retenção local cifrada) e fechamento de
   #1236.
5. INF-05, INF-06, INF-07 — um PR de compose, validado em staging
   (`docker-compose.staging.yml`) antes de produção.
6. INF-08, INF-09, INF-10, INF-11 — PRs pequenos e independentes.
7. INF-13, INF-14, INF-15, INF-17 — backlog.
