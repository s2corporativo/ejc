#!/usr/bin/env python3
"""Restore drill from the latest encrypted rclone backup."""
from __future__ import annotations
import json
import os
import secrets
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse
from app.core.config import get_settings
from app.services.backup_service import decifrar_arquivo

settings = get_settings()

def run(args, env=None, timeout=900):
    try:
        return subprocess.run(args, check=True, capture_output=True, text=True, env=env, timeout=timeout)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()[:1200]
        raise RuntimeError(
            f"command failed rc={exc.returncode} cmd={args[0]}: {detail}"
        ) from exc

def conn():
    u = urlparse(settings.DATABASE_URL_SYNC)
    return {"host": u.hostname or "db", "port": str(u.port or 5432),
            "user": unquote(u.username or ""), "password": unquote(u.password or ""),
            "db": unquote((u.path or "").lstrip("/"))}

def pg_env(c):
    return {**os.environ, "PGPASSWORD": c["password"]}

def psql(c, db, sql):
    return run(["psql","-h",c["host"],"-p",c["port"],"-U",c["user"],"-d",db,
                "-v","ON_ERROR_STOP=1","-A","-t","-q","-c",sql], pg_env(c)).stdout.strip()

def main():
    started = time.monotonic()
    remote = (settings.BACKUP_RCLONE_REMOTE or "").strip()
    key = (settings.BACKUP_ENCRYPTION_KEY or "").strip()
    if not remote or not key:
        raise RuntimeError("backup remote/key missing")
    names = run(["rclone","lsf",remote,"--files-only","--include","ejc_backup_*_db.dump.enc"]).stdout.splitlines()
    names = sorted(x.strip() for x in names if x.strip())
    if not names:
        raise RuntimeError("no database backup found offsite")
    latest = names[-1]
    remote_file = f"{remote.rstrip('/')}/{latest}"
    remote_bytes = int(json.loads(run(["rclone","size","--json",remote_file]).stdout).get("bytes",-1))
    if remote_bytes <= 0:
        raise RuntimeError("remote backup empty")
    c = conn()
    target = ("ejc_restore_offsite_" + secrets.token_hex(5))[:63]
    created = False
    try:
        with tempfile.TemporaryDirectory(prefix="ejc_restore_offsite_") as tmp:
            enc = Path(tmp) / "backup.enc"
            clear = Path(tmp) / "backup.dump"
            run(["rclone","copyto",remote_file,str(enc)])
            if enc.stat().st_size != remote_bytes:
                raise RuntimeError("downloaded size differs from remote")
            clear_bytes = decifrar_arquivo(str(enc), str(clear), key)
            if clear_bytes <= 0:
                raise RuntimeError("decrypted dump empty")
            src_version = psql(c,c["db"],"SELECT version_num FROM alembic_version LIMIT 1;")
            src_tables = int(psql(c,c["db"],"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';"))
            run(["createdb","-h",c["host"],"-p",c["port"],"-U",c["user"],"-T","template0",target], pg_env(c))
            created = True
            run(["pg_restore","-h",c["host"],"-p",c["port"],"-U",c["user"],"-d",target,
                 "--exit-on-error","--no-owner","--no-privileges",str(clear)], pg_env(c), 1200)
            dst_version = psql(c,target,"SELECT version_num FROM alembic_version LIMIT 1;")
            dst_tables = int(psql(c,target,"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';"))
            if dst_version != src_version:
                raise RuntimeError(f"alembic mismatch backup={dst_version} production={src_version}")
            if dst_tables != src_tables:
                raise RuntimeError(f"table count mismatch backup={dst_tables} production={src_tables}")
            print(json.dumps({"status":"sucesso","arquivo":latest,"remote_bytes":remote_bytes,
                "dump_bytes":clear_bytes,"alembic_version":dst_version,"tabelas_publicas":dst_tables,
                "executado_em":datetime.now(timezone.utc).isoformat(),
                "duracao_segundos":round(time.monotonic()-started,2)}, sort_keys=True))
            return 0
    finally:
        if created:
            subprocess.run(["dropdb","-h",c["host"],"-p",c["port"],"-U",c["user"],"--if-exists",target],
                           env=pg_env(c), check=False, capture_output=True, text=True)

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"status":"erro","erro":f"{type(exc).__name__}: {str(exc)[:800]}"}))
        raise SystemExit(1)
