#!/usr/bin/env python3
"""Drill LOCAL de backup/restore do EJC — prova de continuidade sem Drive/VPS.

O que faz, ponta a ponta e SEM sair da máquina:

  1. Lê métricas do banco de ORIGEM (já semeado) apontado por DATABASE_URL_SYNC:
     versão Alembic, extensões instaladas, nº de tabelas BASE e a contagem de
     linhas de um conjunto de "tabelas-chave".
  2. `pg_dump -Fc` da origem.
  3. `createdb` de um banco DESTINO vazio (nome aleatório, a partir de template0).
  4. `pg_restore` do dump no destino.
  5. VERIFICA a integridade comparando origem × destino:
        - mesma versão em `alembic_version`;
        - mesmo nº de tabelas BASE em `public`;
        - mesma contagem de linhas em cada tabela-chave existente;
        - extensões pgvector (`vector`) e `pg_trgm` presentes no destino;
        - (bônus) se existir uma tabela com coluna `vector`, os valores do vetor
          batem byte a byte — prova que o DADO pgvector, não só a extensão,
          sobrevive ao ciclo dump→restore.
  6. REMOVE o banco destino (sempre, no finally).

Diferença para `restore_drill.py` (que também existe): aquele é o GATE de
continuidade com dump CIFRADO (Fernet) + marcador, exigindo chave. Este é o drill
LOCAL, sem cifragem, focado nas verificações de schema/dados que o gate não faz
(extensões e linhas-chave). Os dois se complementam.

Segurança:
  - Só executa com DRILL_ALLOW=1 (evita rodada acidental).
  - O destino tem nome aleatório e NUNCA pode coincidir com o banco de origem.
  - Nenhum segredo é impresso no relatório.

Uso:
    export DATABASE_URL_SYNC='postgresql://user:pass@host:5432/ejc_db'
    DRILL_ALLOW=1 python3 scripts/backup/drill_local_backup_restore.py

Variáveis opcionais:
    DRILL_KEY_TABLES   CSV de tabelas-chave (default: clients,cases,users,
                       deadlines,knowledge_chunks). Tabelas ausentes na origem
                       são ignoradas — o drill funciona em qualquer revisão.
    DRILL_REPORT       Caminho do relatório JSON (default: ./drill-local-report.json).
"""

from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

_DEFAULT_KEY_TABLES = "clients,cases,users,deadlines,knowledge_chunks"
_EXTENSOES_OBRIGATORIAS = ("vector", "pg_trgm")


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
    args: list[str], conn: PgConn, *, timeout: int = 300
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


def _coletar_metricas(
    conn: PgConn, database: str, key_tables: list[str]
) -> dict[str, object]:
    """Snapshot de integridade de um banco: versão Alembic, extensões, nº de
    tabelas e contagem das tabelas-chave existentes."""
    alembic = _psql(
        conn, "SELECT version_num FROM alembic_version LIMIT 1;", database=database
    )
    tabelas = int(
        _psql(
            conn,
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema='public' AND table_type='BASE TABLE';",
            database=database,
        )
    )
    ext_raw = _psql(
        conn,
        "SELECT extname||'='||extversion FROM pg_extension ORDER BY extname;",
        database=database,
    )
    extensoes = dict(
        linha.split("=", 1) for linha in ext_raw.splitlines() if "=" in linha
    )

    # Só conta as tabelas-chave que realmente existem (drill robusto entre revisões).
    existentes_raw = _psql(
        conn,
        "SELECT tablename FROM pg_tables WHERE schemaname='public' "
        "AND tablename = ANY (string_to_array(%s, ','));"
        % _quote(",".join(key_tables)),
        database=database,
    )
    existentes = [t for t in existentes_raw.splitlines() if t]
    contagens: dict[str, int] = {}
    for t in sorted(existentes):
        contagens[t] = int(
            _psql(conn, f'SELECT COUNT(*) FROM "{t}";', database=database)
        )

    # Bônus: round-trip de DADO pgvector, se houver alguma tabela com coluna vector.
    vec_amostra: str | None = None
    vec_tabela = _psql(
        conn,
        "SELECT c.table_name||'.'||c.column_name FROM information_schema.columns c "
        "WHERE c.table_schema='public' AND c.udt_name='vector' ORDER BY 1 LIMIT 1;",
        database=database,
    ).strip()
    if vec_tabela:
        tab, col = vec_tabela.split(".", 1)
        vec_amostra = _psql(
            conn,
            f"SELECT COALESCE(string_agg(\"{col}\"::text, '|' ORDER BY \"{col}\"::text), '') "
            f'FROM "{tab}";',
            database=database,
        )

    return {
        "alembic_version": alembic,
        "tabelas_base": tabelas,
        "extensoes": extensoes,
        "linhas_chave": contagens,
        "amostra_vetor": vec_amostra,
        "amostra_vetor_origem": vec_tabela or None,
    }


