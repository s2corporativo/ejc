Vou consolidar o runbook a partir das quatro seções verificadas. Como a tarefa é puramente de redação (consolidar JSON em Markdown coeso), produzo o documento diretamente.

# Runbook de Deploy — EJC Fases 1-3

> Produção: VPS Contabo · Docker Compose · `APP_DIR=/opt/ejc` · Domínio `ejc.depaulateixeira.adv.br`
> Modo de entrega: upload SFTP via `vps-tools` (o repositório local **não** é git). Comandos remotos via `node vps-tools/run.js`.

---

## TOP 3 RISCOS — LEIA ANTES DE COMEÇAR

1. **Imagem de produção NÃO contém `alembic/`.** A imagem atual foi construída com um Dockerfile antigo que não copiava `alembic/`, `alembic.ini` nem `seeds/`. Por isso o Alembic está **inoperante** lá dentro. Nenhum comando `alembic stamp/upgrade` funciona até o **rebuild** do backend com o Dockerfile novo. Um `docker restart` ou `sync.js` arquivo-a-arquivo **não** resolve — é obrigatório `docker compose build backend`.

2. **Nome do container e estado do `alembic_version` são incertos — VERIFIQUE na VPS.** O `docker-compose.yml` não define `container_name`. Os scripts assumem `ejc_backend`/`ejc_db`/`ejc_frontend`, mas relatórios citam `ejc_postgres`. Comandos `docker compose exec <serviço>` (db/backend) são imunes; comandos `docker exec <nome>` dependem do nome real. **Rode `docker ps` antes** (Passo 1.1). Da mesma forma, o `version_num` em `alembic_version` define se haverá `stamp` ou não — **consulte antes de agir** (Passo 4).

3. **Código da Fase 3B e a migration 051 têm de subir juntos.** O código RAG (`ai_service.py`, `routers/rag.py`, `teses.py`) já referencia `kd.client_id`/`d.client_id`. Se o backend liberar tráfego **antes** da 051 estar aplicada, `GET /api/rag/buscar` (ramo semântico, sem try/except) lança **HTTP 500 (UndefinedColumn)** quando `EMBEDDINGS_ENABLED` está ligado; nas buscas via `ai_service` o try/except degrada para resultado vazio (perda de isolamento/contexto). **Aplique a 051 ANTES de liberar tráfego ao RAG.**

---

## 0. Contexto e avisos

- O banco de **produção já tem o schema** (tabelas das Fases 1-2 já existem historicamente). A 051 só adiciona colunas/índices e faz backfill.
- **Senha root NÃO será trocada** (decisão do usuário). Nenhum comando deste runbook depende ou altera credenciais de banco/root. Risco residual aceito e documentado.
- **Tudo é idempotente / sem destruição.** A 051 faz apenas `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS` e dois `UPDATE ... WHERE ... IS NULL` (backfill). **Nenhum DROP, nenhum DELETE.** Reexecutar é seguro. As migrations 048/049/050 não rodam (apenas `stamp`).
- **Janela de manutenção recomendada.** Embora as operações sejam seguras, o backfill faz `UPDATE` em banco populado e há uma janela entre subir o backend e aplicar a 051. Faça em horário de baixo tráfego.
- **Atenção ao `monitor_health.sh` (cron):** ele reinicia `ejc_backend`/`ejc_frontend` se o health local cair, podendo **mascarar** uma falha de deploy. Monitore `/var/log/ejc_health_monitor.log` durante a janela.
- **`deploy_vps_safe.sh` só migra com `RUN_MIGRATIONS=1`** (default `0` = não migra). Faremos o `stamp`+`upgrade` manualmente e deliberadamente.

---

## 1. Pré-requisitos (ambiente / credenciais)

### 1.1. Credenciais locais — `vps-tools/.env` (NÃO versionar)
Sem este arquivo, todo `run.js`/`upload.js`/`sync.js` aborta. Crie localmente `C:\Users\User\EJC\vps-tools\.env` com:
- `VPS_HOST`
- `VPS_USER` (default `root` se ausente)
- `VPS_PASSWORD` (a senha root atual — **não será trocada**; basta replicar a já em uso)
- `VPS_PORT` (default `22`)

