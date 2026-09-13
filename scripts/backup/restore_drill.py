#!/usr/bin/env python3
"""Gate de continuidade: dump cifrado, decifragem e restauração em banco vazio.

Este script é destrutivo apenas para um banco temporário de nome aleatório.
Por segurança, só executa quando RESTORE_DRILL_ALLOW=1.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.backup_service import cifrar_arquivo, decifrar_arquivo  # noqa: E402


@dataclass(frozen=True)
class PgConn:
    host: str
    port: int
    user: str
    password: str
    database: str

    @classmethod
    def from_url(cls, raw: str) -> "PgConn":
        parsed = urlparse(raw)
        if not parsed.hostname or not parsed.username:
            raise RuntimeError("DATABASE_URL_SYNC inválida: host/usuário ausentes.")
        database = unquote((parsed.path or "").lstrip("/"))
        if not database:
            raise RuntimeError("DATABASE_URL_SYNC inválida: banco ausente.")
        return cls(
            host=parsed.hostname,
            port=parsed.port or 5432,
            user=unquote(parsed.username),
            password=unquote(parsed.password or ""),
            database=database,
        )

    def args(self, database: str | None = None) -> list[str]:
        return [
            "-h",
            self.host,
            "-p",
            str(self.port),
            "-U",
            self.user,
            "-d",
            database or self.database,
        ]

    def env(self) -> dict[str, str]:
        return {**os.environ, "PGPASSWORD": self.password}


def _run(
    args: list[str],
    conn: PgConn,
    *,
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            env=conn.env(),
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.CalledProcessError as exc:
        detalhe = (exc.stderr or exc.stdout or "").strip()[:800]
        raise RuntimeError(
            f"Comando PostgreSQL falhou (código {exc.returncode}): {detalhe}"
        ) from exc


def _psql(conn: PgConn, sql: str, *, database: str | None = None) -> str:
    result = _run(
        [
            "psql",
            *conn.args(database),
            "-v",
            "ON_ERROR_STOP=1",
            "-A",
            "-t",
            "-q",
            "-c",
            sql,
        ],
        conn,
    )
    return result.stdout.strip()


def _drop_database(conn: PgConn, database: str) -> None:
    _run(
        [
            "dropdb",
            "-h",
            conn.host,
            "-p",
            str(conn.port),
            "-U",
            conn.user,
            "--if-exists",
            database,
        ],
        conn,
    )


def _write_report(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    if os.getenv("RESTORE_DRILL_ALLOW") != "1":
        print(
            "RESTORE_DRILL_ALLOW=1 é obrigatório para executar a prova de restauração.",
            file=sys.stderr,
        )
        return 2

    raw_url = (os.getenv("DATABASE_URL_SYNC") or "").strip()
    if not raw_url:
        print("DATABASE_URL_SYNC ausente.", file=sys.stderr)
        return 2

    report_path = Path(
        os.getenv("RESTORE_DRILL_REPORT", str(ROOT / "restore-drill-report.json"))
    )
    started = time.monotonic()
    executed_at = datetime.now(timezone.utc)
    conn = PgConn.from_url(raw_url)

    suffix = secrets.token_hex(6)
    safe_source = re.sub(r"[^a-zA-Z0-9_]", "_", conn.database)[:36]
    target_db = f"{safe_source}_restore_{suffix}"[:63]
    marker_table = f"ejc_restore_drill_{suffix}"
    marker_token = secrets.token_hex(24)

    source_marker_created = False
    target_created = False
    report: dict[str, object] = {
        "status": "erro",
        "executado_em": executed_at.isoformat(),
        "banco_origem": conn.database,
        "banco_destino_temporario": target_db,
    }

    try:
        with tempfile.TemporaryDirectory(prefix="ejc_restore_drill_") as tmp:
            tmp_path = Path(tmp)
            # 0o700 e dono-apenas: MAIS restritivo que o 0o644 que a regra sugere.
            # Seguir a regra afrouxaria o diretorio. Ver docs/seguranca/SAST_BASELINE.md
            # nosemgrep: python.lang.security.audit.insecure-file-permissions.insecure-file-permissions
            os.chmod(tmp_path, 0o700)
            clear_dump = tmp_path / "ejc.dump"
            encrypted_dump = tmp_path / "ejc.dump.enc"
            restored_dump = tmp_path / "ejc.restore.dump"

            _psql(
                conn,
                (
                    f'CREATE TABLE public."{marker_table}" ('
                    "token TEXT PRIMARY KEY, "
                    "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());"
                    f'INSERT INTO public."{marker_table}" (token) '
                    f"VALUES ('{marker_token}');"
                ),
            )
            source_marker_created = True

            source_version = _psql(
                conn,
                "SELECT version_num FROM alembic_version LIMIT 1;",
            )
            source_tables = int(
                _psql(
                    conn,
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_type = 'BASE TABLE';",
                )
            )

            _run(
                [
                    "pg_dump",
                    *conn.args(),
                    "-Fc",
                    "--no-owner",
                    "--no-privileges",
                    "-f",
                    str(clear_dump),
                ],
                conn,
                timeout=600,
            )
            os.chmod(clear_dump, 0o600)
            dump_bytes = clear_dump.stat().st_size
            if dump_bytes <= 0:
                raise RuntimeError("pg_dump produziu arquivo vazio.")

            key = (
                os.getenv("RESTORE_DRILL_ENCRYPTION_KEY")
                or os.getenv("BACKUP_ENCRYPTION_KEY")
                or Fernet.generate_key().decode()
            )
            encrypted_bytes = cifrar_arquivo(
                str(clear_dump),
                str(encrypted_dump),
                key,
            )
            os.chmod(encrypted_dump, 0o600)
            clear_dump.unlink()

            restored_bytes = decifrar_arquivo(
                str(encrypted_dump),
                str(restored_dump),
                key,
            )
            os.chmod(restored_dump, 0o600)
            if restored_bytes != dump_bytes:
                raise RuntimeError(
                    "Tamanho do dump restaurado difere do dump original."
                )

            _run(
                [
                    "createdb",
                    "-h",
                    conn.host,
                    "-p",
                    str(conn.port),
                    "-U",
                    conn.user,
                    "-T",
                    "template0",
                    target_db,
                ],
                conn,
            )
            target_created = True

            _run(
                [
                    "pg_restore",
                    "-h",
                    conn.host,
                    "-p",
                    str(conn.port),
                    "-U",
                    conn.user,
                    "-d",
                    target_db,
                    "--exit-on-error",
                    "--no-owner",
                    "--no-privileges",
                    str(restored_dump),
                ],
                conn,
                timeout=900,
            )
            restored_dump.unlink()

            restored_token = _psql(
                conn,
                f'SELECT token FROM public."{marker_table}" LIMIT 1;',
                database=target_db,
            )
            target_version = _psql(
                conn,
                "SELECT version_num FROM alembic_version LIMIT 1;",
                database=target_db,
            )
            target_tables = int(
                _psql(
                    conn,
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_type = 'BASE TABLE';",
                    database=target_db,
                )
            )

            if restored_token != marker_token:
                raise RuntimeError("Marcador de integridade não foi restaurado.")
            if target_version != source_version:
                raise RuntimeError(
                    "Versão Alembic restaurada difere da origem."
                )
            if target_tables != source_tables:
                raise RuntimeError(
                    "Quantidade de tabelas restaurada difere da origem."
                )

            report.update(
                {
                    "status": "sucesso",
                    "duracao_segundos": round(time.monotonic() - started, 2),
                    "dump_bytes": dump_bytes,
                    "dump_cifrado_bytes": encrypted_bytes,
                    "alembic_version": target_version,
                    "tabelas_publicas": target_tables,
                    "marcador_integridade": True,
                    "dump_claro_removido_antes_da_restauracao": True,
                    "banco_temporario_removido": True,
                }
            )
            print(json.dumps(report, ensure_ascii=False, sort_keys=True))
            return 0
    except Exception as exc:
        report.update(
            {
                "status": "erro",
                "duracao_segundos": round(time.monotonic() - started, 2),
                "erro": f"{type(exc).__name__}: {str(exc)[:800]}",
            }
        )
        print(json.dumps(report, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1
    finally:
        cleanup_errors: list[str] = []
        if source_marker_created:
            try:
                _psql(conn, f'DROP TABLE IF EXISTS public."{marker_table}";')
            except Exception as exc:
                cleanup_errors.append(f"marker: {type(exc).__name__}")
        if target_created:
            try:
                _drop_database(conn, target_db)
            except Exception as exc:
                cleanup_errors.append(f"database: {type(exc).__name__}")
        if cleanup_errors:
            report["cleanup_errors"] = cleanup_errors
            report["banco_temporario_removido"] = False
        _write_report(report_path, report)


if __name__ == "__main__":
    raise SystemExit(main())
