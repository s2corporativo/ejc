# Notas de execução — Módulo 02 (Infraestrutura, Docker e Health)

## Ambiente local montado (sandbox Manus)
- PostgreSQL 16.14 + pgvector 0.6.0 + pg_trgm — serviço local porta 5432
- Redis 7 — porta 6379 (PONG)
- Usuário/banco: ejc/ejc, database ejc, extensões vector e pg_trgm criadas
- Python 3.12 + dependências backend instaladas (requirements.txt OK)
- .env local gerado por scripts/inventory/prep_local_env.py (Fernet reais,
  POSTGRES_USER/PASSWORD/DB=ejc/ejc/ejc, DATABASE_URL/DATABASE_URL_SYNC/
  SCHEMA_CHECK_DATABASE_URL apontando para localhost:5432/ejc,
  APP_ENV=development, AI_ENABLED=false, PII_ENCRYPTION_KEY + VAULT_MASTER_KEYS Fernet)
- Loader: scripts/inventory/env_shell.sh (exporta .env linha a linha e executa)

## Observações técnicas do .env do repositório
- .env.example NÃO declara DATABASE_URL/DATABASE_URL_SYNC: são compostos no
  docker-compose.yml a partir de POSTGRES_USER/PASSWORD/DB. O Settings
  (pydantic-settings) tem env_file=".env" como string (v2 exige Path; sem
  efeito), então o app depende das env vars exportadas — padrão Docker.
- Loader local adiciona os compostos ao final do .env local.

