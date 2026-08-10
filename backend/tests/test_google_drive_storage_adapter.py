"""Google Drive adapter: path direto, segurança e compensação.

Os testes não acessam Google/rclone real. O contrato externo é simulado na
fronteira `_run`, provando quais comandos seriam executados e impedindo que uma
regressão volte a varrer a árvore inteira para documentos novos.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import google_drive as gd


def _ok(*, stdout: str = ""):
    return SimpleNamespace(returncode=0, stdout=stdout, stderr="")


def _erro(code: int = 1):
    return SimpleNamespace(returncode=code, stdout="", stderr="detalhe-sensivel")


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


def test_upload_usa_copyto_e_stat_exato_sem_varredura_recursiva(monkeypatch):
    monkeypatch.setattr(gd, "DRIVE_AVAILABLE", True)
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


def test_upload_compensa_objeto_quando_pos_check_falha(monkeypatch):
    monkeypatch.setattr(gd, "DRIVE_AVAILABLE", True)
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
    monkeypatch.setattr(gd, "DRIVE_AVAILABLE", True)
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
    monkeypatch.setattr(gd, "DRIVE_AVAILABLE", True)
    comandos: list[list[str]] = []

    def fake_run(cmd, timeout=gd.RCLONE_TIMEOUT):
        del timeout
        comandos.append(list(cmd))
        return _ok()

    monkeypatch.setattr(gd, "_run", fake_run)

    gd.delete_file(
        "drive-id",
        remote_path=f"casos/{uuid4()}/{uuid4()}.pdf",
    )

    assert comandos == [
        [
            "rclone",
            "deletefile",
            comandos[0][-1],
        ]
    ]
    assert "-R" not in comandos[0]


def test_fallback_legado_varre_somente_quando_remote_path_esta_ausente(monkeypatch):
    monkeypatch.setattr(gd, "DRIVE_AVAILABLE", True)
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
    monkeypatch.setattr(gd, "DRIVE_AVAILABLE", True)

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
