"""Exclusão mútua cross-process/cross-container para o motor de backup.

O lock reside em ``BACKUP_DIR`` (volume ``backups_data``), compartilhado por
backend, ``docker exec`` e ``docker compose run backend`` no mesmo host.

Propriedades (comuns às plataformas):
- O(1) tempo/memória para adquirir/liberar;
- o lock é liberado automaticamente pelo kernel/CRT em exit/crash;
- arquivo regular e link-count 1 são invariantes bloqueantes;
- recusa de symlink no arquivo de lock é invariante bloqueante;
- BACKUP_DIR ausente é erro de infraestrutura: o código nunca cria storage de
  continuidade silenciosamente;
- erro de infraestrutura nunca degrada para execução sem lock.

Semântica por plataforma
-------------------------
POSIX (Linux/Docker — caminho de produção, canônico):
- ``fcntl.flock(fd, LOCK_EX | LOCK_NB)``;
- abertura por ``dir_fd`` + ``O_NOFOLLOW`` (quando disponível) reduz TOCTOU e
  impede seguir symlink;
- ``O_NOFOLLOW`` ausente degrada para validação pós-abertura: link-count 1,
  arquivo regular e modo 0600 (``fchmod`` + ``fstat``) são exigidos;
- permissão de grupo/outros no ``BACKUP_DIR`` (``st_mode & 0o022``) é rejeitada;
- ``open_backup_dir_fd`` devolve um ``dir_fd`` utilizável pelas operações
  relativas a diretório do motor de backup.

Windows (somente desenvolvimento/testes — o backup não roda neste SO):
- o mutex é tomado com ``msvcrt.locking(fd, LK_NBLCK, 1)`` sobre 1 byte no
  offset 0 do arquivo, com o mesmo contrato não bloqueante: erro de conteúdo
  (``EACCES``/``EAGAIN``/``EDEADLOCK``) vira ``BackupAlreadyRunning``;
- ``O_NOFOLLOW``/``dir_fd``/``os.open`` de diretório não existem: o arquivo é
  aberto por caminho e a recusa de symlink passa a ser verificada por
  ``lstat`` + comparação de identidade (``st_dev``/``st_ino``) com o descritor
  já aberto, o que detecta tanto symlink na abertura quanto troca do caminho
  depois dela;
- o byte de lock precisa existir: o arquivo é garantido com 1 byte antes de
  bloquear (equivalente funcional do ``flock``);
- o modo POSIX 0600 e a checagem de permissão do diretório NÃO são verificáveis
  no Windows (``os.stat`` reporta 0o666/0o777 e a autorização é por ACL/NTFS):
  a validação é explicitamente ignorada e documentada aqui, nunca simulada;
- ``open_backup_dir_fd`` **falha alto** neste SO: as operações do motor de
  backup são relativas a ``dir_fd``, que o Windows não implementa.
"""
from __future__ import annotations

import errno
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

# Seleção do backend de lock por plataforma. POSIX é o caminho de produção e
# mantém exatamente as mesmas flags/erros de sempre; o resto do módulo só
# ramifica no ramo Windows, deixando o ramo POSIX inalterado.
if os.name == "posix":  # pragma: no branch - Linux/Docker
    import fcntl

    _FLOCK = fcntl
    _MSVCRT = None
else:  # pragma: no cover - exercitado só no Windows de desenvolvimento
    import msvcrt

    _FLOCK = None
    _MSVCRT = msvcrt

_POSIX = os.name == "posix"

_LOCK_NAME = ".ejc-backup.lock"
_LOCK_REGION = 1

# EACCES/EAGAIN: BSD e Linux. EDEADLOCK (errno 36): devolvido pelo CRT do
# Windows (msvcrt.locking) quando o byte já está travado.
_LOCK_CONTENTION_ERRNOS = frozenset({errno.EACCES, errno.EAGAIN})
if hasattr(errno, "EDEADLOCK"):
    _LOCK_CONTENTION_ERRNOS = _LOCK_CONTENTION_ERRNOS | {errno.EDEADLOCK}


class BackupLockError(RuntimeError):
    """Falha ao preparar/validar a exclusão mútua de backup."""


class BackupAlreadyRunning(BackupLockError):
    """Outro processo/container já detém o mutex de backup."""


def _take_lock(fd: int) -> None:
    """Exclui o arquivo de forma não bloqueante; levanta OSError se ocupado."""
    if _POSIX:
        _FLOCK.flock(fd, _FLOCK.LOCK_EX | _FLOCK.LOCK_NB)
        return

    # Windows: 1 byte no offset 0, sem esperar.
    os.lseek(fd, 0, os.SEEK_SET)
    _MSVCRT.locking(fd, _MSVCRT.LK_NBLCK, _LOCK_REGION)