def _quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def main() -> int:
    if os.getenv("DRILL_ALLOW") != "1":
        print(
            "DRILL_ALLOW=1 é obrigatório para executar o drill local.", file=sys.stderr
        )
        return 2

    raw_url = (os.getenv("DATABASE_URL_SYNC") or "").strip()
    if not raw_url:
        print("DATABASE_URL_SYNC ausente.", file=sys.stderr)
        return 2

    key_tables = [
        t.strip()
        for t in (os.getenv("DRILL_KEY_TABLES") or _DEFAULT_KEY_TABLES).split(",")
        if t.strip()
    ]
    report_path = Path(os.getenv("DRILL_REPORT", "drill-local-report.json"))

    started = time.monotonic()
    conn = PgConn.from_url(raw_url)
    suffix = secrets.token_hex(6)
    safe_source = re.sub(r"[^a-zA-Z0-9_]", "_", conn.database)[:36]
    target_db = f"{safe_source}_drill_{suffix}"[:63]
    if target_db == conn.database:
        print(
            "Nome do banco destino coincide com a origem — abortado.", file=sys.stderr
        )
        return 2

    report: dict[str, object] = {
        "status": "erro",
        "executado_em": datetime.now(timezone.utc).isoformat(),
        "banco_origem": conn.database,
        "banco_destino_temporario": target_db,
    }
    target_created = False

    try:
        import tempfile

        origem = _coletar_metricas(conn, conn.database, key_tables)

        with tempfile.TemporaryDirectory(prefix="ejc_drill_") as tmp:
            dump = Path(tmp) / "ejc.dump"
            _run(
                [
                    "pg_dump",
                    *conn.args(),
                    "-Fc",
                    "--no-owner",
                    "--no-privileges",
                    "-f",
                    str(dump),
                ],
                conn,
                timeout=600,
            )
            dump_bytes = dump.stat().st_size
            if dump_bytes <= 0:
                raise RuntimeError("pg_dump produziu arquivo vazio.")

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
                    str(dump),
                ],
                conn,
                timeout=900,
            )

            destino = _coletar_metricas(conn, target_db, key_tables)

        # ── Verificações de integridade ──────────────────────────────────────
        falhas: list[str] = []
        if destino["alembic_version"] != origem["alembic_version"]:
            falhas.append(
                f"alembic_version: origem={origem['alembic_version']} "
                f"destino={destino['alembic_version']}"
            )
        if destino["tabelas_base"] != origem["tabelas_base"]:
            falhas.append(
                f"tabelas_base: origem={origem['tabelas_base']} destino={destino['tabelas_base']}"
            )
        if destino["linhas_chave"] != origem["linhas_chave"]:
            falhas.append(
                f"linhas_chave divergem: origem={origem['linhas_chave']} "
                f"destino={destino['linhas_chave']}"
            )
        for ext in _EXTENSOES_OBRIGATORIAS:
            if ext not in destino["extensoes"]:  # type: ignore[operator]
                falhas.append(f"extensão ausente no destino: {ext}")
        if origem["amostra_vetor"] != destino["amostra_vetor"]:
            falhas.append("amostra de dado pgvector divergiu após restore")

        report.update(
            {
                "duracao_segundos": round(time.monotonic() - started, 2),
                "dump_bytes": dump_bytes,
                "tabelas_chave_verificadas": sorted(origem["linhas_chave"].keys()),  # type: ignore[union-attr]
                "origem": origem,
                "destino": destino,
            }
        )

        if falhas:
            report["status"] = "erro"
            report["falhas"] = falhas
            print(
                json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
                file=sys.stderr,
            )
            return 1

        report["status"] = "sucesso"
        _resumo(origem, report)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        report.update(
            {
                "duracao_segundos": round(time.monotonic() - started, 2),
                "erro": f"{type(exc).__name__}: {str(exc)[:800]}",
            }
        )
        print(json.dumps(report, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1
    finally:
        if target_created:
            try:
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
                        target_db,
                    ],
                    conn,
                )
                report["banco_temporario_removido"] = True
            except Exception as exc:
                report["banco_temporario_removido"] = False
                report["cleanup_error"] = f"{type(exc).__name__}"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _resumo(origem: dict[str, object], report: dict[str, object]) -> None:
    linhas = origem["linhas_chave"]  # type: ignore[index]
    print("── Drill local de backup/restore: SUCESSO ─────────────────────────")
    print(f"  alembic_version .... {origem['alembic_version']}")
    print(f"  tabelas base ....... {origem['tabelas_base']} (origem == destino)")
    print(f"  extensões .......... {', '.join(sorted(origem['extensoes']))}")  # type: ignore[arg-type]
    print(f"  linhas-chave ....... {linhas}")
    print(
        f"  dado pgvector ...... round-trip OK ({origem.get('amostra_vetor_origem')})"
    )
    print(f"  duração ............ {report['duracao_segundos']}s")
    print("───────────────────────────────────────────────────────────────────")


if __name__ == "__main__":
    raise SystemExit(main())
