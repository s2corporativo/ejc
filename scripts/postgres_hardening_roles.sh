#!/usr/bin/env bash
# Hardening PostgreSQL do EJC — separa owner de schema (ejc_migrator) do runtime (ejc_app).
#
# Uso:
#   bash scripts/postgres_hardening_roles.sh plan
#   POSTGRES_ROLE_CUTOVER_ALLOW=1 bash scripts/postgres_hardening_roles.sh apply
#   POSTGRES_ROLE_CUTOVER_ALLOW=1 bash scripts/postgres_hardening_roles.sh rollback
#
# O script não lê, gera nem imprime senhas. Os papéis devem existir previamente.
# Requer migration 162 aplicada antes do cutover.
set -euo pipefail

MODE="${1:-plan}"
DB_CONTAINER="${EJC_DB_CONTAINER:-ejc_db}"
ADMIN_ROLE="${EJC_DB_ADMIN_ROLE:-ejc_user}"
DB_NAME="${EJC_DB_NAME:-ejc_db}"
APP_ROLE="${EJC_DB_APP_ROLE:-ejc_app}"
MIGRATOR_ROLE="${EJC_DB_MIGRATOR_ROLE:-ejc_migrator}"
EXPECTED_HEAD="${EJC_DB_HARDENING_HEAD:-162_runtime_tables_alembic}"

case "$MODE" in
  plan|apply|rollback) ;;
  *) echo "Uso: $0 {plan|apply|rollback}" >&2; exit 2 ;;
esac

command -v docker >/dev/null 2>&1 || { echo "Docker ausente." >&2; exit 2; }
docker inspect "$DB_CONTAINER" >/dev/null 2>&1 || {
  echo "Container PostgreSQL não encontrado: $DB_CONTAINER" >&2
  exit 2
}

psql_admin() {
  docker exec -i "$DB_CONTAINER" psql -v ON_ERROR_STOP=1 -U "$ADMIN_ROLE" -d "$DB_NAME" "$@"
}

role_exists() {
  local role="$1"
  [ "$(psql_admin -Atqc "SELECT 1 FROM pg_roles WHERE rolname = '$role'")" = "1" ]
}

role_exists "$APP_ROLE" || { echo "Papel $APP_ROLE ausente." >&2; exit 2; }
role_exists "$MIGRATOR_ROLE" || { echo "Papel $MIGRATOR_ROLE ausente." >&2; exit 2; }

HEAD="$(psql_admin -Atqc "SELECT version_num FROM alembic_version LIMIT 1")"
[ "$HEAD" = "$EXPECTED_HEAD" ] || {
  echo "Cutover bloqueado: Alembic atual=$HEAD; esperado=$EXPECTED_HEAD." >&2
  exit 2
}

if [ "$MODE" = "plan" ]; then
  psql_admin -Atqc "
    SELECT 'alembic=' || version_num FROM alembic_version LIMIT 1;
    SELECT 'app_role=' || rolname || ',super=' || rolsuper || ',createdb=' || rolcreatedb ||
           ',createrole=' || rolcreaterole || ',replication=' || rolreplication
      FROM pg_roles WHERE rolname='$APP_ROLE';
    SELECT 'migrator_role=' || rolname || ',super=' || rolsuper || ',createdb=' || rolcreatedb ||
           ',createrole=' || rolcreaterole || ',replication=' || rolreplication
      FROM pg_roles WHERE rolname='$MIGRATOR_ROLE';
    SELECT 'relations_admin=' || count(*)
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
     WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','S')
       AND pg_get_userbyid(c.relowner)='$ADMIN_ROLE';
    SELECT 'relations_migrator=' || count(*)
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
     WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','S')
       AND pg_get_userbyid(c.relowner)='$MIGRATOR_ROLE';
  "
  exit 0
fi

[ "${POSTGRES_ROLE_CUTOVER_ALLOW:-}" = "1" ] || {
  echo "Defina POSTGRES_ROLE_CUTOVER_ALLOW=1 para executar $MODE." >&2
  exit 2
}

