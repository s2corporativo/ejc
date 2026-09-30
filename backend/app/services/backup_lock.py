"""Exclusão mútua cross-process/cross-container para o motor de backup.

O lock reside em ``BACKUP_DIR`` (volume ``backups_data``), compartilhado por
backend, ``docker exec`` e ``docker compose run backend`` no mesmo host.

Propriedades (comuns às duas plataformas):
- O(1) tempo/memória para adquirir/liberar;
- o lock é liberado automaticamente pelo SO em exit/crash do dono;
- arquivo regular e link-count 1 são invariantes bloqueantes;
- BACKUP_DIR ausente é erro de infraestrutura: o código nunca cria storage de
  continuidade silenciosamente;
- erro de infraestrutura nunca degrada para execução sem lock.

Semântica POSIX (Linux, produção)
---------------------------------
A abertura ancorada em ``dir_fd`` + ``O_NOFOLLOW`` reduz TOCTOU e impede seguir
symlink tanto no diretório quanto no arquivo de lock; ``fchmod``/``fstat``
fixam o modo 0600; e ``stat.S_IMODE(mode) & 0o022`` recusa diretório gravável
por grupo/outros. A rejeição de diretório permissivo depende dos bits de modo
POSIX, que o Windows não representa — ver "Limitações explícitas" abaixo.

Semântica Windows (dev)
------------------------
Não existem ``O_NOFOLLOW``, ``dir_fd`` nem abertura de diretório por ``os.open``.
O lock file é portanto aberto por caminho, e a recusa de symlink passa a ser
pós-abertura: ``lstat`` exige arquivo regular e a identidade ``st_dev``/``st_ino``
é comparada contra o descritor já aberto, o que fecha a janela de troca. A
invariantes de arquivo regular e ``st_nlink == 1`` seguem valendo.

A exclusão mútua usa ``msvcrt.locking(fd, LK_NBLCK, 1)`` em 1 byte no offset 0
— o CRT do Windows não tem equivalente de ``flock``, e regions só podem ser
bloqueadas sobre bytes já existentes, então o arquivo é garantido ter 1 byte
antes do lock. A liberação é ``LK_UNLCK``. O CRT reporta contenção como
``EDEADLOCK`` (e não ``EACCES``), então a tradução de errno é explícita em
``_LOCK_CONTENTION_ERRNOS``; qualquer contenção vira ``BackupAlreadyRunning``,
igual ao POSIX.

Limitações explícitas (fail-high, nunca simuladas)
--------------------------------------------------
Dois invariantes são genuinamente inobserváveis no Windows. Nenhum é
aproximado por valor falso:

1. Bits de modo POSIX. ``os.stat`` reporta 0o666/0o777 de qualquer forma e a
   autorização real é por ACL do NTFS. A checagem de modo 0600 e de diretório
   gravável por grupo/outros é *pulada* — não simulada. A redução a esse
   invariante é a razão de a produção não poder rodar no Windows.
2. ``open_backup_dir_fd`` levanta ``BackupLockError`` no Windows em vez de
   devolver algo que não seja um fd. O motor de backup consome esse descritor
   com ``os.listdir``/``os.stat``/``os.unlink`` relativos a ``dir_fd``; devolver
   qualquer outro objeto derrubaria silenciosamente a âncora segura do diretório
   (TOCTOU entre checar e apagar). Fail-high é o comportamento correto.
"""
from __future__ import annotations

import errno
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

if os.name == "posix":  # pragma: no cover - depende da plataforma de execução
    import fcntl
else:  # pragma: no cover - idem
    import msvcrt


_POSIX = os.name == "posix"

# O CRT do Windows mapeia contenção de lock para EDEADLOCK; POSIX usa EAGAIN.
_LOCK_CONTENTION_ERRNOS = frozenset(
    {errno.EACCES, errno.EAGAIN} | ({errno.EDEADLOCK} if not _POSIX else set())
)

_LOCK_NAME = ".ejc-backup.lock"


class BackupLockError(RuntimeError):
    """Falha ao preparar/validar a exclusão mútua de backup."""


class BackupAlreadyRunning(BackupLockError):
    """Outro processo/container já detém o mutex de backup."""