### 1.2. `.env` de PRODUÇÃO (`/opt/ejc/.env`) — chaves obrigatórias
Com `APP_ENV=production`, o validador do Pydantic **bloqueia o boot** se faltarem. Confira (sem expor valores):
- `SECRET_KEY` — obrigatória; falha se vazia ou se começar com `TROCAR`. Gerar com:
  `python3 -c "import secrets; print(secrets.token_urlsafe(64))"` (gerar local, colar no `.env`, não versionar).
- `FRONTEND_URL` — obrigatória; falha se contiver `SEU_DOMINIO`.
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` — usadas pelo compose para montar `db` e as `DATABASE_URL*`.
- `GROQ_API_KEY` — necessária para IA/RAG responderem.
- `ADMIN_EMAIL` / `ADMIN_PASSWORD` (opcional `ADMIN_NAME`) — lidas pelo seed. Sem senha, o seed gera uma aleatória e a imprime uma vez.

Opcionais (default seguro/desligado): `CORS_ORIGINS`, `GROQ_MODEL`, `EMBEDDINGS_ENABLED`, `DATAJUD_API_KEY`, `SMTP_*`/`EMAIL_ENABLED`, `ZAPI_*`/`WHATSAPP_ENABLED`, `VAPID_*`/`PUSH_ENABLED`, `SENTRY_DSN`, `BACKUP_REMOTE`, `OLLAMA_*`, `AI_PROVIDER`.

> Nota: o isolamento RAG (`_FILTRO_ESCOPO_RAG`, que usa `kd.client_id`) é injetado **tanto na busca semântica quanto na textual**. O impacto da 051 **não depende** de `EMBEDDINGS_ENABLED`.

### 1.3. Endpoint de health
O backend expõe **os dois**: `/health` (usado pelo healthcheck do Docker) e `/api/health` (usado pelos scripts e nginx). Retorna `{"status":"ok"|"degraded","version":"3.0.0","database":true/false}`.

---

## 2. Pré-flight (backup + ponto de rollback + checar .env)

Modo somente-leitura, exceto o backup. Execute de `C:\Users\User\EJC`.

**2.1. Confirmar nomes e portas reais dos containers** (resolve a incerteza de nome):
```
node vps-tools/run.js "docker ps --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'"
```
> Anote os nomes reais do Postgres e do backend. Onde este runbook usa `ejc_db`/`ejc_backend` em `docker exec`, substitua pelo nome real se divergir. Os comandos `docker compose exec <serviço>` são robustos e não dependem disso.

**2.2. Confirmar que o `.env` de produção existe:**
```
node vps-tools/run.js "test -f /opt/ejc/.env && echo ENV_OK || echo ENV_FALTANDO"
```

**2.3. Anotar ponto de rollback (código + imagens):**
```
node vps-tools/run.js "cd /opt/ejc && git rev-parse HEAD"   # pode falhar se /opt/ejc nao for git; tudo bem
node vps-tools/run.js "docker inspect -f '{{.Image}}' ejc_backend; docker inspect -f '{{.Image}}' ejc_frontend"
```
> Guarde os IDs de imagem como `OLD_BACKEND_IMAGE` e `OLD_FRONTEND_IMAGE`. Necessários no rollback manual (seção 6).

**2.4. Backup OBRIGATÓRIO do banco (antes de qualquer toque):**
```
node vps-tools/run.js "cd /opt/ejc && bash scripts/backup.sh"
node vps-tools/run.js "ls -lh /opt/ejc/backups/ | tail -3"
```
> Confirme que o `.sql.gz` foi gerado com tamanho > 0 e **anote o nome exato** (será necessário no rollback 6c). O backup é `pg_dump | gzip` (plain comprimido) — ver aviso de incompatibilidade no rollback.

**2.5. VERIFICAR o estado do Alembic (CRÍTICO — define o caminho da migration):**
```
node vps-tools/run.js "docker exec ejc_db psql -U ejc_user -d ejc_db -tAc \"SELECT to_regclass('public.alembic_version')\""
node vps-tools/run.js "docker exec ejc_db psql -U ejc_user -d ejc_db -tAc \"SELECT version_num FROM alembic_version\""
```
Interprete (decide a seção 4):
- **Tabela ausente** OU `version_num` ≠ `050`/`051` → cenário (a): fará `stamp 050_novos_modulos` antes do upgrade.
- `version_num` = `050_novos_modulos` → cenário (b): só `upgrade head`.
- `version_num` = `051_rag_isolation` → cenário (c): nada a migrar.

**2.6. Validar o compose:**
```
node vps-tools/run.js "cd /opt/ejc && docker compose config >/dev/null && echo COMPOSE_OK"
```

---

## 3. Entrega do código + rebuild das imagens

O EJC local **não é git** — a entrega é por upload SFTP. O `sync.js` só alcança `backend/app` e `frontend/src`; os arquivos NOVOS fora de `app/` (Dockerfile, `alembic/`, `alembic.ini`, `seeds/`) precisam de `upload.js`.

**3.1. Enviar arquivos/pastas NOVOS do backend (fora de `app/`):**
```
node vps-tools/upload.js /opt/ejc/backend/Dockerfile C:\Users\User\EJC\backend\Dockerfile
node vps-tools/upload.js /opt/ejc/backend/alembic.ini C:\Users\User\EJC\backend\alembic.ini
node vps-tools/upload.js /opt/ejc/backend/alembic/env.py C:\Users\User\EJC\backend\alembic\env.py
node vps-tools/upload.js /opt/ejc/backend/alembic/script.py.mako C:\Users\User\EJC\backend\alembic\script.py.mako
node vps-tools/upload.js /opt/ejc/backend/alembic/versions/048_processes.py C:\Users\User\EJC\backend\alembic\versions\048_processes.py
node vps-tools/upload.js /opt/ejc/backend/alembic/versions/049_totp_2fa.py C:\Users\User\EJC\backend\alembic\versions\049_totp_2fa.py
node vps-tools/upload.js /opt/ejc/backend/alembic/versions/050_novos_modulos.py C:\Users\User\EJC\backend\alembic\versions\050_novos_modulos.py
node vps-tools/upload.js /opt/ejc/backend/alembic/versions/051_rag_isolation.py C:\Users\User\EJC\backend\alembic\versions\051_rag_isolation.py
node vps-tools/upload.js /opt/ejc/backend/seeds/seed_all.py C:\Users\User\EJC\backend\seeds\seed_all.py
```

**3.2. Enviar arquivos alterados do backend (`app/`, sem restart):**
```
node vps-tools/sync.js backend routers/documents.py --no-restart
node vps-tools/sync.js backend routers/legal_docs.py --no-restart
node vps-tools/sync.js backend routers/ramos.py --no-restart
node vps-tools/sync.js backend routers/rag.py --no-restart
node vps-tools/sync.js backend routers/teses.py --no-restart
node vps-tools/sync.js backend services/ai_service.py --no-restart
node vps-tools/sync.js backend services/ingestion_service.py --no-restart
node vps-tools/sync.js backend services/case_intel.py --no-restart
node vps-tools/sync.js backend models/rag.py --no-restart
```

**3.3. Enviar arquivos alterados do frontend (`src/`, sem rebuild ainda):**
```
node vps-tools/sync.js frontend lib/api.ts --no-restart
node vps-tools/sync.js frontend pages/RecuperarSenha.tsx --no-restart
node vps-tools/sync.js frontend pages/RedefinirSenha.tsx --no-restart
node vps-tools/sync.js frontend components/PecaGeneratorModal.tsx --no-restart
```

**3.4. Remover órfãos do frontend na VPS (DUPLA CONFIRMAÇÃO antes de apagar):**
O frontend é multi-stage (Vite build → Nginx); órfãos deixados em `src/` podem ser reincluídos no `npm run build`. Primeiro liste, confirme cada caminho, só então remova:
```
node vps-tools/run.js "ls -la /opt/ejc/frontend/src/pages/Login.tsx /opt/ejc/frontend/src/components/DashboardModernLuxury.tsx"
```
> Só apague após confirmar visualmente cada caminho (regra de dupla confirmação de exclusão). A lista completa de órfãos está em `_QUARENTENA/frontend_orfaos/`.

**3.5. Rebuild da imagem do backend (passo que torna o Alembic operável):**
```
node vps-tools/run.js "cd /opt/ejc && docker compose build backend"
```

> O build do frontend fica para a seção 5 (após a 051 aplicada), para não liberar a UI antes do schema.

---

## 4. Migration do banco (sequência condicional segura)

Cadeia: `048_processes (down_revision=None) → 049_totp_2fa → 050_novos_modulos → 051_rag_isolation (head)`.
A 051 é a **única** com DDL real a rodar; 048/049/050 são apenas marcadas via `stamp`.

**4.1. Subir o backend novo SEM liberar tráfego RAG e aguardar health:**
```
node vps-tools/run.js "cd /opt/ejc && docker compose up -d --no-deps backend && sleep 10 && curl -fsS http://127.0.0.1:8000/api/health"
```

**4.2. Aplicar conforme o cenário detectado em 2.5:**

**Cenário (a) — tabela ausente OU `version_num` ≠ 050/051** (mais provável, pois o Alembic estava inoperante):
```
node vps-tools/run.js "cd /opt/ejc && docker compose exec -T backend alembic stamp 050_novos_modulos"
node vps-tools/run.js "cd /opt/ejc && docker compose exec -T backend alembic upgrade head"
```
> O `stamp 050` grava `050_novos_modulos` em `alembic_version` **sem executar** 048/049/050 (cujo schema já existe). O `upgrade head` roda **somente a 051**.

**Cenário (b) — `version_num` = `050_novos_modulos`:** NÃO faça stamp. Só:
```
node vps-tools/run.js "cd /opt/ejc && docker compose exec -T backend alembic upgrade head"
```

**Cenário (c) — `version_num` = `051_rag_isolation`:** nada a fazer, já está no head.

> **Por que NÃO rodar `alembic upgrade head` cru sem stamp:** o baseline 048 chama `create_all(checkfirst=True)` + reflection de todas as tabelas — é idempotente, porém lento e **poluiria o histórico**, marcando 048-050 como aplicados agora e mascarando que o schema é pré-existente. Pior: se houver um `version_num` órfão (revisão inexistente nos arquivos), o `upgrade` falha com "Can't locate revision". O `stamp 050` é a rota limpa.

**4.3. Confirmar que o head foi atingido:**
```
node vps-tools/run.js "cd /opt/ejc && docker compose exec -T backend alembic current"
```
Esperado: `051_rag_isolation (head)`.

**4.4. Conferir colunas/índices da 051 (read-only):**
```
node vps-tools/run.js "docker exec ejc_db psql -U ejc_user -d ejc_db -c \"\\d+ knowledge_docs\""
```
Esperado: colunas `client_id` e `case_id` + índices `ix_knowledge_docs_client_id`/`ix_knowledge_docs_case_id`.

> Nota sobre o backfill: docs antigos sem `extra->>'case_id'` e sem JOIN com `cases` ficam com `client_id`/`case_id` NULL (tratados como conteúdo global). Valide se isso é aceitável para o isolamento pretendido.

**4.5. Seed idempotente (opcional; só cria admin se ausente):**
```
node vps-tools/run.js "cd /opt/ejc && docker compose exec -T backend python seeds/seed_all.py"
```

---

## 5. Subir e validar (health + smoke das Fases 1-3)

**5.1. Build + subir o frontend (rebuild de container é obrigatório):**
```
node vps-tools/run.js "cd /opt/ejc && docker compose build frontend && docker compose up -d --no-deps frontend"
```

**5.2. Health checks:**
```
# Containers de pe
node vps-tools/run.js "docker ps --format '{{.Names}} {{.Status}}' | grep -E '^ejc_(backend|db|frontend) '"
# API local (esperado: 200, status:ok, database:true)
node vps-tools/run.js "curl -fsS http://127.0.0.1:8000/api/health"
# Externo via nginx/HTTPS (esperado: 200 em ambos)
node vps-tools/run.js "curl -k -sS -o /dev/null -w '%{http_code}\n' https://ejc.depaulateixeira.adv.br/api/health"
node vps-tools/run.js "curl -k -sS -o /dev/null -w '%{http_code}\n' https://ejc.depaulateixeira.adv.br/"
# Check completo automatizado
node vps-tools/run.js "cd /opt/ejc && EJC_DOMAIN=ejc.depaulateixeira.adv.br bash scripts/post_deploy_check.sh"
```
> **Falso-negativo conhecido:** o `post_deploy_check.sh` checa o frontend local em `127.0.0.1:8080`, mas o compose publica `80:80`. Se SÓ essa linha falhar e o `https://.../` (acima) der 200, é divergência de porta — **não** é regressão. Confirme a porta real com o `docker ps` do Passo 2.1.

