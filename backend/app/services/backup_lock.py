"""Exclusão mútua cross-process/cross-container para o motor de backup.

O lock reside em ``BACKUP_DIR`` (volume ``backups_data``), compartilhado por
backend, ``docker exec`` e ``docker compose run backend`` no mesmo host.

Propriedades:
- O(1) tempo/memória para adquirir/liberar;
- ``fcntl.flock`` é liberado automaticamente pelo kernel em exit/crash;
- abertura por ``dir_fd`` + ``O_NOFOLLOW`` quando disponível reduz TOCTOU e
  impede seguir symlink no arquivo de lock;
- arquivo regular, link-count 1 e modo 0600 são invariantes bloqueantes;
- BACKUP_DIR ausente é erro de infraestrutura: o código nunca cria storage de
  continuidade silenciosamente;
- erro de infraestrutura nunca degrada para execução sem lock.
"""
from __future__ import annotations

import errno
import fcntl
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType


_LOCK_NAME = ".ejc-backup.lock"


class BackupLockError(RuntimeError):
    """Falha ao preparar/validar a exclusão mútua de backup."""


class BackupAlreadyRunning(BackupLockError):
    """Outro processo/container já detém o mutex de backup."""


@dataclass(slots=True)
class BackupProcessLock:
    """Context manager de ``flock`` sobre o volume compartilhado de backups."""

    backup_dir: Path
    _dir_fd: int | None = None
    _lock_fd: int | None = None

    @classmethod
    def from_path(cls, backup_dir: str | os.PathLike[str]) -> "BackupProcessLock":
        raw = os.fspath(backup_dir)
        if not raw or "\x00" in raw:
            raise BackupLockError("BACKUP_DIR inválido para o mutex de backup")
        return cls(backup_dir=Path(raw))

    def _open_directory(self) -> int:
        """Abre BACKUP_DIR existente sem seguir symlink e valida permissões."""
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_DIRECTORY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)

        try:
            fd = os.open(self.backup_dir, flags)
        except FileNotFoundError as exc:
            raise BackupLockError(
                "BACKUP_DIR ausente; volume de continuidade não está montado"
            ) from exc
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise BackupLockError("BACKUP_DIR não pode ser symlink") from exc
            raise BackupLockError(
                f"não foi possível abrir BACKUP_DIR com segurança: {exc.strerror or exc}"
            ) from exc

        try:
            info = os.fstat(fd)
            if not stat.S_ISDIR(info.st_mode):
                raise BackupLockError("BACKUP_DIR não é diretório")
            if stat.S_IMODE(info.st_mode) & 0o022:
                raise BackupLockError(
                    "BACKUP_DIR é gravável por grupo/outros; mutex não é confiável"
                )
            return fd
        except Exception:
            os.close(fd)
            raise

    @staticmethod
    def _lock_flags() -> int:
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        return flags

    def _open_lock_file(self, dir_fd: int) -> int:
        try:
            fd = os.open(
                _LOCK_NAME,
                self._lock_flags(),
                0o600,
                dir_fd=dir_fd,
            )
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise BackupLockError("arquivo de mutex é symlink") from exc
            raise BackupLockError(
                f"não foi possível abrir mutex de backup: {exc.strerror or exc}"
            ) from exc

        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise BackupLockError("mutex de backup não é arquivo regular")
            if info.st_nlink != 1:
                raise BackupLockError("mutex de backup possui hard links")

            os.fchmod(fd, 0o600)
            after = os.fstat(fd)
            if stat.S_IMODE(after.st_mode) != 0o600:
                raise BackupLockError("mutex de backup não ficou em modo 0600")
            return fd
        except Exception:
            os.close(fd)
            raise

    def acquire(self) -> "BackupProcessLock":
        """Adquire exclusão não bloqueante ou levanta ``BackupAlreadyRunning``."""
        if self._lock_fd is not None or self._dir_fd is not None:
            raise BackupLockError("instância de mutex já utilizada")

        dir_fd = self._open_directory()
        try:
            lock_fd = self._open_lock_file(dir_fd)
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                os.close(lock_fd)
                raise BackupAlreadyRunning("já existe backup em execução") from exc
            except OSError as exc:
                os.close(lock_fd)
                if exc.errno in {errno.EACCES, errno.EAGAIN}:
                    raise BackupAlreadyRunning("já existe backup em execução") from exc
                raise BackupLockError(
                    f"falha ao adquirir mutex de backup: {exc.strerror or exc}"
                ) from exc

            self._dir_fd = dir_fd
            self._lock_fd = lock_fd
            return self
        except Exception:
            os.close(dir_fd)
            raise

    def release(self) -> None:
        """Libera lock e descritores; idempotente para cleanup em ``finally``."""
        lock_fd, dir_fd = self._lock_fd, self._dir_fd
        self._lock_fd = None
        self._dir_fd = None

        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)
        if dir_fd is not None:
            os.close(dir_fd)

    def __enter__(self) -> "BackupProcessLock":
        if self._lock_fd is None:
            return self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()


def open_backup_dir_fd(backup_dir: str | os.PathLike[str]) -> int:
    """Abre BACKUP_DIR com as mesmas invariantes do mutex; caller fecha o fd."""
    return BackupProcessLock.from_path(backup_dir)._open_directory()


def backup_process_lock(backup_dir: str | os.PathLike[str]) -> BackupProcessLock:
    """Retorna context manager ainda não adquirido para uso com ``with``."""
    return BackupProcessLock.from_path(backup_dir)


def acquire_backup_lock(backup_dir: str | os.PathLike[str]) -> BackupProcessLock:
    """Adquire imediatamente o mutex; caller deve executar ``release``."""
    return BackupProcessLock.from_path(backup_dir).acquire()
