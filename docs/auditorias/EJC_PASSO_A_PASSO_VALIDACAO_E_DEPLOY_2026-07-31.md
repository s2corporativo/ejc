# EJC — passo a passo de validação e publicação segura

Data: 2026-07-31  
Branch: `fix/parte10-inteligencia-conferencia-assinatura`

> Não faça merge nem deploy antes de todas as etapas de validação ficarem verdes.
> Os comandos abaixo devem ser executados na VPS, dentro do diretório do EJC.

## 1. Acessar a VPS

No PowerShell do Windows:

```powershell
ssh root@13.140.167.153
```

## 2. Localizar o repositório

```bash
cd /opt/ejc
pwd
git remote -v
git status --short --branch
```

O diretório deve ser `/opt/ejc` e o remoto deve apontar para `s2corporativo/ejc`.

## 3. Salvar o estado atual

```bash
mkdir -p /root/ejc-validacao-$(date +%Y%m%d-%H%M%S)
BACKUP_DIR=$(ls -dt /root/ejc-validacao-* | head -1)
git rev-parse HEAD | tee "$BACKUP_DIR/commit-anterior.txt"
git status --porcelain=v1 | tee "$BACKUP_DIR/git-status.txt"
docker compose ps | tee "$BACKUP_DIR/docker-ps.txt"
docker compose logs --tail=300 backend worker frontend > "$BACKUP_DIR/logs-antes.txt" 2>&1 || true
```

Se `git status --porcelain` mostrar arquivos alterados, pare e salve-os antes de trocar de branch:

```bash
git diff > "$BACKUP_DIR/alteracoes-nao-commitadas.patch"
git diff --cached > "$BACKUP_DIR/alteracoes-indexadas.patch"
```

## 4. Fazer backup do banco

```bash
cd /opt/ejc
bash scripts/backup.sh
```

Confirme que foi gerado arquivo recente:

```bash
find . /opt /root -type f \( -name '*.sql.gz' -o -name '*.dump' \) -mmin -15 2>/dev/null | sort
```

Não continue sem localizar um backup válido.

## 5. Buscar a branch sem alterar a produção

```bash
git fetch origin --prune
git branch --show-current
git log -1 --oneline
```

Crie um worktree separado para validar sem tocar no checkout de produção:

```bash
rm -rf /opt/ejc-validacao
git worktree add /opt/ejc-validacao origin/fix/parte10-inteligencia-conferencia-assinatura
cd /opt/ejc-validacao
git status --short --branch
git log -1 --oneline
```

## 6. Preparar ambiente Python isolado

```bash
cd /opt/ejc-validacao/backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 7. Executar validações sem banco

```bash
cd /opt/ejc-validacao
bash scripts/validar_auditoria_consolidada.sh
```

O script gera o log em:

```text
artifacts/auditoria/
```

Nenhuma etapa marcada como `FALHA` pode ser ignorada.

## 8. Criar banco exclusivo de testes

Use o PostgreSQL do container, sem apontar testes para o banco jurídico real:

```bash
cd /opt/ejc
source .env
TEST_DB="ejc_auditoria_$(date +%Y%m%d%H%M%S)"
docker exec -i ejc_db psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 \
  -c "CREATE DATABASE ${TEST_DB};"
docker exec -i ejc_db psql -U "$POSTGRES_USER" -d "$TEST_DB" -v ON_ERROR_STOP=1 \
  -c 'CREATE EXTENSION IF NOT EXISTS vector;'