**5.3. Smoke test funcional das Fases 1-3** (use credenciais reais de um usuário de teste; substitua os placeholders):
```
# S1 — Login (guardar access_token e refresh_token da resposta)
node vps-tools/run.js "curl -k -sS -X POST https://ejc.depaulateixeira.adv.br/api/auth/login -H 'Content-Type: application/json' -d '{\"email\":\"USUARIO@dominio\",\"password\":\"SENHA\"}'"
# S2 — Refresh (rotacao: o antigo e revogado)
node vps-tools/run.js "curl -k -sS -X POST https://ejc.depaulateixeira.adv.br/api/auth/refresh -H 'Content-Type: application/json' -d '{\"refresh_token\":\"<REFRESH_TOKEN>\"}'"
# S3 — Recuperar senha (esperado 200 com resposta neutra; rate limit 3/hora)
node vps-tools/run.js "curl -k -sS -X POST https://ejc.depaulateixeira.adv.br/api/auth/recuperar-senha -H 'Content-Type: application/json' -d '{\"email\":\"USUARIO@dominio\"}'"
# S4 — Gerar peca (SSE: eventos 'step' e 'concluido'; descricao_fatos >=50 chars, pedidos >=10)
node vps-tools/run.js "curl -k -sS -N -X POST https://ejc.depaulateixeira.adv.br/api/pecas/gerar -H 'Authorization: Bearer <ACCESS_TOKEN>' -H 'Content-Type: application/json' -d '{\"tipo_peca\":\"peticao_inicial\",\"area_direito\":\"civel\",\"descricao_fatos\":\"Caso de teste de fumaca apos deploy para validar o pipeline de geracao de pecas.\",\"pedidos\":\"Procedencia do pedido.\"}' | head -c 400"
# S5 — Busca RAG (valida isolamento Fase 3: fail-closed; sem pecas de outros clientes)
node vps-tools/run.js "curl -k -sS 'https://ejc.depaulateixeira.adv.br/api/rag/buscar?q=prescricao&limite=3' -H 'Authorization: Bearer <ACCESS_TOKEN>'"
```
Esperado em S5: 200 com `"modo":"semantica"` (se embeddings ativos) ou `"textual"`, e `resultados` sem peças/precedentes internos de outros clientes. **Se S5 retornar 500 por `UndefinedColumn`, a 051 não foi aplicada — volte à seção 4.**

