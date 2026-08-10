from __future__ import annotations

import multiprocessing as mp
import os
import stat
from pathlib import Path

import pytest

from app.services.backup_lock import (
    BackupAlreadyRunning,
    BackupLockError,
    backup_process_lock,
)


def _hold_lock(path: str, ready: mp.synchronize.Event, release: mp.synchronize.Event) -> None:
    """Child process: mantém flock até o teste autorizar a saída."""
    with backup_process_lock(path):
        ready.set()
        release.wait(timeout=10)


def _lock_and_crash(path: str, ready: mp.synchronize.Event) -> None:
    """Child process: simula crash não capturável após adquirir flock."""
    lock = backup_process_lock(path)
    lock.acquire()
    ready.set()
    os._exit(73)


def _secure_dir(tmp_path: Path) -> Path:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(mode=0o700)
    backup_dir.chmod(0o700)
    return backup_dir


def _mp_context() -> mp.context.BaseContext:
    # O backend/containers de produção são Linux; fork evita dependência de
    # serialização incidental de fixtures e testa o mesmo kernel flock.
    return mp.get_context("fork")


def test_segundo_processo_nao_adquire_enquanto_primeiro_detem(tmp_path: Path) -> None:
    backup_dir = _secure_dir(tmp_path)
    ctx = _mp_context()
    ready = ctx.Event()
    release = ctx.Event()
    proc = ctx.Process(target=_hold_lock, args=(str(backup_dir), ready, release))
    proc.start()
    try:
        assert ready.wait(timeout=5), "processo filho não adquiriu o lock"
        with pytest.raises(BackupAlreadyRunning, match="backup em execução"):
            with backup_process_lock(backup_dir):
                pytest.fail("segundo processo entrou na seção crítica")
    finally:
        release.set()
        proc.join(timeout=5)
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=2)
    assert proc.exitcode == 0


def test_kernel_libera_flock_quando_processo_morre(tmp_path: Path) -> None:
    backup_dir = _secure_dir(tmp_path)
    ctx = _mp_context()
    ready = ctx.Event()
    proc = ctx.Process(target=_lock_and_crash, args=(str(backup_dir), ready))
    proc.start()
    assert ready.wait(timeout=5), "filho não adquiriu lock antes do crash"
    proc.join(timeout=5)
    assert not proc.is_alive()
    assert proc.exitcode == 73

    # Nenhum cleanup Python do filho rodou; a liberação é do kernel.
    with backup_process_lock(backup_dir):
        pass


def test_release_explicitamente_permite_nova_aquisicao(tmp_path: Path) -> None:
    backup_dir = _secure_dir(tmp_path)
    with backup_process_lock(backup_dir):
        pass
    with backup_process_lock(backup_dir):
        pass


def test_lock_file_fica_regular_link_unico_e_0600(tmp_path: Path) -> None:
    backup_dir = _secure_dir(tmp_path)
    with backup_process_lock(backup_dir):
        lock_path = backup_dir / ".ejc-backup.lock"
        info = lock_path.stat()
        assert stat.S_ISREG(info.st_mode)
        assert info.st_nlink == 1
        assert stat.S_IMODE(info.st_mode) == 0o600


def test_symlink_no_arquivo_de_lock_falha_fechado(tmp_path: Path) -> None:
    backup_dir = _secure_dir(tmp_path)
    target = tmp_path / "target"
    target.write_text("nao usar", encoding="utf-8")
    (backup_dir / ".ejc-backup.lock").symlink_to(target)

    with pytest.raises(BackupLockError, match="symlink"):
        with backup_process_lock(backup_dir):
            pass


def test_hardlink_no_arquivo_de_lock_falha_fechado(tmp_path: Path) -> None:
    backup_dir = _secure_dir(tmp_path)
    source = tmp_path / "source-lock"
    source.write_text("", encoding="utf-8")
    os.link(source, backup_dir / ".ejc-backup.lock")

    with pytest.raises(BackupLockError, match="hard links"):
        with backup_process_lock(backup_dir):
            pass


def test_backup_dir_group_world_writable_e_rejeitado(tmp_path: Path) -> None:
    backup_dir = _secure_dir(tmp_path)
    backup_dir.chmod(0o777)

    with pytest.raises(BackupLockError, match="gravável por grupo/outros"):
        with backup_process_lock(backup_dir):
            pass


def test_backup_dir_symlink_e_rejeitado(tmp_path: Path) -> None:
    real_dir = _secure_dir(tmp_path)
    link = tmp_path / "backups-link"
    link.symlink_to(real_dir, target_is_directory=True)

    with pytest.raises(BackupLockError, match="BACKUP_DIR"):
        with backup_process_lock(link):
            pass


def test_backup_dir_ausente_nao_e_criado(tmp_path: Path) -> None:
    missing = tmp_path / "volume-nao-montado"

    with pytest.raises(BackupLockError, match="volume de continuidade não está montado"):
        with backup_process_lock(missing):
            pass
    assert not missing.exists()


def test_mesma_instancia_nao_pode_ser_reutilizada(tmp_path: Path) -> None:
    backup_dir = _secure_dir(tmp_path)
    lock = backup_process_lock(backup_dir)
    lock.acquire()
    try:
        with pytest.raises(BackupLockError, match="instância de mutex já utilizada"):
            lock.acquire()
    finally:
        lock.release()