## Achado de migration (corrigível — baseline continua)
- `alembic upgrade head` trava na migration 143:
  "value too long for type character varying(32)" em alembic_version (revision
  id 143 tem 35 chars). A migration 144 (widening varchar(32)->128) foi criada
  DEPOIS da 143 na cadeia (down_revision="143..."), então em instalações novas
  a 143 roda antes do widening — exatamente o bug documentado no docstring da 144
  ("Correção do deploy de 15/08/2026 ... o banco do deploy em produção só
  prosseguia após o ALTER manual").
- Estado atual do banco local: migrations aplicadas até 096_rag_embedding_1024
  (143 rejeitada; transação da 143 fez rollback — banco consistente).
- Fix correto (não destrutivo): mover a alteração de widening para rodar ANTES
  da 143 — ex.: novo arquivo com depends_on em "142..." e up_revision que a 143/144
  referenciem, OU reaproveitar a 144 alterando down/up chain. Decisão a validar:
  mínimo impacto = criar migration 144b com depends_on="142_document_hash_rescan"
  e ajustar a 144 para depender dela, sem tocar 143.
- O PR #1151 (0bc7b538) padronizou alembic_version varchar(128) mas manteve a
  ordem errada na cadeia — reproduzível localmente, ou seja, é um defeito REAL
  de baseline de instalação nova. Correção pertence ao escopo do Módulo 02
  (migrations) e é autorizada pelo PROMPT 00.

## Próximos passos M02
1. Corrigir ordem do widening (migration nova + chain 143/144 ajustadas)
2. Reexecutar alembic upgrade head até head (144)
3. Alembic downgrade -1 e upgrade novamente (rollback testado)
4. Alembic check (drift) e downgrade a 096 + re-upgrade (validação de downgrade)
5. Iniciar backend (uvicorn) e testar /api/health e /api/health/ready
6. Testar shutdown/restart, worker (Celery/Redis)
7. Frontend build (npm ci + build)
8. Reportar

## Progresso (15/08 2026)

### migrations — CORRIGIDO
- Bug real: migration 143 (revision_id 35 chars) roda antes do widening varchar(32)->128 (migration 144), quebrando instalações novas. Reproduzido localmente.
- Fix aplicado (não destrutivo, DDL widening):
  - Nova migration `144a_alembic_version_widening_pre_143.py` com down_revision=142
    (roda o widening ANTES da 143 em instalações novas).
  - `143_signature_documento_visualizado.py`: down_revision repointada para 144a.
  - `144_alembic_version_varchar128.py`: down_revision repointada para 143 (cadeia linear
    142 -> 144a -> 143 -> 144) e downgrade() transformado em no-op (estreitar
    rejeitaria a transação pois o Alembic grava a revision_id de destino 143 antes
    de executar o corpo — bug confirmado em teste).
- Validações: upgrade head OK (head único), downgrade -1 OK, re-upgrade OK,
  `alembic check` roda sem erro de execução (apenas drift preexistente).

### drift preexistente confirmado no HEAD da main (não introduzido por mim)
1. `users.password_changed_at` — coluna adicionada pela migration 133, mas o
   ORM `models/user.py` NÃO a declara. Nenhum código de app usa o atributo
   (grep vazio). → Fix sugerido: migration 145 dropping a coluna com guarda
   (nenhum código depende dela) OU adicionar ao ORM. Preferir drop com
   verificação de dependências + migration (DDL, baixo risco).
2. `knowledge_chunks.embedding_legacy_768` — mesma situação (migration adicionou,
   ORM não declara, nenhum uso no app). → mesmo tratamento.
3. ~90 renames de índices (ix_X -> ix_tabela_coluna) — renome puro, sem custo;
   gerar migration de rename quando fix 1/2 forem decididos.
4. 2 modify_type (enum/varchar em credenciais_processo_eletronico e
   sincronizacao_processo_eletronico) — verificar se intencionais.

### Próximo: iniciar backend, health, restart/shutdown, worker, frontend build.

## Estado atual (checkpoint pré-compaction)

- Migrations: 144a (widening pré-143) + 145 (drop colunas órfãs password_changed_at e
  embedding_legacy_768) criadas e aplicadas; HEAD = 145, upgrade OK.
- Arquivos alterados/criados (não commitados ainda):
  - M backend/alembic/versions/143_signature_documento_visualizado.py
  - M backend/alembic/versions/144_alembic_version_varchar128.py
  - A backend/alembic/versions/144a_alembic_version_widening_pre_143.py
  - A backend/alembic/versions/145_drop_orphan_db_only_columns.py
  - A qa/homologacao/m01/*, qa/homologacao/m02/*
  - A scripts/inventory/{m01_baseline_check.py,prep_local_env.py,env_shell.sh,summarize_drift.py}
  - .env local gerado (NÃO versionar — gitignore cobre; conferir)
- Falta em M02:
  1. alembic check pós-145 (verificar se drift de índices/modify_type permanece;
     índices renomeados são cosmetic — decidir se cria migration de rename)
  2. alembic downgrade -1 + upgrade (rollback 145)
  3. Iniciar backend (uvicorn) com env exportado: testar /api/health (200),
     /api/health/ready (DB ok); logs de inicialização
  4. Celery worker com Redis (verificar startup; redis ping OK)
  5. Frontend: npm ci + npm run build (node 22 presente)
  6. Docker: docker-compose config (validar sintaxe) — Docker pode não estar no sandbox;
     registrar como verificação de sintaxe apenas
  7. Reportar M02

## Dados chave do repositório
- HEAD main: 89daf7b2 (15/08/2026 22:29 UTC), 2352 commits
- 155 routers, 68 models, 168 services, 103 páginas frontend, 136 migrations (+144a/145),
  487 testes backend, 104 testes frontend, 8 serviços docker-compose, 17 workflows CI
- CI: ci.yml usa PostgreSQL efêmero porta 55432 (ejc_user/ejc_pass/ejc_db),
  APP_ENV=development, RUN_DB_TESTS=1; pytest backend em working-directory=backend
- Gates locais: backend: RUN_DB_TESTS=1 pytest tests; frontend: npm test + lint + tsc
- Auth: JWT; 2FA TOTP (models: totp_secret/totp_enabled, must_change_password)
- Env app depende de env vars exportadas (Settings pydantic v2 com env_file=".env"
  string = sem efeito; compose injeta DATABASE_URL compostos de POSTGRES_*)

## Resultados de saúde (validados)
- Backend uvicorn: startup completo (Scheduler 41 jobs, "EJC v3.0 iniciado"),
  /api/health 200 {status ok, version dev, environment development},
  /api/health/ready 200 {database:true, migrations:true, redis:null, embeddings:true}
  (redis=null é esperado: app roda check sem falhar quando Redis local sem
  configuração específica; celery worker valida Redis separadamente).
- Shutdown graceful: 2 entradas de shutdown nos logs; após kill porta fechada (correto).
- Restart: OK, health 200. Logs sem segredos (grep SECRET/TOKEN/PASSWORD/API_KEY/fernet = vazio).
- Celery worker: inicia com `celery -A app.core.celery_app.celery_app` (docker-compose
  usa este path; docs antigos com app.tasks.celery_app estão desatualizados).

## Achado frontend
- `npm ci` falha: package-lock.json e pnpm-lock.yaml DES sincronizados
  (lock npm: globals@17.11.0 ≠ requerido 17.7.0 por dependência). O repositório tem
  AMBOS os lockfiles (npm + pnpm). Provável cause: alguém rodou `pnpm install` e
  o lock npm ficou defasado. CI usa qual ferramenta? Verificar ci.yml e Dockerfile.

## Frontend — CORRIGIDO + VALIDADO
- Defeito real na main: package.json exige globals ^17.9.0 mas package-lock.json
  pinava 17.7.0 (lock stale após bump do PR #1137; pnpm-lock.yaml também presente
  e divergente). `npm ci` falhava com EUSAGE — quebraria CI e Docker build.
- Fix: `npm install` (lock sync; diff mínimo: 5 adições/35 remoções no lock,
  package.json intocado). npm ci + tsc --noEmit + vite build OK (3.67s, 98 chunks).
- Falta opcional: verificação docker-compose config (docker não disponível no sandbox — registrar)