def _drop_lock(fd: int) -> None:
    """Libera o lock; o descritor é fechado pelo caller."""
    if _POSIX:
        _FLOCK.flock(fd, _FLOCK.LOCK_UN)
        return

    os.lseek(fd, 0, os.SEEK_SET)
    _MSVCRT.locking(fd, _MSVCRT.LK_UNLCK, _LOCK_REGION)


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

    def _open_directory(self) -> int | None:
        """Abre/valida BACKUP_DIR existente sem seguir symlink.

        POSIX devolve o ``dir_fd``; no Windows não existe descritor de
        diretório (``os.open`` de diretório é EACCES) e a validação é feita por
        caminho, devolvendo ``None``.
        """
        if not _POSIX:
            return self._check_directory_windows()

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

    def _check_directory_windows(self) -> None:
        """Valida BACKUP_DIR por caminho (específico do Windows).

        Invariante preservada: BACKUP_DIR precisa existir e não pode ser
        symlink/reparse point (``lstat`` não segue a ligação).
        Invariante não verificável aqui: modo de permissão — o Windows não expõe
        bits POSIX (``os.stat`` devolve 0o777 para diretórios) e a autorização
        real é por ACL. Documentado como limitação, nunca simulado.
        """
        raw = os.fspath(self.backup_dir)
        try:
            info = os.lstat(raw)
        except FileNotFoundError as exc:
            raise BackupLockError(
                "BACKUP_DIR ausente; volume de continuidade não está montado"
            ) from exc
        except OSError as exc:
            raise BackupLockError(
                f"não foi possível inspecionar BACKUP_DIR: {exc.strerror or exc}"
            ) from exc

        if stat.S_ISLNK(info.st_mode):
            raise BackupLockError("BACKUP_DIR não pode ser symlink")
        if not stat.S_ISDIR(info.st_mode):
            raise BackupLockError("BACKUP_DIR não é diretório")
        return None

    @staticmethod
    def _lock_flags() -> int:
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        return flags

    def _open_lock_file(self, dir_fd: int | None) -> int:
        if not _POSIX:
            return self._open_lock_file_windows()
        return self._open_lock_file_posix(dir_fd)

    def _open_lock_file_posix(self, dir_fd: int | None) -> int:
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
        """Abre o mutex por caminho (específico do Windows).

        Sem ``O_NOFOLLOW`` nem ``dir_fd``, a recusa de symlink e a identidade do
        objeto aberto são verificadas depois do ``open``: ``lstat`` precisa
        devolver arquivo regular (symlink aparece como tal) e tem de ser o MESMO
        objeto do descritor aberto, o que também pega a troca do caminho entre
        ``open`` e a validação. O modo 0600 não é verificável no Windows (ver a
        docstring do módulo).
        """
        path = self.backup_dir / _LOCK_NAME
        flags = os.O_RDWR | os.O_CREAT
        flags |= getattr(os, "O_NOINHERIT", 0)
        flags |= getattr(os, "O_BINARY", 0)

        try:
            fd = os.open(path, flags, 0o600)
        except FileNotFoundError as exc:
            raise BackupLockError(
                "BACKUP_DIR ausente; volume de continuidade não está montado"
            ) from exc
        except OSError as exc:
            raise BackupLockError(
                f"não foi possível abrir mutex de backup: {exc.strerror or exc}"
            ) from exc

        try:
            opened = os.fstat(fd)
            on_path = os.lstat(path)

            if not stat.S_ISREG(on_path.st_mode):
                raise BackupLockError("arquivo de mutex é symlink")
            if (on_path.st_dev, on_path.st_ino) != (opened.st_dev, opened.st_ino):
                raise BackupLockError(
                    "arquivo de mutex foi substituído durante a abertura"
                )
            if opened.st_nlink != 1:
                raise BackupLockError("mutex de backup possui hard links")

            # msvcrt.locking exige uma região de 1 byte existente; flock não.
            if opened.st_size < _LOCK_REGION:
                os.write(fd, b"\x00")
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
                _take_lock(lock_fd)
            except BlockingIOError as exc:
                os.close(lock_fd)
                raise BackupAlreadyRunning("já existe backup em execução") from exc
            except OSError as exc:
                os.close(lock_fd)
                if exc.errno in _LOCK_CONTENTION_ERRNOS:
                    raise BackupAlreadyRunning("já existe backup em execução") from exc
                raise BackupLockError(
                    f"falha ao adquirir mutex de backup: {exc.strerror or exc}"
                ) from exc

            self._dir_fd = dir_fd
            self._lock_fd = lock_fd
            return self
        except Exception:
            if dir_fd is not None:
                os.close(dir_fd)
            raise

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
    """Abre BACKUP_DIR com as mesmas invariantes do mutex; caller fecha o fd.

    Específico de POSIX: as operações do motor de backup (``os.listdir``,
    ``os.stat``, ``os.unlink``) são relativas a ``dir_fd``, que o Windows não
    implementa. Em vez de degradar para operações por caminho — que perderiam a
    âncora segura do diretório — a função falha alto neste SO.
    """
    if not _POSIX:
        raise BackupLockError(
            "dir_fd para BACKUP_DIR é específico de POSIX; o motor de backup "
            "não roda em Windows"
        )
    fd = BackupProcessLock.from_path(backup_dir)._open_directory()
    assert fd is not None  # POSIX sempre devolve o descritor
    return fd


def backup_process_lock(backup_dir: str | os.PathLike[str]) -> BackupProcessLock:
    """Retorna context manager ainda não adquirido para uso com ``with``."""
    return BackupProcessLock.from_path(backup_dir)


def acquire_backup_lock(backup_dir: str | os.PathLike[str]) -> BackupProcessLock:
    """Adquire imediatamente o mutex; caller deve executar ``release``."""
    return BackupProcessLock.from_path(backup_dir).acquire()
