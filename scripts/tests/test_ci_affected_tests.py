from pathlib import Path

from scripts.ci_affected_tests import select_backend, select_frontend


def _touch(root: Path, rel: str, content: str = "") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_backend_seleciona_teste_direto_e_contratos(tmp_path: Path):
    _touch(tmp_path, "backend/tests/test_alembic_single_head.py")
    _touch(tmp_path, "backend/tests/test_rotas_registro_explicito.py")
    _touch(tmp_path, "backend/tests/test_fees.py", "from app.routers import fees")
    _touch(tmp_path, "backend/app/routers/fees.py")
    result = select_backend(tmp_path, ["backend/app/routers/fees.py"])
    assert "tests/test_fees.py" in result
    assert "tests/test_alembic_single_head.py" in result
    assert "tests/test_rotas_registro_explicito.py" in result


def test_backend_migration_adiciona_contratos_schema(tmp_path: Path):
    for rel in (
        "backend/tests/test_alembic_single_head.py",
        "backend/tests/test_rotas_registro_explicito.py",
        "backend/tests/test_migration_reservations_head.py",
        "backend/tests/test_migrations_reais_passam_no_gate.py",
        "backend/tests/test_schema_dr_parity.py",
    ):
        _touch(tmp_path, rel)
    result = select_backend(tmp_path, ["backend/alembic/versions/999_x.py"])
    assert "tests/test_schema_dr_parity.py" in result
    assert "tests/test_migrations_reais_passam_no_gate.py" in result


def test_frontend_seleciona_teste_do_componente(tmp_path: Path):
    _touch(tmp_path, "frontend/src/config/canonicalNavigation.test.ts")
    _touch(tmp_path, "frontend/src/pages/DashboardUltra.tsx")
    _touch(tmp_path, "frontend/src/pages/DashboardUltra.test.tsx")
    result = select_frontend(tmp_path, ["frontend/src/pages/DashboardUltra.tsx"])
    assert "src/pages/DashboardUltra.test.tsx" in result
    assert "src/config/canonicalNavigation.test.ts" in result
