---
name: gestor-migracao-banco
description: >
  Playbook de referência de migrações Alembic do EJC/FastAPI (criar/reverter migration, adicionar coluna sem perda, renomear com segurança, zero-downtime, seed). Ponto de entrada canônico: agente `db-migrations` — este arquivo é o playbook que ele consulta, não um roteador concorrente. Consulte para: padrões de migração segura, downgrade funcional, evitar heads múltiplos, backup antes de migrar.
---

> Playbook de referência. Ponto de entrada canônico: agente `db-migrations`. Consultado durante a tarefa — não roteia.

# Gestor de Migrações de Banco — EJC (Alembic) + Sistema-S2 (SQL)

## Contexto

```
EJC BACKEND: FastAPI + SQLAlchemy + Alembic + PostgreSQL
SISTEMA-S2: TypeScript + node-postgres + scripts SQL versionados
REGRA ABSOLUTA: nunca alterar banco de produção sem backup + teste em homologação
```

---

## 1. Alembic — EJC (FastAPI)

### Inicialização (primeira vez)

```bash
cd backend
pip install alembic --break-system-packages
alembic init alembic

# alembic.ini — ajustar sqlalchemy.url
# sqlalchemy.url = postgresql://%(DB_USER)s:%(DB_PASS)s@%(DB_HOST)s/%(DB_NAME)s

# alembic/env.py — importar os modelos
from app.database import Base
from app.models import *  # importa todos os modelos
target_metadata = Base.metadata
```

### Comandos Essenciais

```bash
# Criar migration automática (detecta diferenças do schema)
alembic revision --autogenerate -m "add_clients_table"

# Criar migration manual (vazia para preencher)
alembic revision -m "migrate_case_data"

# Executar todas as migrations pendentes
alembic upgrade head

# Reverter uma migration
alembic downgrade -1

# Reverter para versão específica
alembic downgrade abc123def456

# Ver histórico
alembic history --verbose

# Ver estado atual
alembic current

# Ver SQL que seria executado (sem executar)
alembic upgrade head --sql
```

### Templates de Migration

#### Adicionar coluna (seguro em produção)
```python
def upgrade() -> None:
    # Adicionar coluna com valor padrão — não bloqueia tabela
    op.add_column("cases", sa.Column(
        "priority",
        sa.String(20),
        nullable=True,
        server_default="normal"
    ))
    # Preencher dados existentes se necessário
    op.execute("UPDATE cases SET priority = 'normal' WHERE priority IS NULL")
    # Tornar NOT NULL apenas depois de preencher
    op.alter_column("cases", "priority", nullable=False)

def downgrade() -> None:
    op.drop_column("cases", "priority")
```

#### Renomear coluna (cuidado — pode quebrar código)
```python
def upgrade() -> None:
    # Estratégia segura: adicionar nova + copiar dados + remover antiga
    op.add_column("clients", sa.Column("full_name", sa.String(200), nullable=True))
    op.execute("UPDATE clients SET full_name = name")
    op.alter_column("clients", "full_name", nullable=False)
    # NÃO remover "name" ainda — manter até confirmar código atualizado
    # op.drop_column("clients", "name")  # fazer em migration separada
```

#### Criar índice em tabela grande (sem bloqueio)
```python
def upgrade() -> None:
    # CONCURRENTLY: não bloqueia leituras/escritas durante criação
    op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_cases_status ON cases(status)")

def downgrade() -> None:
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_cases_status")
```

#### Migration de dados (transformação)
```python
def upgrade() -> None:
    # Criar nova estrutura
    op.create_table("case_areas", ...)
    # Migrar dados antigos
    connection = op.get_bind()
    cases = connection.execute("SELECT id, area FROM cases").fetchall()
    for case in cases:
        connection.execute(
            "INSERT INTO case_areas (case_id, area_name) VALUES (%s, %s)",
            (case.id, case.area)
        )
    # Não remover coluna antiga até validar

def downgrade() -> None:
    op.drop_table("case_areas")
```

---

## 2. Sistema-S2 — Migrations SQL Versionadas

### Estrutura de Arquivos

