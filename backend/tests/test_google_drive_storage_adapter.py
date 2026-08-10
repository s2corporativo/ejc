"""Google Drive adapter: config, path direto, segurança e compensação.

Os testes não acessam Google/rclone real. O contrato externo é simulado na
fronteira `_run`/`subprocess.run`, provando quais comandos seriam executados e
impedindo regressão para varredura recursiva em documentos novos.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import google_drive as gd


def _ok(*, stdout: str = ""):
    return SimpleNamespace(returncode=0, stdout=stdout, stderr="")


def _erro(code: int = 1):
    return SimpleNamespace(returncode=code, stdout="", stderr="detalhe-sensivel")


def _drive_habilitado(monkeypatch):
    monkeypatch.setattr(gd, "_drive_available", lambda: True)


def test_config_padrao_alinha_com_volume_montado_no_compose(monkeypatch):
    monkeypatch.delenv("RCLONE_CONFIG", raising=False)
    assert gd._rclone_conf_path() == "/root/.config/rclone/rclone.conf"


def test_rclone_config_env_sobrescreve_padrao(monkeypatch):
    monkeypatch.setenv("RCLONE_CONFIG", "/run/ejc/rclone/custom.conf")
    assert gd._rclone_conf_path() == "/run/ejc/rclone/custom.conf"


def test_disponibilidade_e_avaliada_em_runtime(monkeypatch):
    monkeypatch.setenv("RCLONE_CONFIG", "/run/ejc/rclone/rclone.conf")
    monkeypatch.setattr(
        gd.shutil,
        "which",
        lambda nome: "/usr/bin/rclone" if nome == "rclone" else None,
    )
    monkeypatch.setattr(
        gd.os.path,
        "isfile",
        lambda path: path == "/run/ejc/rclone/rclone.conf",
    )
    monkeypatch.setattr(
        gd.os,
        "access",
        lambda path, mode: path == "/run/ejc/rclone/rclone.conf",
    )

    assert gd._drive_available() is True

    monkeypatch.setattr(gd.os.path, "isfile", lambda path: False)
    assert gd._drive_available() is False


def test_operacoes_falham_fechado_quando_storage_indisponivel(monkeypatch):
    monkeypatch.setattr(gd, "_drive_available", lambda: False)

    with pytest.raises(gd.DriveIndisponivelError):
        gd.upload_file(b"x", "a.pdf", "application/pdf")
    with pytest.raises(gd.DriveIndisponivelError):
        gd.download_file("drive-id", remote_path="geral/a.pdf")
    with pytest.raises(gd.DriveIndisponivelError):
        gd.delete_file("drive-id", remote_path="geral/a.pdf")


def test_run_passa_mesma_config_explicitamente_ao_rclone(monkeypatch):
    monkeypatch.setenv("RCLONE_CONFIG", "/run/ejc/rclone/rclone.conf")
    capturado: list[list[str]] = []

    def fake_subprocess_run(cmd, **kwargs):
        del kwargs
        capturado.append(list(cmd))
        return _ok()

    monkeypatch.setattr(gd.subprocess, "run", fake_subprocess_run)

    gd._run(["rclone", "lsd", "gdrive:EJC-Documentos"])

    assert capturado == [
        [
            "rclone",
            "--config",
            "/run/ejc/rclone/rclone.conf",
            "lsd",
            "gdrive:EJC-Documentos",
        ]
    ]


def test_run_rejeita_comando_que_nao_seja_rclone():
    with pytest.raises(ValueError, match="somente comandos rclone"):
        gd._run(["bash", "-lc", "echo proibido"])


def test_case_folder_token_exige_uuid_e_nao_aceita_segmento_arbitrario():
    case_id = str(uuid4())
    assert gd.case_folder_token(case_id) == f"case:{case_id}"

    for invalido in ("../outro", "/absoluto", "cliente-x", ""):
        with pytest.raises(ValueError):
            gd.case_folder_token(invalido)


def test_remote_path_rejeita_traversal_absoluto_e_remote_injetado():
    for invalido in (
        "../segredo.pdf",
        "/etc/passwd",
        "casos/../segredo.pdf",
        "outro:bucket/arquivo.pdf",
    ):
        with pytest.raises(ValueError):
            gd._rclone_path_rel(invalido)


def test_upload_reduz_filename_com_traversal_a_um_segmento(monkeypatch):
    _drive_habilitado(monkeypatch)
    comandos: list[list[str]] = []

    def fake_run(cmd, timeout=gd.RCLONE_TIMEOUT):
        del timeout
        comandos.append(list(cmd))
        if cmd[1] == "lsjson":
            return _ok(stdout='{"ID":"drive-1"}')
        return _ok()

    monkeypatch.setattr(gd, "_run", fake_run)

    out = gd.upload_file(
        b"x",
        "../../segredo.pdf",
        "application/pdf",
    )

    assert out["remote_path"] == "geral/segredo.pdf"
    assert all(".." not in parte for cmd in comandos for parte in cmd)
    assert any(cmd[-1].endswith("/geral/segredo.pdf") for cmd in comandos)


def test_upload_usa_copyto_e_stat_exato_sem_varredura_recursiva(monkeypatch):
    _drive_habilitado(monkeypatch)
    comandos: list[list[str]] = []

    def fake_run(cmd, timeout=gd.RCLONE_TIMEOUT):
        del timeout
        comandos.append(list(cmd))
        if cmd[1] == "lsjson":
            return _ok(stdout='{"ID":"drive-123"}')
        return _ok()

    monkeypatch.setattr(gd, "_run", fake_run)
    case_id = str(uuid4())
    nome_remoto = f"{uuid4()}.pdf"

    out = gd.upload_file(
        b"%PDF-1.7 teste",
        nome_remoto,
        "application/pdf",
        gd.case_folder_token(case_id),
    )

    assert out["id"] == "drive-123"
    assert out["remote_path"] == f"casos/{case_id}/{nome_remoto}"
    assert any(cmd[1] == "copyto" for cmd in comandos)
    stat = next(cmd for cmd in comandos if cmd[1] == "lsjson")
    assert "--stat" in stat
    assert "-R" not in stat
    assert all("-R" not in cmd for cmd in comandos)


def test_upload_compensa_objeto_quando_copy_falha(monkeypatch):
    _drive_habilitado(monkeypatch)
    comandos: list[list[str]] = []

    def fake_run(cmd, timeout=gd.RCLONE_TIMEOUT):
        del timeout
        comandos.append(list(cmd))
        if cmd[1] == "copyto":
            return _erro(6)
        return _ok()

    monkeypatch.setattr(gd, "_run", fake_run)

    with pytest.raises(RuntimeError, match="upload falhou"):
        gd.upload_file(
            b"conteudo",
            f"{uuid4()}.pdf",
            "application/pdf",
            gd.case_folder_token(str(uuid4())),
        )

    assert any(cmd[1] == "deletefile" for cmd in comandos)


def test_upload_compensa_objeto_quando_copy_estoura_timeout(monkeypatch):
    _drive_habilitado(monkeypatch)
    comandos: list[list[str]] = []

    def fake_run(cmd, timeout=gd.RCLONE_TIMEOUT):
        comandos.append(list(cmd))
        if cmd[1] == "copyto":
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)
        return _ok()

    monkeypatch.setattr(gd, "_run", fake_run)

    with pytest.raises(subprocess.TimeoutExpired):
        gd.upload_file(
            b"conteudo",
            f"{uuid4()}.pdf",
            "application/pdf",
            gd.case_folder_token(str(uuid4())),
        )

    assert any(cmd[1] == "deletefile" for cmd in comandos)


def test_compensacao_nao_mascara_falha_quando_deletefile_tambem_expira(monkeypatch):
    _drive_habilitado(monkeypatch)

    def fake_run(cmd, timeout=gd.RCLONE_TIMEOUT):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)

    monkeypatch.setattr(gd, "_run", fake_run)

    # Best effort: a compensação registra o problema, mas não propaga outro erro.
    gd._compensar_objeto("gdrive:EJC-Documentos/geral/arquivo.pdf")


def test_upload_compensa_objeto_quando_pos_check_falha(monkeypatch):
    _drive_habilitado(monkeypatch)
    comandos: list[list[str]] = []

    def fake_run(cmd, timeout=gd.RCLONE_TIMEOUT):
        del timeout
        comandos.append(list(cmd))
        if cmd[1] == "lsjson":
            return _erro(7)
        return _ok()

    monkeypatch.setattr(gd, "_run", fake_run)

    with pytest.raises(RuntimeError, match="lsjson --stat falhou"):
        gd.upload_file(
            b"conteudo",
            f"{uuid4()}.pdf",
            "application/pdf",
            gd.case_folder_token(str(uuid4())),
        )

    assert any(cmd[1] == "deletefile" for cmd in comandos)


def test_download_com_remote_path_nao_executa_lsjson_recursivo(monkeypatch):
    _drive_habilitado(monkeypatch)
    comandos: list[list[str]] = []

    def fake_run(cmd, timeout=gd.RCLONE_TIMEOUT):
        del timeout
        comandos.append(list(cmd))
        assert cmd[1] == "copyto"
        Path(cmd[-1]).write_bytes(b"arquivo-remoto")
        return _ok()

    monkeypatch.setattr(gd, "_run", fake_run)

    conteudo = gd.download_file(
        "drive-id",
        remote_path=f"casos/{uuid4()}/{uuid4()}.pdf",
    )

    assert conteudo == b"arquivo-remoto"
    assert len(comandos) == 1
    assert comandos[0][1] == "copyto"
    assert "-R" not in comandos[0]


def test_delete_com_remote_path_e_operacao_direta(monkeypatch):
    _drive_habilitado(monkeypatch)
    comandos: list[list[str]] = []
    remote_path = f"casos/{uuid4()}/{uuid4()}.pdf"

    def fake_run(cmd, timeout=gd.RCLONE_TIMEOUT):
        del timeout
        comandos.append(list(cmd))
        return _ok()

    monkeypatch.setattr(gd, "_run", fake_run)

    gd.delete_file("drive-id", remote_path=remote_path)

    assert len(comandos) == 1
    assert comandos[0][:2] == ["rclone", "deletefile"]
    assert comandos[0][-1] == f"gdrive:EJC-Documentos/{remote_path}"
    assert "-R" not in comandos[0]


def test_fallback_legado_varre_somente_quando_remote_path_esta_ausente(monkeypatch):
    _drive_habilitado(monkeypatch)
    comandos: list[list[str]] = []
    path_legado = "geral/arquivo-legado.pdf"

    def fake_run(cmd, timeout=gd.RCLONE_TIMEOUT):
        del timeout
        comandos.append(list(cmd))
        if cmd[1] == "lsjson":
            return _ok(stdout=f'[{{"ID":"legacy-id","Path":"{path_legado}"}}]')
        if cmd[1] == "copyto":
            Path(cmd[-1]).write_bytes(b"legado")
            return _ok()
        raise AssertionError(f"comando inesperado: {cmd}")

    monkeypatch.setattr(gd, "_run", fake_run)

    assert gd.download_file("legacy-id") == b"legado"
    assert comandos[0][1] == "lsjson"
    assert "-R" in comandos[0]
    assert comandos[1][1] == "copyto"


def test_nonzero_no_download_nao_e_classificado_como_404(monkeypatch):
    _drive_habilitado(monkeypatch)

    def fake_run(cmd, timeout=gd.RCLONE_TIMEOUT):
        del cmd, timeout
        return _erro(9)

    monkeypatch.setattr(gd, "_run", fake_run)

    with pytest.raises(RuntimeError) as exc:
        gd.download_file(
            "drive-id",
            remote_path=f"casos/{uuid4()}/{uuid4()}.pdf",
        )

    assert not isinstance(exc.value, gd.DriveObjetoNaoEncontradoError)
    assert "detalhe-sensivel" not in str(exc.value)