```

Monte as URLs apenas na sessão atual:

```bash
export DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:5432/${TEST_DB}"
export DATABASE_URL_SYNC="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:5432/${TEST_DB}"
export RUN_DB_TESTS=1
export APP_ENV=test
export SECRET_KEY="auditoria-local-nao-producao"
export JWT_SECRET_KEY="auditoria-local-nao-producao"
```

Se a porta do PostgreSQL não estiver publicada no host, execute os testes em um container temporário na rede do Compose ou publique a porta somente em loopback. Nunca altere o banco de produção para acomodar os testes.

## 9. Aplicar migrations no banco de teste

```bash
cd /opt/ejc-validacao/backend
source .venv/bin/activate
alembic upgrade head
alembic current
alembic heads
```

`current` e `heads` devem apontar para a mesma revisão.

## 10. Rodar testes de banco e suíte completa

```bash
cd /opt/ejc-validacao/backend
source .venv/bin/activate
RUN_DB_TESTS=1 pytest -q tests/test_integridade_contadores_dblevel.py
pytest -q
```

Também rode cobertura para detectar módulos não exercitados:

```bash
pytest --cov=app --cov-report=term-missing --cov-report=html
```

## 11. Validar frontend

```bash
cd /opt/ejc-validacao/frontend
npm ci
npm run lint
npm run lint:eslint
npm test
npm run build
```

Todas as cinco etapas devem terminar com código de saída zero.

## 12. Validar Compose

```bash
cd /opt/ejc-validacao
cp /opt/ejc/.env .env
docker compose config -q
```

Não imprima o conteúdo do `.env` no terminal ou em logs compartilhados.

## 13. Smoke test isolado

Suba a branch em um projeto Compose separado, usando portas diferentes ou somente rede interna. Não substitua os containers de produção durante esta validação.

Exemplo conceitual:

```bash
cd /opt/ejc-validacao
export COMPOSE_PROJECT_NAME=ejc_validacao
export RUN_MIGRATIONS=0
docker compose build backend worker frontend
```

Antes de executar `up`, revise portas, nomes fixos de container e volumes. O Compose atual usa nomes fixos (`ejc_backend`, `ejc_db`, etc.), portanto uma segunda stack conflitará com a produção. Para smoke isolado, use um arquivo override que remova `container_name`, altere as portas e use volumes próprios. Não execute um segundo `up` com o Compose original.

## 14. Verificações funcionais obrigatórias

Na instância de validação, conferir manualmente:

1. Login e RBAC de cada perfil.
2. Listagem de casos sem filtro.
3. `status=all`, `status=todos`, `status=*` e status reais.
4. Dashboard e `/cases/stats` com números idênticos.
5. Caso arquivado fora da contagem de ativos.
6. Peça de IA em rascunho entrando na fila de revisão.
7. Exclusão lógica de caso removendo filhos das superfícies operacionais.
8. Restauração do caso restabelecendo a visibilidade dos filhos.
9. Geração de minuta, conferência e assinatura.
10. Download imediato do PDF de minuta.
11. `/api/ia/status` com um único contrato.
12. RAG, embeddings e pesquisa jurídica.
13. Upload de PDF, OCR e indexação.
14. Celery e Redis.
15. Backup e restauração em banco descartável.

## 15. Verificar embeddings

```bash
cd /opt/ejc
 grep -E '^(EMBEDDINGS_ENABLED|EMBEDDING_MODEL|EMBEDDING_DIM)=' .env || true
```

A ativação só deve ocorrer quando o modelo configurado e a dimensão forem compatíveis com a coluna vetorial e com os embeddings já existentes. Depois:

```bash
docker compose exec backend python scripts/check_flags_producao.py
```

Se houver mudança de modelo, execute a reindexação indicada pelo próprio projeto; não misture vetores de modelos ou dimensões diferentes.

## 16. Verificar Ollama antes de ativar

```bash
free -h
df -h
docker stats --no-stream
```

Somente se houver RAM suficiente:

```bash
cd /opt/ejc
docker compose --profile ia-local up -d ollama ollama-init
docker compose ps
docker compose logs --tail=200 ollama ollama-init
```

Depois ajuste `OLLAMA_ENABLED=true` no `.env` e reinicie apenas backend e worker. Não exponha a porta do Ollama publicamente.

## 17. Preparar publicação

Somente com todos os testes aprovados:

```bash
cd /opt/ejc-validacao
git status --short --branch
git log --oneline --decorate -10
```

Revise o comparativo no GitHub entre a branch e `main`. Abra PR apenas quando decidir iniciar a revisão formal.

## 18. Deploy seguro após merge autorizado

Depois de mergear na `main`:

```bash
cd /opt/ejc
git checkout main
git fetch origin --prune
git pull --ff-only origin main
bash scripts/deploy_vps_safe.sh
```

Não use `git reset --hard` nem force atualização da `main`.

## 19. Pós-deploy

```bash
cd /opt/ejc
docker compose ps
bash scripts/post_deploy_check.sh
curl -fsS http://127.0.0.1:8000/api/health
curl -I http://127.0.0.1:8080/
docker compose logs --tail=300 backend worker frontend
```

Registre o SHA publicado:

```bash
git rev-parse HEAD
curl -fsS http://127.0.0.1:8000/api/health
```

O SHA informado pela API deve coincidir com `git rev-parse HEAD`.

## 20. Rollback

Se o pós-deploy falhar, use o SHA salvo em `commit-anterior.txt` e o procedimento de rollback do script de deploy. Não restaure o banco automaticamente sem confirmar que uma migration incompatível foi aplicada.

Para retornar apenas o código:

```bash
ANTERIOR=$(cat "$BACKUP_DIR/commit-anterior.txt")
git fetch origin --prune
git checkout --detach "$ANTERIOR"
```

Depois reconstrua os serviços conforme o procedimento de deploy seguro. Para banco, restaure somente a partir do backup verificado e após identificar a migration que exige reversão.

## 21. Limpeza do ambiente de teste

```bash
cd /opt/ejc
source .env
docker exec -i ejc_db psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${TEST_DB}';" \
  -c "DROP DATABASE IF EXISTS ${TEST_DB};"
git worktree remove /opt/ejc-validacao
```

Guarde os logs de validação e o relatório de cobertura antes de remover o worktree.
