#!/usr/bin/env python3
"""Valida e, opcionalmente, restaura backups Fernet do EJC.

O backup offsite atual produz dois artefatos:

- ``ejc_backup_<UTC>_db.dump.enc``;
- ``ejc_backup_<UTC>_uploads.tar.gz.enc``.

Por padrão este utilitário decifra em diretório temporário, valida o dump com
``pg_restore --list`` e inspeciona o ``tar.gz`` contra path traversal, links e
tipos especiais. Os arquivos em claro são removidos ao final.

A restauração de prova é opt-in com ``--restore-test`` e exige
``RESTORE_TEST_DATABASE_URL`` apontando para banco explicitamente descartável.
Para disaster recovery existe ``--export-clear-dir``: ele exporta os arquivos
já validados com permissões restritas, para uso consciente pelo script guiado
``restaurar_backup.sh``. A chave nunca é aceita na linha de comando para não
aparecer em ``ps``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse

from cryptography.fernet import Fernet, InvalidToken

ARTIFACT_RE = re.compile(
    r"^ejc_backup_(?P<timestamp>\d{8}T\d{6}Z)_"
    r"(?P<kind>db\.dump|uploads\.tar\.gz)\.enc$"
)
DISPOSABLE_DB_RE = re.compile(
    r"(?:^|[_-])(?:test|teste|homolog|homologacao|restore|restauracao|dr)"
    r"(?:[_-]|$)",
    re.IGNORECASE,
)
PRODUCTION_DB_ENV_NAMES = ("DATABASE_URL_SYNC", "DATABASE_URL")


class RestoreValidationError(RuntimeError):
    """Erro operacional seguro, sem conteúdo sensível."""


@dataclass(frozen=True)
class DatabaseTarget:
    host: str
    port: int
    user: str
    password: str
    database: str

    @property
    def identity(self) -> tuple[str, int, str]:
        """Identidade física do alvo; usuário diferente não torna o banco seguro."""
        return (self.host.lower(), self.port, self.database)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_artifact(path: Path, expected_kind: str) -> str:
    if not path.is_file():
        raise RestoreValidationError(f"Artefato não encontrado: {path}")
    match = ARTIFACT_RE.fullmatch(path.name)
    if not match:
        raise RestoreValidationError(
            "Nome de artefato inválido. Esperado "
            "ejc_backup_<AAAAmmddTHHMMSSZ>_<tipo>.enc"
        )
    if match.group("kind") != expected_kind:
        raise RestoreValidationError(
            f"Artefato {path.name} não corresponde ao tipo {expected_kind}"
        )
    return match.group("timestamp")


def validate_pair(db_path: Path, uploads_path: Path | None) -> str:
    timestamp = parse_artifact(db_path, "db.dump")
    if uploads_path is not None:
        uploads_timestamp = parse_artifact(uploads_path, "uploads.tar.gz")
        if uploads_timestamp != timestamp:
            raise RestoreValidationError(
                "Dump e uploads pertencem a execuções diferentes de backup"
            )
    return timestamp


def load_fernet_key(key_file: Path | None = None) -> bytes:
    if key_file is not None:
        if not key_file.is_file():
            raise RestoreValidationError("Arquivo da chave de backup não encontrado")
        raw = key_file.read_text(encoding="utf-8").strip()
    else:
        raw = os.getenv("BACKUP_ENCRYPTION_KEY", "").strip()
    if not raw:
        raise RestoreValidationError(
            "BACKUP_ENCRYPTION_KEY ausente; defina no ambiente ou use --key-file"
        )
    try:
        Fernet(raw.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise RestoreValidationError("Chave Fernet de backup inválida") from exc
    return raw.encode("ascii")


def decrypt_artifact(source: Path, destination: Path, key: bytes) -> int:
    try:
        token = source.read_bytes()
        clear = Fernet(key).decrypt(token)
    except InvalidToken as exc:
        raise RestoreValidationError(
            f"Falha ao decifrar {source.name}: chave incorreta ou artefato corrompido"
        ) from exc
    destination.write_bytes(clear)
    destination.chmod(0o600)
    return len(clear)


def require_binary(name: str) -> str:
    binary = shutil.which(name)
    if not binary:
        raise RestoreValidationError(f"Binário obrigatório não encontrado: {name}")
    return binary


def inspect_pg_dump(path: Path, timeout: int) -> int:
    pg_restore = require_binary("pg_restore")
    result = subprocess.run(
        [pg_restore, "--list", str(path)],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise RestoreValidationError(
            f"pg_restore --list rejeitou o dump (código {result.returncode})"
        )
    object_count = sum(
        1 for line in result.stdout.splitlines() if line and line[0].isdigit()
    )
    if object_count <= 0:
        raise RestoreValidationError(
            "Dump PostgreSQL vazio ou sem objetos restauráveis"
        )
    return object_count


def inspect_uploads_tar(path: Path) -> tuple[int, int]:
    file_count = 0
    total_bytes = 0
    try:
        with tarfile.open(path, mode="r:gz") as archive:
            for member in archive.getmembers():
                posix = PurePosixPath(member.name)
                parts = posix.parts
                if posix.is_absolute() or ".." in parts:
                    raise RestoreValidationError(
                        f"Entrada insegura no arquivo de uploads: {member.name}"
                    )
                if not parts or parts[0] != "uploads":
                    raise RestoreValidationError(
                        "Arquivo de uploads contém entrada fora da raiz uploads/"
                    )
                if member.issym() or member.islnk():
                    raise RestoreValidationError(
                        f"Links não são permitidos no backup de uploads: {member.name}"
                    )
                if not (member.isfile() or member.isdir()):
                    raise RestoreValidationError(
                        f"Tipo especial não permitido no backup: {member.name}"
                    )
                if member.isfile():
                    file_count += 1
                    total_bytes += member.size
    except (tarfile.TarError, OSError) as exc:
        raise RestoreValidationError(
            "Arquivo de uploads inválido ou corrompido"
        ) from exc
    return file_count, total_bytes


def parse_database_url(raw_url: str) -> DatabaseTarget:
    parsed = urlparse(raw_url)
    if not parsed.scheme.startswith("postgresql"):
        raise RestoreValidationError(
            "RESTORE_TEST_DATABASE_URL deve ser PostgreSQL"
        )
    database = unquote((parsed.path or "").lstrip("/"))
    user = unquote(parsed.username or "")
    if not database or not user:
        raise RestoreValidationError(
            "RESTORE_TEST_DATABASE_URL deve informar usuário e banco"
        )
    return DatabaseTarget(
        host=parsed.hostname or "localhost",
        port=parsed.port or 5432,
        user=user,
        password=unquote(parsed.password or ""),
        database=database,
    )


def ensure_disposable_target(target: DatabaseTarget) -> None:
    if not DISPOSABLE_DB_RE.search(target.database):
        raise RestoreValidationError(
            "Banco alvo não parece descartável. O nome deve conter test, teste, "
            "homolog, restore, restauracao ou dr."
        )
    for env_name in PRODUCTION_DB_ENV_NAMES:
        production_url = os.getenv(env_name, "").strip()
        if not production_url:
            continue
        try:
            production = parse_database_url(production_url)
        except RestoreValidationError:
            continue
        if production.identity == target.identity:
            raise RestoreValidationError(
                f"Banco alvo coincide com {env_name}; restauração recusada"
            )


def database_command_env(target: DatabaseTarget) -> dict[str, str]:
    env = dict(os.environ)
    if target.password:
        env["PGPASSWORD"] = target.password
    else:
        env.pop("PGPASSWORD", None)
    return env


def restore_database(path: Path, target: DatabaseTarget, timeout: int) -> int:
    ensure_disposable_target(target)
    pg_restore = require_binary("pg_restore")
    env = database_command_env(target)
    command = [
        pg_restore,
        "-h",
        target.host,
        "-p",
        str(target.port),
        "-U",
        target.user,
        "-d",
        target.database,
        "--clean",
        "--if-exists",
        "--no-owner",
        str(path),
    ]
    result = subprocess.run(
        command,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise RestoreValidationError(
            f"pg_restore falhou no banco descartável (código {result.returncode})"
        )

    psql = require_binary("psql")
    count_result = subprocess.run(
        [
            psql,
            "-h",
            target.host,
            "-p",
            str(target.port),
            "-U",
            target.user,
            "-d",
            target.database,
            "-Atc",
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'public';",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=min(timeout, 120),
        check=False,
    )
    if count_result.returncode != 0:
        raise RestoreValidationError(
            "Banco restaurado, mas a consulta de sanidade falhou"
        )
    try:
        table_count = int(count_result.stdout.strip())
    except ValueError as exc:
        raise RestoreValidationError(
            "Contagem de tabelas restauradas inválida"
        ) from exc
    if table_count <= 0:
        raise RestoreValidationError(
            "Restauração concluída sem tabelas no schema public"
        )
    return table_count


def extract_uploads(path: Path, output_dir: Path) -> int:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise RestoreValidationError(
            "Diretório de restauração dos uploads deve estar vazio"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir.chmod(0o700)
    file_count, _ = inspect_uploads_tar(path)
    with tarfile.open(path, mode="r:gz") as archive:
        archive.extractall(output_dir)
    return file_count


def export_clear_artifacts(
    db_path: Path,
    uploads_path: Path | None,
    output_dir: Path,
) -> dict[str, str]:
    """Exporta dados em claro somente após validação, com permissões restritas."""
    if output_dir.exists() and any(output_dir.iterdir()):
        raise RestoreValidationError(
            "Diretório de exportação em claro deve estar vazio"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir.chmod(0o700)

    exported: dict[str, str] = {}
    db_output = output_dir / "db.dump"
    shutil.copyfile(db_path, db_output)
    db_output.chmod(0o600)
    exported["db.dump"] = str(db_output)

    if uploads_path is not None:
        uploads_output = output_dir / "uploads.tar.gz"
        shutil.copyfile(uploads_path, uploads_output)
        uploads_output.chmod(0o600)
        exported["uploads.tar.gz"] = str(uploads_output)
    return exported


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Valida e opcionalmente restaura backups cifrados do EJC"
    )
    parser.add_argument("db_artifact", type=Path)
    parser.add_argument("uploads_artifact", type=Path, nargs="?")
    parser.add_argument(
        "--key-file",
        type=Path,
        help=(
            "arquivo somente leitura contendo a chave Fernet; "
            "a chave não vai no argv"
        ),
    )
    parser.add_argument(
        "--restore-test",
        action="store_true",
        help=(
            "restaura em RESTORE_TEST_DATABASE_URL, "
            "obrigatoriamente descartável"
        ),
    )
    parser.add_argument(
        "--uploads-output-dir",
        type=Path,
        help="diretório vazio para restaurar uploads no modo --restore-test",
    )
    parser.add_argument(
        "--export-clear-dir",
        type=Path,
        help=(
            "exporta db.dump/uploads.tar.gz já validados; contém PII e deve ser "
            "apagado após o procedimento"
        ),
    )
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--json-output", type=Path)
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    timestamp = validate_pair(args.db_artifact, args.uploads_artifact)
    key = load_fernet_key(args.key_file)

    manifest: dict[str, object] = {
        "status": "validado",
        "timestamp_backup": timestamp,
        "modo": "restore-test" if args.restore_test else "verify-only",
        "artefatos": [],
    }

    with tempfile.TemporaryDirectory(prefix="ejc_restore_verify_") as temp_dir:
        temp = Path(temp_dir)
        db_clear = temp / "db.dump"
        db_size = decrypt_artifact(args.db_artifact, db_clear, key)
        db_objects = inspect_pg_dump(db_clear, args.timeout)
        manifest["artefatos"].append(
            {
                "tipo": "db.dump",
                "arquivo_cifrado": args.db_artifact.name,
                "sha256_cifrado": sha256_file(args.db_artifact),
                "sha256_decifrado": sha256_file(db_clear),
                "bytes_decifrados": db_size,
                "objetos_pg_restore": db_objects,
            }
        )

        uploads_clear: Path | None = None
        if args.uploads_artifact is not None:
            uploads_clear = temp / "uploads.tar.gz"
            uploads_size = decrypt_artifact(
                args.uploads_artifact,
                uploads_clear,
                key,
            )
            upload_files, upload_bytes = inspect_uploads_tar(uploads_clear)
            manifest["artefatos"].append(
                {
                    "tipo": "uploads.tar.gz",
                    "arquivo_cifrado": args.uploads_artifact.name,
                    "sha256_cifrado": sha256_file(args.uploads_artifact),
                    "sha256_decifrado": sha256_file(uploads_clear),
                    "bytes_decifrados": uploads_size,
                    "arquivos": upload_files,
                    "bytes_conteudo": upload_bytes,
                }
            )

        if args.export_clear_dir is not None:
            exported = export_clear_artifacts(
                db_clear,
                uploads_clear,
                args.export_clear_dir,
            )
            manifest["exportacao_em_claro"] = {
                "diretorio": str(args.export_clear_dir),
                "arquivos": exported,
                "aviso": "contém PII; apagar com segurança após a restauração",
            }

        if args.restore_test:
            raw_target = os.getenv("RESTORE_TEST_DATABASE_URL", "").strip()
            if not raw_target:
                raise RestoreValidationError(
                    "--restore-test exige RESTORE_TEST_DATABASE_URL no ambiente"
                )
            target = parse_database_url(raw_target)
            tables = restore_database(db_clear, target, args.timeout)
            manifest["banco_restaurado"] = {
                "host": target.host,
                "port": target.port,
                "database": target.database,
                "tabelas_public": tables,
            }
            if uploads_clear is not None:
                if args.uploads_output_dir is None:
                    raise RestoreValidationError(
                        "Backup contém uploads; informe --uploads-output-dir "
                        "no restore-test"
                    )
                restored_files = extract_uploads(
                    uploads_clear,
                    args.uploads_output_dir,
                )
                manifest["uploads_restaurados"] = {
                    "diretorio": str(args.uploads_output_dir),
                    "arquivos": restored_files,
                }
            manifest["status"] = "restaurado_em_ambiente_descartavel"

    return manifest


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        manifest = run(args)
    except (RestoreValidationError, subprocess.TimeoutExpired) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2

    rendered = json.dumps(manifest, ensure_ascii=False, indent=2)
    print(rendered)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
