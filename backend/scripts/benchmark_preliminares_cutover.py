#!/usr/bin/env python3
"""Mede a migration 171 com massa fictícia em PostgreSQL local de teste.

Cria somente schema/tabelas vazias, depois todas as cargas/cutovers/rollbacks
ocorrem em transações desfeitas. Limpeza remove somente esses objetos vazios.
Não acessa linhas do schema público, apenas suas definições de tabelas.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
from time import perf_counter
import traceback
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

MIGRATION = Path(__file__).resolve().parents[1] / "alembic/versions/171_preliminares_cutover.py"


def validate_test_url(value):
    url = make_url(value)
    if (os.getenv("RUN_DB_TESTS") != "1" or url.host not in {"127.0.0.1", "localhost"}
            or any(os.getenv(n) for n in ("PGHOSTADDR", "PGHOST", "PGDATABASE", "PGPORT", "PGSERVICE", "PGSERVICEFILE"))
            or url.drivername not in {"postgresql", "postgresql+psycopg", "postgresql+psycopg2"}
            or url.query  # libpq permite sobrescrever host/database via query string
            or not re.fullmatch(r"ejc_(?:test|higiene|redundancias)_[a-zA-Z0-9_]+", url.database or "")):
        raise ValueError("Benchmark exige RUN_DB_TESTS=1 e banco local com nome de teste")
    return url


def migrate(module, conn, direction):
    with Operations.context(MigrationContext.configure(conn)):
        getattr(module, direction)()


def setup(engine, module, schema):
    names = [f[0] for f in module.FONTES] + list(module.CANONICAS)
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        tables = set(inspect(conn).get_table_names(schema="public"))
        for name in names:
            source = name if name in tables else name + "_legado_171"
            conn.execute(text(f'CREATE TABLE "{schema}".{name} (LIKE public.{source} INCLUDING ALL)'))
        for old, canonical, _, renames in module.FONTES:
            if canonical == "preliminares":
                continue
            column = next(k for k, v in renames.items() if v == "preliminar_id")
            parent = "raio_x_analises" if column == "analise_id" else "legal_chat_sessions"
            conn.execute(text(f'ALTER TABLE "{schema}".{old} ADD FOREIGN KEY ({column}) '
                              f'REFERENCES "{schema}".{parent}(id) ON DELETE CASCADE'))
        for child in module.CANONICAS[1:]:
            conn.execute(text(f'ALTER TABLE "{schema}".{child} ADD FOREIGN KEY (preliminar_id) '
                              f'REFERENCES "{schema}".preliminares(id) ON DELETE CASCADE'))
    return names


def cleanup_empty(engine, schema, names):
    # Nenhum CASCADE, purge ou remoção de dados: exige objetos conhecidos vazios.
    with engine.begin() as conn:
        if set(inspect(conn).get_table_names(schema=schema)) != set(names):
            raise RuntimeError("Schema fictício mudou; preservar para inspeção")
        conn.execute(text("SET LOCAL lock_timeout='5s'"))
        conn.execute(text('LOCK TABLE ' + ','.join(f'"{schema}".{n}' for n in names)
                          + ' IN ACCESS EXCLUSIVE MODE'))
        if any(conn.execute(text(f'SELECT EXISTS(SELECT 1 FROM "{schema}".{n})')).scalar_one() for n in names):
            raise RuntimeError("Schema fictício contém dados; limpeza recusada")
        for name in reversed(names):
            conn.execute(text(f'DROP TABLE "{schema}".{name}'))
        conn.execute(text(f'DROP SCHEMA "{schema}"'))


def seed(conn, parents, payload):
    values = {"n": parents, "bytes": payload}
    statements = [
        "INSERT INTO raio_x_analises(id,titulo,created_by,dados_extraidos) SELECT 'r-'||i, 'Raio ficticio', 'u-ficticio', jsonb_build_object('ficticio',repeat('x',:bytes)) FROM generate_series(1,:n) i",
        "INSERT INTO legal_chat_sessions(id,titulo,created_by,workspace_texto) SELECT 's-'||i, 'Sala ficticia', 'u-ficticio', repeat('x',:bytes) FROM generate_series(1,:n) i",
        "INSERT INTO raio_x_documentos(id,analise_id,nome_original,filepath,size_bytes,sha256,uploaded_by) SELECT 'dr-'||i,'r-'||i,'ficticio.txt','/tmp/ficticio.txt',1,'hash-r-'||i,'u-ficticio' FROM generate_series(1,:n) i",
        "INSERT INTO legal_chat_attachments(id,session_id,nome_original,filepath,size_bytes,sha256,uploaded_by) SELECT 'ds-'||i,'s-'||i,'ficticio.txt','/tmp/ficticio.txt',1,'hash-s-'||i,'u-ficticio' FROM generate_series(1,:n) i",
        "INSERT INTO legal_chat_messages(id,session_id,autor,conteudo) SELECT 'm-'||i||'-'||v,'s-'||i,'user',repeat('x',:bytes) FROM generate_series(1,:n) i CROSS JOIN generate_series(1,10) v",
        "INSERT INTO legal_chat_state_versions(id,session_id,versao,origem,estado) SELECT 'e-'||i||'-'||v,'s-'||i,v,'ia',jsonb_build_object('ficticio',repeat('x',:bytes)) FROM generate_series(1,:n) i CROSS JOIN generate_series(1,2) v",
    ]
    for statement in statements:
        conn.execute(text(statement), values)


def verify_mirrors(conn, module):
    for name, _, _, _ in module.FONTES:
        columns = ",".join(module.COLUNAS[name])
        query = f"SELECT {columns} FROM {name} EXCEPT ALL SELECT {columns} FROM {name}_legado_171"
        reverse = f"SELECT {columns} FROM {name}_legado_171 EXCEPT ALL SELECT {columns} FROM {name}"
        assert not conn.execute(text(query + " LIMIT 1")).first()
        assert not conn.execute(text(reverse + " LIMIT 1")).first()


def sample(engine, module, schema, parents, payload):
    with engine.connect() as conn:
        txn = conn.begin()
        try:
            conn.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
            seed(conn, parents, payload)
            lock_acquired = []

            def after_execute(connection, cursor, statement, parameters, context, executemany):
                if statement.startswith("LOCK TABLE"):
                    lock_acquired.append(perf_counter())

            event.listen(conn, "after_cursor_execute", after_execute)
            start = perf_counter()
            migrate(module, conn, "upgrade")
            migrated = perf_counter()
            event.remove(conn, "after_cursor_execute", after_execute)
            pid = conn.execute(text("SELECT pg_backend_pid()")).scalar_one()
            oids = conn.execute(text("SELECT c.oid FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=:schema AND c.relkind IN ('r','v')"), {"schema": schema}).scalars().all()
            with engine.connect() as observer:
                exclusive = observer.execute(text("SELECT count(*) FROM pg_locks WHERE pid=:pid AND mode='AccessExclusiveLock' AND granted AND relation=ANY(:oids)"), {"pid": pid, "oids": oids}).scalar_one()
                assert exclusive >= 10
                observer.execute(text("SET LOCAL statement_timeout='200ms'"))
                blocked_start = perf_counter()
                try:
                    observer.execute(text(f'SELECT count(*) FROM "{schema}".raio_x_analises'))
                except DBAPIError as error:
                    assert error.orig.pgcode == "57014"
                else:
                    raise AssertionError("Leitor não ficou bloqueado pelo cutover")
                blocked_ms = (perf_counter() - blocked_start) * 1000
            counts = {n: conn.execute(text(f"SELECT count(*) FROM {n}")).scalar_one() for n in module.CANONICAS}
            assert list(counts.values()) == [parents * 2, parents * 2, parents * 10, parents * 2]
            conn.execute(text("UPDATE legal_chat_sessions SET titulo='Editado ficticio' WHERE id='s-1'"))
            conn.execute(text("DELETE FROM preliminar_mensagens WHERE id='m-1-1'"))
            verify_mirrors(conn, module)
            downgrade_start = perf_counter()
            migrate(module, conn, "downgrade")
            downgrade_ms = (perf_counter() - downgrade_start) * 1000
            assert conn.execute(text("SELECT titulo FROM legal_chat_sessions WHERE id='s-1'")).scalar_one() == "Editado ficticio"
            assert conn.execute(text("SELECT count(*) FROM legal_chat_messages")).scalar_one() == parents * 10 - 1
            migrate(module, conn, "upgrade")
            verify_mirrors(conn, module)
            return {"parents_per_origin": parents, "rows": sum(counts.values()), "counts": counts,
                    "payload_bytes": payload, "upgrade_ms": round((migrated - start) * 1000, 2),
                    "exclusive_during_upgrade_ms": round((migrated - lock_acquired[0]) * 1000, 2),
                    "exclusive_relations_observed": exclusive, "reader_timeout_ms": round(blocked_ms, 2),
                    "downgrade_ms": round(downgrade_ms, 2), "full_mirror_equivalence": True,
                    "rollback_and_reupgrade": True}
        finally:
            txn.rollback()


def contention(engine, module, schema):
    with engine.connect() as holder, engine.connect() as migrator:
        holder.execute(text(f'SELECT count(*) FROM "{schema}".raio_x_analises'))
        txn = migrator.begin()
        try:
            migrator.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
            start = perf_counter()
            try:
                migrate(module, migrator, "upgrade")
            except DBAPIError as error:
                assert error.orig.pgcode == "55P03"  # lock_timeout, não falha arbitrária
            else:
                raise AssertionError("Lock concorrente deveria impedir o cutover")
            elapsed = round((perf_counter() - start) * 1000, 2)
        finally:
            txn.rollback()
            holder.rollback()
    with engine.connect() as conn:
        assert not inspect(conn).get_view_names(schema=schema)
        assert conn.execute(text(f'SELECT count(*) FROM "{schema}".preliminares')).scalar_one() == 0
    return {"lock_timeout_ms": elapsed, "sqlstate": "55P03", "schema_unchanged": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", default="1000,10000")
    parser.add_argument("--payload-bytes", type=int, default=1024)
    args = parser.parse_args()
    engine = None
    try:
        sizes = [int(n) for n in args.sizes.split(",")]
        if not sizes or not all(1 <= n <= 50000 for n in sizes) or not 1 <= args.payload_bytes <= 8192:
            raise ValueError("Massa fora dos limites do benchmark")
        engine = create_engine(validate_test_url(os.environ.get("DATABASE_URL_SYNC", "")))
        spec = importlib.util.spec_from_file_location("benchmark_cutover_171", MIGRATION)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        schema = "bench_171_" + uuid4().hex
        names = setup(engine, module, schema)
        try:
            results = [sample(engine, module, schema, n, args.payload_bytes) for n in sizes]
            lock_test = contention(engine, module, schema)
        finally:
            cleanup_empty(engine, schema, names)
        print(json.dumps({"migration_sha256": hashlib.sha256(MIGRATION.read_bytes()).hexdigest(),
                          "samples": results, "contention": lock_test,
                          "synthetic_only": True, "test_schema_removed": True}, indent=2))
        return 0
    except Exception as error:
        # DBAPIError pode incluir DSN/SQL/valores: não registrar mensagem crua.
        frames = traceback.extract_tb(error.__traceback__)
        print(json.dumps({"error_type": type(error).__name__,
                          "frames": [{"file": Path(f.filename).name, "line": f.lineno} for f in frames]}, indent=2))
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