```
sistema-s2/
└── db/
    └── migrations/
        ├── 001_initial_schema.sql
        ├── 002_add_editais_radar.sql
        ├── 003_add_contracts.sql
        └── run_migrations.ts
```

### run_migrations.ts

```typescript
// db/migrations/run_migrations.ts
import { Pool } from "pg"
import * as fs from "fs"
import * as path from "path"

const pool = new Pool({ connectionString: process.env.DATABASE_URL })

async function runMigrations() {
  // Criar tabela de controle de migrations
  await pool.query(`
    CREATE TABLE IF NOT EXISTS schema_migrations (
      version INTEGER PRIMARY KEY,
      filename TEXT NOT NULL,
      applied_at TIMESTAMP DEFAULT NOW()
    )
  `)

  const migrationsDir = path.join(__dirname)
  const files = fs.readdirSync(migrationsDir)
    .filter(f => f.match(/^\d{3}_.*\.sql$/))
    .sort()

  for (const file of files) {
    const version = parseInt(file.split("_")[0])
    const existing = await pool.query(
      "SELECT version FROM schema_migrations WHERE version = $1",
      [version]
    )
    if (existing.rows.length > 0) {
      console.log(`⏭️  Migration ${file} — já aplicada`)
      continue
    }

    console.log(`⚡ Aplicando: ${file}`)
    const sql = fs.readFileSync(path.join(__dirname, file), "utf8")
    const client = await pool.connect()
    try {
      await client.query("BEGIN")
      await client.query(sql)
      await client.query(
        "INSERT INTO schema_migrations (version, filename) VALUES ($1, $2)",
        [version, file]
      )
      await client.query("COMMIT")
      console.log(`✅ ${file} aplicada com sucesso`)
    } catch (err) {
      await client.query("ROLLBACK")
      console.error(`❌ Erro em ${file}:`, err)
      throw err
    } finally {
      client.release()
    }
  }
  await pool.end()
}

runMigrations().catch(err => { console.error(err); process.exit(1) })
```

---

## 3. Protocolo de Migração Segura em Produção

```bash
# 1. BACKUP ANTES DE TUDO
pg_dump -h DB_HOST -U DB_USER -d DB_NAME -F c -f backup_$(date +%Y%m%d_%H%M%S).dump

# 2. TESTAR EM HOMOLOGAÇÃO PRIMEIRO
DATABASE_URL=postgresql://...homolog alembic upgrade head

# 3. VER SQL GERADO
alembic upgrade head --sql > migration_preview.sql
cat migration_preview.sql  # revisar linha por linha

# 4. EXECUTAR EM PRODUÇÃO
alembic upgrade head 2>&1 | tee migration_log.txt

# 5. VERIFICAR RESULTADO
alembic current
psql -c "SELECT * FROM alembic_version"

# 6. EM CASO DE ERRO
alembic downgrade -1
# Restaurar backup se necessário
pg_restore -h DB_HOST -U DB_USER -d DB_NAME backup_file.dump
```

---

## 4. Diagnóstico de Problemas Comuns

```bash
# Migration em conflito (dois devs criaram migrations simultâneas)
# SINTOMA: alembic history mostra fork (duas revisões com mesmo down_revision)
# SOLUÇÃO: criar migration de merge
alembic merge -m "merge_branch" abc123 def456

# Banco divergiu do código (alguém alterou manualmente)
# SINTOMA: alembic upgrade falha com "column already exists"
# SOLUÇÃO 1: marcar como aplicada sem executar
alembic stamp <revision_id>
# SOLUÇÃO 2: ajustar a migration para verificar antes de criar
op.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS phone TEXT")

# Alembic não detecta mudança no model
# CAUSA: model não importado no env.py
# SOLUÇÃO: verificar imports em alembic/env.py
```

---

## 5. Checklist Pré-Migração Produção

```
[ ] Backup completo do banco realizado e verificado
[ ] Migration testada em ambiente de homologação
[ ] SQL gerado revisado linha por linha
[ ] Janela de manutenção comunicada (se necessário)
[ ] Rollback planejado e testado
[ ] Monitoramento de erros ativo durante execução
[ ] Confirmação de integridade pós-migração (SELECT COUNT(*) nas tabelas afetadas)
```