if [ "$MODE" = "apply" ]; then
  psql_admin <<SQL
BEGIN;

GRANT CONNECT ON DATABASE $DB_NAME TO $APP_ROLE, $MIGRATOR_ROLE;
GRANT USAGE ON SCHEMA public TO $APP_ROLE, $MIGRATOR_ROLE;
GRANT CREATE ON SCHEMA public TO $MIGRATOR_ROLE;
REVOKE CREATE ON SCHEMA public FROM $APP_ROLE;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO $APP_ROLE;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO $APP_ROLE;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO $APP_ROLE;

DO \$\$
DECLARE r record; kind text;
BEGIN
  FOR r IN
    SELECT c.oid,n.nspname,c.relname,c.relkind
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
     WHERE n.nspname='public'
       AND c.relkind IN ('r','p','v','m')
       AND pg_get_userbyid(c.relowner)='$ADMIN_ROLE'
       AND NOT EXISTS (
         SELECT 1 FROM pg_depend d
          WHERE d.classid='pg_class'::regclass
            AND d.objid=c.oid
            AND d.deptype='e'
       )
  LOOP
    kind := CASE r.relkind
              WHEN 'v' THEN 'VIEW'
              WHEN 'm' THEN 'MATERIALIZED VIEW'
              ELSE 'TABLE'
            END;
    EXECUTE format('ALTER %s %I.%I OWNER TO $MIGRATOR_ROLE',
                   kind,r.nspname,r.relname);
  END LOOP;
END \$\$;

-- Sequências SERIAL/IDENTITY vinculadas a colunas seguem o owner da tabela;
-- PostgreSQL não permite mudar seu owner isoladamente.
DO \$\$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT c.oid,n.nspname,c.relname
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
     WHERE n.nspname='public'
       AND c.relkind='S'
       AND pg_get_userbyid(c.relowner)='$ADMIN_ROLE'
       AND NOT EXISTS (
         SELECT 1 FROM pg_depend d
          WHERE d.classid='pg_class'::regclass
            AND d.objid=c.oid
            AND d.deptype IN ('a','i','e')
       )
  LOOP
    EXECUTE format('ALTER SEQUENCE %I.%I OWNER TO $MIGRATOR_ROLE',
                   r.nspname,r.relname);
  END LOOP;
END \$\$;

DO \$\$
DECLARE r record; kind text;
BEGIN
  FOR r IN
    SELECT p.oid,n.nspname,p.proname,p.prokind,
           pg_get_function_identity_arguments(p.oid) args
      FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
     WHERE n.nspname='public'
       AND pg_get_userbyid(p.proowner)='$ADMIN_ROLE'
       AND p.prokind IN ('f','p')
       AND NOT EXISTS (
         SELECT 1 FROM pg_depend d
          WHERE d.classid='pg_proc'::regclass
            AND d.objid=p.oid
            AND d.deptype='e'
       )
  LOOP
    kind := CASE r.prokind WHEN 'p' THEN 'PROCEDURE' ELSE 'FUNCTION' END;
    EXECUTE format('ALTER %s %I.%I(%s) OWNER TO $MIGRATOR_ROLE',
                   kind,r.nspname,r.proname,r.args);
  END LOOP;
END \$\$;

-- Apenas enums/domains independentes; composite row-types seguem as tabelas.
DO \$\$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT t.oid,n.nspname,t.typname
      FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
     WHERE n.nspname='public'
       AND t.typtype IN ('e','d')
       AND pg_get_userbyid(t.typowner)='$ADMIN_ROLE'
       AND NOT EXISTS (
         SELECT 1 FROM pg_depend d
          WHERE d.classid='pg_type'::regclass
            AND d.objid=t.oid
            AND d.deptype='e'
       )
  LOOP
    EXECUTE format('ALTER TYPE %I.%I OWNER TO $MIGRATOR_ROLE',
                   r.nspname,r.typname);
  END LOOP;