def _take_lock(fd: int) -> None:
    """Tenta tomar o lock exclusivo não bloqueante.

    Levanta ``BlockingIOError``/``OSError`` com errno de contenção; o caller
    traduz para ``BackupAlreadyRunning``.
    """
    if _POSIX:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    else:
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)


def _drop_lock(fd: int) -> None:
    """Libera o lock; ``release`` é idempotente para uso em ``finally``."""
    if _POSIX:
        fcntl.flock(fd, fcntl.LOCK_UN)
    else:
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)


@dataclass(slots=True)
class BackupProcessLock:
    """Context manager de lock sobre o volume compartilhado de backups."""

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
        if not _POSIX:
            raise BackupLockError(
                "open de diretório ancorado (O_NOFOLLOW/dir_fd) não existe no "
                "Windows; o motor de backup exige âncora segura de diretório e "
                "não degrada para abertura por caminho"
            )

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
        if _POSIX:
            flags |= getattr(os, "O_NOFOLLOW", 0)
        return flags

    def _open_lock_file_posix(self, dir_fd: int) -> int:
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

    def _open_lock_file_windows(self) -> int:
        path = self.backup_dir / _LOCK_NAME
        if not self.backup_dir.is_dir():
            raise BackupLockError("BACKUP_DIR ausente; volume de continuidade não está montado")

        try:
            fd = os.open(path, self._lock_flags(), 0o600)
        except OSError as exc:
            raise BackupLockError(
                f"não foi possível abrir mutex de backup: {exc.strerror or exc}"
            ) from exc

        try:
            # Sem O_NOFOLLOW: a recusa de symlink é pós-abertura. lstat precisa
            # ver arquivo regular e a identidade precisa ser a do descritor já
            # aberto — é isso que fecha a janela de troca (TOCTOU).
            link_info = os.lstat(path)
            if not stat.S_ISREG(link_info.st_mode):
                raise BackupLockError("mutex de backup não é arquivo regular")

            info = os.fstat(fd)
            if (info.st_dev, info.st_ino) != (link_info.st_dev, link_info.st_ino):
                raise BackupLockError("mutex de backup foi trocado durante a abertura")
            if info.st_nlink != 1:
                raise BackupLockError("mutex de backup possui hard links")

            # msvcrt.locking só bloqueia bytes existentes: garante 1 byte.
            if os.fstat(fd).st_size < 1:
                os.write(fd, b"\0")
                os.lseek(fd, 0, os.SEEK_SET)
            return fd
        except Exception:
            os.close(fd)
            raise

    def _open_lock_file(self, dir_fd: int | None) -> int:
        if _POSIX:
            return self._open_lock_file_posix(dir_fd)  # type: ignore[arg-type]
        return self._open_lock_file_windows()

    def acquire(self) -> "BackupProcessLock":
        """Adquire exclusão não bloqueante ou levanta ``BackupAlreadyRunning``."""
        if self._lock_fd is not None or self._dir_fd is not None:
            raise BackupLockError("instância de mutex já utilizada")

        dir_fd: int | None = None
        if _POSIX:
            dir_fd = self._open_directory()

        try:
            lock_fd = self._open_lock_file(dir_fd)
        except Exception:
            if dir_fd is not None:
                os.close(dir_fd)
            raise

        try:
            _take_lock(lock_fd)
        except BlockingIOError as exc:
            os.close(lock_fd)
            if dir_fd is not None:
                os.close(dir_fd)
            raise BackupAlreadyRunning("já existe backup em execução") from exc
        except OSError as exc:
            os.close(lock_fd)
            if dir_fd is not None:
                os.close(dir_fd)
            if exc.errno in _LOCK_CONTENTION_ERRNOS:
                raise BackupAlreadyRunning("já existe backup em execução") from exc
            raise BackupLockError(
                f"falha ao adquirir mutex de backup: {exc.strerror or exc}"
            ) from exc
        except Exception:
            os.close(lock_fd)
            if dir_fd is not None:
                os.close(dir_fd)
            raise

        self._dir_fd = dir_fd
        self._lock_fd = lock_fd
        return self

    def release(self) -> None:
        """Libera lock e descritores; idempotente para cleanup em ``finally``."""
        lock_fd, dir_fd = self._lock_fd, self._dir_fd
        self._lock_fd = None
        self._dir_fd = None

        if lock_fd is not None:
            try:
                _drop_lock(lock_fd)
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
