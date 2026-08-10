from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVICES = ROOT / "app" / "services"
ROUTERS = ROOT / "app" / "routers"
SCRIPTS = ROOT.parent / "scripts"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_scheduler_nao_agenda_motor_legado_de_backup():
    scheduler = _text(SERVICES / "scheduler.py")
    assert 's.add_job(_backup_banco' not in scheduler, (
        "P0: scheduler ainda agenda o motor legado _backup_banco além do backup canônico"
    )


def test_scheduler_backup_drive_usa_fachada_exclusiva():
    scheduler = _text(SERVICES / "scheduler.py")
    assert "from app.services.backup_execution_service import" in scheduler
    assert "job_backup_drive_exclusivo" in scheduler
    assert "from app.services.backup_service import hora_backup_utc, job_backup_drive" not in scheduler
    assert "job_backup_drive," not in scheduler


def test_router_admin_nao_dispara_motor_cru():
    router = _text(ROUTERS / "backup_admin.py")
    assert "executar_backup_background_exclusivo" in router
    assert "backup_service.executar_backup_background(" not in router


def test_callers_produtivos_nao_chamam_executar_backup_cru():
    """AST guard: só a fachada pode invocar backup_service.executar_backup."""
    allowed = (SERVICES / "backup_execution_service.py").resolve()
    offenders: list[str] = []

    roots = [SERVICES, ROUTERS]
    for base in roots:
        for path in base.rglob("*.py"):
            if path.resolve() == allowed:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr in {"executar_backup", "executar_backup_background"}
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "backup_service"
                ):
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}:{func.attr}")

    assert not offenders, (
        "callers produtivos burlam backup_execution_service: " + ", ".join(offenders)
    )


def test_predeploy_deve_migrar_para_fachada_exclusiva_quando_pr_1017_for_integrado():
    """Contrato do script operacional; não aceita chamada crua permanente."""
    backup_script = _text(SCRIPTS / "backup.sh")
    # Enquanto #1017 ainda não estiver na base, este teste documenta e bloqueia
    # a última ligação que precisa ser reconciliada no rebase/stack.
    assert "backup_execution_service.executar_backup_exclusivo" in backup_script, (
        "P0: scripts/backup.sh ainda chama backup_service.executar_backup diretamente"
    )
