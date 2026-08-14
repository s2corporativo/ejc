from __future__ import annotations

import asyncio
import hashlib
import os
import stat
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import document_remote_hash_service as svc


def _config(tmp_path: Path) -> svc.ConfiguracaoHashRclone:
    config_path = tmp_path / "rclone.conf"
    config_path.write_text("[gdrive]\ntype = drive\n", encoding="utf-8")
    os.chmod(config_path, 0o600)
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    return svc.ConfiguracaoHashRclone(
        config_path=config_path,
        remote="gdrive",
        work_dir=work_dir,
        timeout_seconds=30,
    )


@pytest.mark.asyncio
async def test_hash_remoto_copia_para_temp_0600_calcula_exato_e_limpa(
    tmp_path: Path,
    monkeypatch,
):
    config = _config(tmp_path)
    payload = b"conteudo-remoto" * 1000
    observado = {}

    monkeypatch.setattr(svc.shutil, "which", lambda nome: "/usr/bin/rclone")

    def fake_run(argv, **kwargs):
        destino = Path(argv[-1])
        observado["argv"] = argv
        observado["modo_antes"] = stat.S_IMODE(destino.stat().st_mode)
        destino.write_bytes(payload)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(svc.subprocess, "run", fake_run)

    resultado = await svc.calcular_sha256_remoto_rclone(
        config,
        "casos/abc/documento.pdf",
        expected_size=len(payload),
    )

    assert resultado.sha256 == hashlib.sha256(payload).hexdigest()
    assert resultado.size_bytes == len(payload)
    assert observado["modo_antes"] == 0o600
    assert observado["argv"][:4] == [
        "/usr/bin/rclone",
        "--config",
        str(config.config_path),
        "copyto",
    ]
    assert observado["argv"][4] == "gdrive:casos/abc/documento.pdf"
    assert not list(config.work_dir.iterdir())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "remote_path",
    ["", "../fora.pdf", "/absoluto.pdf", r"pasta\\arquivo.pdf", "gdrive:objeto"],
)
async def test_path_remoto_invalido_falha_antes_de_subprocess(
    tmp_path: Path,
    monkeypatch,
    remote_path: str,
):
    config = _config(tmp_path)
    chamado = False

    def fake_run(*args, **kwargs):
        nonlocal chamado
        chamado = True
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(svc.subprocess, "run", fake_run)

    with pytest.raises(svc.HashRemotoConfiguracaoError):
        await svc.calcular_sha256_remoto_rclone(config, remote_path)

    assert chamado is False
    assert not list(config.work_dir.iterdir())


@pytest.mark.asyncio
async def test_erro_rclone_nao_vaza_remote_path_config_ou_stderr(tmp_path: Path, monkeypatch):
    config = _config(tmp_path)
    monkeypatch.setattr(svc.shutil, "which", lambda nome: "/usr/bin/rclone")

    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(svc.subprocess, "run", fake_run)

    with pytest.raises(svc.HashRemotoIndisponivelError) as exc:
        await svc.calcular_sha256_remoto_rclone(
            config,
            "casos/cliente-cpf-sentinela/documento.pdf",
        )

    texto = str(exc.value)
    assert "sentinela" not in texto
    assert str(config.config_path) not in texto
    assert "gdrive" not in texto
    assert not list(config.work_dir.iterdir())


@pytest.mark.asyncio
async def test_timeout_limpa_temporario_e_retorna_erro_generico(tmp_path: Path, monkeypatch):
    config = _config(tmp_path)
    monkeypatch.setattr(svc.shutil, "which", lambda nome: "/usr/bin/rclone")

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="rclone sentinela", timeout=1)

    monkeypatch.setattr(svc.subprocess, "run", fake_run)

    with pytest.raises(svc.HashRemotoIndisponivelError) as exc:
        await svc.calcular_sha256_remoto_rclone(config, "casos/a.pdf")

    assert "sentinela" not in str(exc.value)
    assert not list(config.work_dir.iterdir())


@pytest.mark.asyncio
async def test_tamanho_remoto_divergente_limpa_temp(tmp_path: Path, monkeypatch):
    config = _config(tmp_path)
    monkeypatch.setattr(svc.shutil, "which", lambda nome: "/usr/bin/rclone")

    def fake_run(argv, **kwargs):
        Path(argv[-1]).write_bytes(b"12345")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(svc.subprocess, "run", fake_run)

    with pytest.raises(Exception) as exc:
        await svc.calcular_sha256_remoto_rclone(
            config,
            "casos/a.pdf",
            expected_size=99,
        )

    assert exc.type.__name__ == "HashMetadataMismatchError"
    assert not list(config.work_dir.iterdir())


@pytest.mark.asyncio
async def test_cancelamento_durante_copia_aguarda_thread_e_limpa_temp(
    tmp_path: Path,
    monkeypatch,
):
    config = _config(tmp_path)
    monkeypatch.setattr(svc.shutil, "which", lambda nome: "/usr/bin/rclone")
    iniciou = threading.Event()
    liberar = threading.Event()
    finalizou = threading.Event()

    def fake_run(argv, **kwargs):
        destino = Path(argv[-1])
        destino.write_bytes(b"temporario")
        iniciou.set()
        liberar.wait(timeout=5)
        finalizou.set()
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(svc.subprocess, "run", fake_run)

    tarefa = asyncio.create_task(
        svc.calcular_sha256_remoto_rclone(config, "casos/a.pdf")
    )
    await asyncio.to_thread(iniciou.wait, 2)
    assert iniciou.is_set()

    tarefa.cancel()
    await asyncio.sleep(0)
    assert not tarefa.done()
    assert not finalizou.is_set()

    liberar.set()
    with pytest.raises(asyncio.CancelledError):
        await tarefa

    assert finalizou.is_set()
    assert not list(config.work_dir.iterdir())