---

## 6. Rollback (se algo falhar)

### 6a. Reverter código/imagens (deploy ruim, schema preservado — PREFERIR)
Use os valores anotados em 2.3:
```
node vps-tools/run.js "docker tag <OLD_BACKEND_IMAGE> ejc-backend:latest && docker tag <OLD_FRONTEND_IMAGE> ejc-frontend:latest && cd /opt/ejc && docker compose up -d --no-deps backend frontend"
```
Depois revalide com a seção 5.2.

### 6b. Reverter SOMENTE a migration 051 (downgrade seguro, mas destrói isolamento)
O downgrade da 051 existe e dropa os índices e as colunas `case_id`/`client_id`:
```
node vps-tools/run.js "cd /opt/ejc && docker compose exec -T backend alembic downgrade 050_novos_modulos"
```
> **ATENÇÃO:** isso **apaga** `client_id`/`case_id` e o backfill de isolamento (LGPD/EOAB). Só reverta se o problema for **especificamente** a 051; caso contrário prefira 6a (mantém schema). **Nunca** tente `downgrade base` — o baseline 048 lança `NotImplementedError` e reverter abaixo de 050 não é suportado.

### 6c. Restaurar o banco a partir do dump (último recurso)
**INCOMPATIBILIDADE conhecida:** `backup.sh` gera `*.sql.gz` (plain comprimido), mas `restore.sh` usa `pg_restore`, que exige formato custom `*.dump`. **NÃO use `restore.sh`** com o backup do pipeline. Restaure assim (parando o backend para evitar escrita concorrente):
```
node vps-tools/run.js "docker stop ejc_backend"
node vps-tools/run.js "gunzip -c /opt/ejc/backups/ejc_db_<DATA>.sql.gz | docker exec -i ejc_db psql -U ejc_user -d ejc_db"
node vps-tools/run.js "docker start ejc_backend"
```

