from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT


def _text(relative: str) -> str:
    return (REPO / relative).read_text(encoding="utf-8")


def test_backup_diario_legado_e_apenas_shim_cifrado():
    src = _text("scripts/backup/backup_diario.sh")
    assert 'BACKUP_ORIGEM=agendado exec bash "$ROOT/scripts/backup.sh"' in src

    forbidden = (
        "pg_dump",
        "tar czf",
        "ejc_db_",
        "ejc_uploads_",
        "ejc_ged_",
        "BACKUP_BASE_DIR",
        "RCLONE_REMOTE",
    )
    for marker in forbidden:
        assert marker not in src, f"rotina legada em claro reapareceu: {marker}"


def test_restore_legado_em_claro_permanece_bloqueado():
    src = _text("scripts/backup/restaurar_backup.sh")
    assert "Restore legado DESATIVADO" in src
    assert "exit 2" in src
    assert "RESTORE_DRILL_ALLOW=1" in src

    forbidden = (
        "pg_restore --clean",
        "ASSUME_YES",
        "tar xzf",
        "read -r -p",
        "POSTGRES_PASSWORD_ENV",
    )
    for marker in forbidden:
        assert marker not in src, f"restore destrutivo legado reapareceu: {marker}"


def test_runbook_nao_ensina_reter_backup_em_claro():
    runbook = _text("RUNBOOK_BACKUP.md")
    assert "backup cifrado" in runbook.lower()
    assert "restore legado em claro **desativado**" in runbook.lower()
    assert "um único job de backup canônico" in runbook
    assert "BACKUP_DIR" in runbook
    assert "offsite_ok=true" in runbook

    forbidden = (
        "0 2 * * *",
        "0 3 * * *",
        "/opt/ejc/backups/diario/ejc_db_",
        "bash scripts/backup/restaurar_backup.sh \\",
        "RCLONE_REMOTE configurado e primeiro upload offsite confirmado",
    )
    for marker in forbidden:
        assert marker not in runbook, f"runbook voltou a instruir fluxo legado: {marker}"


def test_wrapper_operacional_nao_implementa_dump_ou_tar_proprio():
    wrapper = _text("scripts/backup.sh")
    assert "backup_execution_service.executar_backup_exclusivo" in wrapper
    assert "backup_service.executar_backup(" not in wrapper
    # O wrapper de main mantém apenas a chave de mensagem de diagnóstico
    # `"pg_dump_disponivel"` no JSON de pré-requisitos — não executa pg_dump/tar.
    # Linhas de comentário também são excluídas da verificação de comandos.
    linhas = [
        linha for linha in wrapper.splitlines()
        if not linha.lstrip().startswith("#")
    ]
    corpo = (
        "\n".join(linhas)
        .replace('"pg_dump_disponivel"', '""')
        .replace('"pg_dump indisponível"', '""')
    )
    assert "pg_dump" not in corpo, "wrapper não deve executar pg_dump"
    assert "tar cz" not in corpo, "wrapper não deve executar tar cz"
    # INF-04: prova recuperável = offsite confirmado OU retenção local cifrada
    # em BACKUP_DIR; `local_ok` (temporário) continua não bastando.
    assert "and (offsite_ok or retencao_local_ok)" in wrapper
    assert 'retencao_local_ok = bool(result.get("retencao_local_ok"))' in wrapper