END \$\$;

ALTER DEFAULT PRIVILEGES FOR ROLE $MIGRATOR_ROLE IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO $APP_ROLE;
ALTER DEFAULT PRIVILEGES FOR ROLE $MIGRATOR_ROLE IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO $APP_ROLE;
ALTER DEFAULT PRIVILEGES FOR ROLE $MIGRATOR_ROLE IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO $APP_ROLE;

-- Reforça o WORM e mantém readiness do runtime.
REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM $APP_ROLE;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON alembic_version FROM $APP_ROLE;
GRANT SELECT ON alembic_version TO $APP_ROLE;

COMMIT;
SQL
else
  # Rollback de ownership/grants. Não altera extensão, senha ou conteúdo.
  psql_admin <<SQL
BEGIN;

DO \$\$
DECLARE r record; kind text;
BEGIN
  FOR r IN
    SELECT c.oid,n.nspname,c.relname,c.relkind
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
     WHERE n.nspname='public'
       AND c.relkind IN ('r','p','v','m')
       AND pg_get_userbyid(c.relowner)='$MIGRATOR_ROLE'
  LOOP
    kind := CASE r.relkind
              WHEN 'v' THEN 'VIEW'
              WHEN 'm' THEN 'MATERIALIZED VIEW'
              ELSE 'TABLE'
            END;
    EXECUTE format('ALTER %s %I.%I OWNER TO $ADMIN_ROLE',
                   kind,r.nspname,r.relname);
  END LOOP;
END \$\$;

DO \$\$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT c.oid,n.nspname,c.relname
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
     WHERE n.nspname='public'
       AND c.relkind='S'
       AND pg_get_userbyid(c.relowner)='$MIGRATOR_ROLE'
       AND NOT EXISTS (
         SELECT 1 FROM pg_depend d
          WHERE d.classid='pg_class'::regclass
            AND d.objid=c.oid
            AND d.deptype IN ('a','i','e')
       )
  LOOP
    EXECUTE format('ALTER SEQUENCE %I.%I OWNER TO $ADMIN_ROLE',
                   r.nspname,r.relname);
  END LOOP;
END \$\$;

DO \$\$
DECLARE r record; kind text;
BEGIN
  FOR r IN
    SELECT p.oid,n.nspname,p.proname,p.prokind,
           pg_get_function_identity_arguments(p.oid) args
      FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
     WHERE n.nspname='public'
       AND pg_get_userbyid(p.proowner)='$MIGRATOR_ROLE'
       AND p.prokind IN ('f','p')
  LOOP
    kind := CASE r.prokind WHEN 'p' THEN 'PROCEDURE' ELSE 'FUNCTION' END;
    EXECUTE format('ALTER %s %I.%I(%s) OWNER TO $ADMIN_ROLE',
                   kind,r.nspname,r.proname,r.args);
  END LOOP;
END \$\$;

DO \$\$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT t.oid,n.nspname,t.typname
      FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
     WHERE n.nspname='public'
       AND t.typtype IN ('e','d')
       AND pg_get_userbyid(t.typowner)='$MIGRATOR_ROLE'
  LOOP
    EXECUTE format('ALTER TYPE %I.%I OWNER TO $ADMIN_ROLE',
                   r.nspname,r.typname);
  END LOOP;
END \$\$;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO $APP_ROLE;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO $APP_ROLE;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO $APP_ROLE;

COMMIT;
SQL
fi

# Pós-condições sem conteúdo sensível.
psql_admin -Atqc "
  SELECT 'head=' || version_num FROM alembic_version LIMIT 1;
  SELECT 'app_schema_create=' ||
         has_schema_privilege('$APP_ROLE','public','CREATE');
  SELECT 'app_audit_update=' ||
         has_table_privilege('$APP_ROLE','audit_logs','UPDATE');
  SELECT 'relations_migrator=' || count(*)
    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','S')
     AND pg_get_userbyid(c.relowner)='$MIGRATOR_ROLE';
"
