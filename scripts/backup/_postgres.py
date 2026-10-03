"""Helpers PostgreSQL dos drills; não autoriza execução nem escolhe banco."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from urllib.parse import unquote, urlparse


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
    runner=None,
) -> subprocess.CompletedProcess[str]:
    try:
        return (runner or subprocess.run)(
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


def psql(conn: PgConn, sql: str, *, database: str | None = None, runner=_run) -> str:
    result = runner(
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
