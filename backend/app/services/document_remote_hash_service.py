"""SHA-256 streaming de objeto remoto via rclone sem materializar bytes em RAM.

O adapter Drive atual do GED possui métodos de download que retornam ``bytes``.
Este módulo é uma primitiva separada para backfill/rescan: copia o objeto remoto
para um arquivo temporário 0600 em diretório de trabalho explícito e reutiliza o
hash local streaming. O temporário é removido em sucesso, erro e cancelamento.

Não há defaults de remote/config/workdir derivados de ambiente e nenhum detalhe
do provider/path é propagado em mensagens de erro.
"""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.services.document_hash_service import (
    HashDocumentoCalculado,
    calcular_sha256_local,
)

_REMOTE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


class HashRemotoError(RuntimeError):
    pass


class HashRemotoConfiguracaoError(HashRemotoError):
    pass


class HashRemotoIndisponivelError(HashRemotoError):
    pass


@dataclass(frozen=True, slots=True)
class ConfiguracaoHashRclone:
    config_path: Path
    remote: str
    work_dir: Path
    timeout_seconds: int = 300

    def __post_init__(self) -> None:
        if not _REMOTE_RE.fullmatch(self.remote):
            raise HashRemotoConfiguracaoError("remote rclone inválido")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, int)
            or not 1 <= self.timeout_seconds <= 3600
        ):
            raise HashRemotoConfiguracaoError("timeout rclone inválido")


def _validar_path_remoto(remote_path: str) -> str:
    bruto = str(remote_path or "").strip()
    rel = PurePosixPath(bruto)
    if (
        not bruto
        or rel.is_absolute()
        or "\\" in bruto
        or ":" in bruto
        or any(part in {"", ".", ".."} for part in rel.parts)
    ):
        raise HashRemotoConfiguracaoError("path remoto inválido")
    return rel.as_posix()


def _validar_arquivo_config(path: Path) -> Path:
    try:
        info = os.lstat(path)
    except OSError:
        raise HashRemotoConfiguracaoError("configuração rclone indisponível") from None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise HashRemotoConfiguracaoError("configuração rclone inválida")
    if not os.access(path, os.R_OK):
        raise HashRemotoConfiguracaoError("configuração rclone indisponível")
    return path


def _validar_work_dir(path: Path) -> Path:
    try:
        info = os.lstat(path)
    except OSError:
        raise HashRemotoConfiguracaoError("diretório temporário indisponível") from None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise HashRemotoConfiguracaoError("diretório temporário inválido")
    if not os.access(path, os.W_OK | os.X_OK):
        raise HashRemotoConfiguracaoError("diretório temporário indisponível")
    return path.resolve()


def _copiar_remoto_sync(
    config: ConfiguracaoHashRclone,
    remote_path: str,
) -> Path:
    config_path = _validar_arquivo_config(config.config_path)
    work_dir = _validar_work_dir(config.work_dir)
    binario = shutil.which("rclone")
    if not binario:
        raise HashRemotoIndisponivelError("rclone indisponível")

    fd, nome = tempfile.mkstemp(
        prefix=".ged-remote-hash-",
        suffix=".tmp",
        dir=work_dir,
    )
    os.close(fd)
    temp_path = Path(nome)
    try:
        # mkstemp já nasce owner-only; reforço defensivo contra umask incomum.
        os.chmod(temp_path, 0o600)
        try:
            resultado = subprocess.run(
                [
                    binario,
                    "--config",
                    str(config_path),
                    "copyto",
                    f"{config.remote}:{remote_path}",
                    str(temp_path),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=config.timeout_seconds,
            )
        except (subprocess.TimeoutExpired, OSError):
            raise HashRemotoIndisponivelError("objeto remoto indisponível para hash") from None
        if resultado.returncode != 0:
            raise HashRemotoIndisponivelError("objeto remoto indisponível para hash")
        return temp_path
    except BaseException:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


async def calcular_sha256_remoto_rclone(
    config: ConfiguracaoHashRclone,
    remote_path: str,
    *,
    expected_size: int | None = None,
) -> HashDocumentoCalculado:
    """Copia remotamente para staging temporário e calcula SHA em O(1 MiB)."""

    remoto = _validar_path_remoto(remote_path)
    tarefa_copia = asyncio.create_task(
        asyncio.to_thread(_copiar_remoto_sync, config, remoto)
    )
    temp_path: Path | None = None
    try:
        try:
            temp_path = await asyncio.shield(tarefa_copia)
        except asyncio.CancelledError:
            # A thread/subprocess não pode ser abandonada: esperar conclusão e
            # remover eventual temporário antes de repropagar cancelamento.
            try:
                temp_path = await tarefa_copia
            except BaseException:
                temp_path = None
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise

        return await calcular_sha256_local(
            temp_path.parent,
            temp_path.name,
            expected_size=expected_size,
        )
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