### 6d. Auto-recuperação existente
`monitor_health.sh` (cron) reinicia `ejc_backend`/`ejc_frontend` se o health cair — pode **mascarar** falhas durante o deploy. Observe `/var/log/ejc_health_monitor.log` na janela.

---

## 7. Checklist final

- [ ] `vps-tools/.env` local presente (host/user/password/port) — não versionado.
- [ ] `/opt/ejc/.env` confirmado (`ENV_OK`): `SECRET_KEY` válida, `FRONTEND_URL` sem placeholder, `POSTGRES_*`, `GROQ_API_KEY`.
- [ ] Nomes reais de container confirmados via `docker ps` (Postgres/backend/frontend).
- [ ] Backup gerado e validado (`.sql.gz` > 0); nome do arquivo anotado.
- [ ] `OLD_BACKEND_IMAGE` / `OLD_FRONTEND_IMAGE` anotados.
- [ ] Estado do `alembic_version` verificado → cenário (a/b/c) decidido.
- [ ] `docker compose config` OK.
- [ ] Arquivos NOVOS (Dockerfile, `alembic/`, `alembic.ini`, `seeds/`) enviados.
- [ ] Arquivos alterados de `backend/app` e `frontend/src` enviados.
- [ ] Órfãos do frontend removidos da VPS (com dupla confirmação de cada caminho).
- [ ] `docker compose build backend` concluído (Alembic agora na imagem).
- [ ] Backend novo no ar e `/api/health` = 200.
- [ ] `stamp 050` (se cenário a) → `upgrade head` → `alembic current` = `051_rag_isolation (head)`.
- [ ] Colunas `client_id`/`case_id` + índices presentes em `knowledge_docs`.
- [ ] Seed idempotente rodado (se aplicável).
- [ ] `docker compose build frontend` + `up -d frontend` concluídos.
- [ ] Health local + externo (HTTPS) = 200; `post_deploy_check.sh` OK (ignorando o falso-negativo da porta 8080).
- [ ] Smoke S1-S5 passou; S5 (RAG) sem 500 e sem vazamento entre clientes.
- [ ] `monitor_health.sh` observado durante a janela (sem reinícios mascarando falhas).

---

## O que depende de informação que só está na VPS (seja honesto)

- **Nome real dos containers** (`ejc_db` vs `ejc_postgres`, etc.) — só `docker ps` (2.1) confirma. Comandos `docker exec <nome>` falham se o nome divergir.
- **Estado do `alembic_version`** — só a consulta em 2.5 decide entre stamp ou não. Não assuma.
- **Porta publicada do frontend** (80 vs 8080) — afeta a interpretação do `post_deploy_check.sh`.
- **Se `/opt/ejc` é git** — `git rev-parse HEAD` pode falhar; nesse caso o rollback de código depende exclusivamente das imagens antigas (6a).
- **Conteúdo atual do `/opt/ejc/.env`** — só a verificação remota confirma se as chaves obrigatórias estão presentes e válidas.

Arquivos de referência locais: `C:\Users\User\EJC\backend\Dockerfile`, `C:\Users\User\EJC\backend\alembic\versions\051_rag_isolation.py`, `C:\Users\User\EJC\scripts\backup.sh`, `C:\Users\User\EJC\scripts\deploy_vps_safe.sh`, `C:\Users\User\EJC\scripts\post_deploy_check.sh`, `C:\Users\User\EJC\vps-tools\ssh-config.js`.