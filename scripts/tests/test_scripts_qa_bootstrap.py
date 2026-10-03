"""Bootstrap/CLI dos scripts e seeds usando somente SQLite e subprocessos fictícios."""

from __future__ import annotations

import ast
import importlib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(os.getenv("EJC_SCRIPTS_QA_SOURCE", str(ROOT)))
# backend/scripts pode sombrear o namespace scripts da raiz na suíte backend.
# O pacote privado mantém os imports relativos reais sem executar entrypoints.
_PACKAGE = "ejc_qa_backup"
_package = ModuleType(_PACKAGE)
_package.__path__ = [str(ROOT / "scripts/backup")]
sys.modules[_PACKAGE] = _package
drill_local_backup_restore = importlib.import_module(f"{_PACKAGE}.drill_local_backup_restore")
restore_drill = importlib.import_module(f"{_PACKAGE}.restore_drill")
PgConn = importlib.import_module(f"{_PACKAGE}._postgres").PgConn


def source_drill(module):
    if SOURCE == ROOT:
        return module
    name = module.__name__.rsplit(".", 1)[-1]
    spec = importlib.util.spec_from_file_location(
        f"scripts.backup.qa_baseline_{name}", SOURCE / "scripts/backup" / f"{name}.py"
    )
    original = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = original
    spec.loader.exec_module(original)
    return original


DRILLS = [source_drill(drill_local_backup_restore), source_drill(restore_drill)]


@pytest.mark.parametrize("module", DRILLS)
def test_drill_cli_psql_preserva_alias_de_monkeypatch(module, monkeypatch):
    conn = module.PgConn.from_url(
        "postgresql://qa%20user:fake%21@localhost:5544/qa%20db"
    )
    assert (
        conn.user == "qa user" and conn.password == "fake!" and conn.database == "qa db"
    )
    calls = []

    def run(args, actual_conn, **kwargs):
        calls.append((args, actual_conn, kwargs))
        return SimpleNamespace(stdout="  fictitious result\n")

    monkeypatch.setattr(module, "_run", run)
    assert module._psql(conn, "SELECT 1", database="qa_target") == "fictitious result"
    args, actual_conn, _ = calls[0]
    assert actual_conn is conn
    assert args == [
        "psql",
        "-h",
        "localhost",
        "-p",
        "5544",
        "-U",
        "qa user",
        "-d",
        "qa_target",
        "-v",
        "ON_ERROR_STOP=1",
        "-A",
        "-t",
        "-q",
        "-c",
        "SELECT 1",
    ]
    assert "fake!" not in args


@pytest.mark.parametrize(
    "module,gate", [(DRILLS[0], "DRILL_ALLOW"), (DRILLS[1], "RESTORE_DRILL_ALLOW")]
)
def test_drill_sem_opt_in_nao_executa_postgres(module, gate, monkeypatch):
    monkeypatch.delenv(gate, raising=False)
    monkeypatch.setattr(
        module, "_run", lambda *args, **kwargs: pytest.fail("Postgres não autorizado")
    )
    assert module.main() == 2


def test_pgconn_rejeita_url_incompleta():
    for url in ("", "postgresql://localhost/qa", "postgresql://qa@localhost"):
        with pytest.raises(RuntimeError, match="DATABASE_URL_SYNC inválida"):
            PgConn.from_url(url)


@pytest.mark.parametrize("module", DRILLS)
def test_run_segredo_so_no_ambiente_e_erro_pg_preservado(module, monkeypatch):
    conn = module.PgConn.from_url("postgresql://qa:fictitious-password@localhost/qa")

    def run(args, **kwargs):
        assert args == ["psql", "--version"]
        assert kwargs["env"]["PGPASSWORD"] == "fictitious-password"
        assert kwargs["timeout"] == 7 and kwargs["check"] is True
        raise subprocess.CalledProcessError(3, args, stderr="fictitious database error")

    monkeypatch.setattr(module.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="código 3.*fictitious database error"):
        module._run(["psql", "--version"], conn, timeout=7)


@pytest.mark.parametrize(
    "script",
    ["ingestao_biblioteca_juridica.py", "quarentenar_biblioteca_juridica_piloto.py"],
)
@pytest.mark.parametrize("candidate", ["/app", "/home/ubuntu/ejc/backend", "local"])
def test_bootstrap_direto_preserva_preferencia_e_evita_path_duplicado(
    script, candidate, monkeypatch
):
    # Carrega só o bootstrap, sem imports que configurem ou abram banco.
    path = Path("backend/scripts") / script
    tree = ast.parse((SOURCE / path).read_text())
    node = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "_bootstrap_backend"
    )
    namespace = {"os": os, "sys": sys, "__file__": str(ROOT / path)}
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])),
            str(path),
            "exec",
        ),
        namespace,
    )
    selected = str(ROOT / "backend") if candidate == "local" else candidate
    monkeypatch.setattr(
        os.path, "isdir", lambda path: path == os.path.join(selected, "app")
    )
    original_path = sys.path[:]
    monkeypatch.setattr(sys, "path", original_path[:])
    # Remove o candidato local se já tiver sido inserido por conftest.
    sys.path[:] = [p for p in sys.path if p != selected]
    namespace["_bootstrap_backend"]()
    assert sys.path[0] == selected
    namespace["_bootstrap_backend"]()
    assert sys.path.count(selected) == 1


def load_seed(name):
    path = SOURCE / "backend/app/seeds" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"app.seeds.qa_test_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "name",
    [
        "checklists_seed",
        "clausulas_seed",
        "skills_contextual_areas_seed",
        "skills_workflows_seed",
    ],
)
def test_seeds_catalogos_idempotentes_sqlite_ficticio(name, monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        for ddl in (
            "CREATE TABLE checklist_templates(id TEXT PRIMARY KEY, nome TEXT, descricao TEXT, area_juridica TEXT, is_default BOOLEAN, deleted_at TEXT)",
            "CREATE TABLE checklist_template_items(id TEXT PRIMARY KEY, template_id TEXT, texto TEXT, obrigatorio BOOLEAN, ordem INTEGER)",
            "CREATE TABLE doc_templates(id TEXT PRIMARY KEY, titulo TEXT, tipo_peca TEXT, area TEXT, descricao TEXT, conteudo TEXT, ativo BOOLEAN, deleted_at TEXT)",
            "CREATE TABLE ejc_skills(id TEXT PRIMARY KEY, name TEXT UNIQUE, display_name TEXT, description TEXT, system_prompt TEXT, engine TEXT, area TEXT, active BOOLEAN, requires_case BOOLEAN, requires_human_review BOOLEAN, oab_restricted BOOLEAN, version INTEGER, created_at TEXT, updated_at TEXT)",
        ):
            conn.execute(text(ddl))
    monkeypatch.setenv("DATABASE_URL_SYNC", "sqlite:///:memory:")
    monkeypatch.setattr("sqlalchemy.create_engine", lambda *args, **kwargs: engine)
    module = load_seed(name)
    module.seed()
    module.seed()
    with engine.connect() as conn:
        if name == "checklists_seed":
            rows = conn.execute(
                text("SELECT nome, area_juridica, is_default FROM checklist_templates")
            ).all()
            assert {row.nome for row in rows} == {c["nome"] for c in module.CHECKLISTS}
            assert all(row.is_default for row in rows)
            count = conn.execute(
                text("SELECT count(*) FROM checklist_template_items")
            ).scalar_one()
            assert count == sum(len(c["itens"]) for c in module.CHECKLISTS)
        elif name == "clausulas_seed":
            rows = conn.execute(
                text("SELECT titulo, conteudo, ativo FROM doc_templates")
            ).all()
            assert len(rows) == len(module.CLAUSULAS)
            original = dict(module.CLAUSULAS)
            for row in rows:
                assert row.ativo and row.conteudo.startswith(original[row.titulo])
                assert "revisão humana obrigatória" in row.conteudo
        else:
            rows = conn.execute(
                text(
                    "SELECT name, system_prompt, requires_human_review, oab_restricted, version FROM ejc_skills"
                )
            ).all()
            assert {row.name: row.system_prompt for row in rows} == {
                s["name"]: s["system_prompt"] for s in module.SKILLS
            }
            assert all(
                row.requires_human_review and row.oab_restricted and row.version == 1
                for row in rows
            )


@pytest.mark.parametrize(
    "name",
    [
        "checklists_seed",
        "clausulas_seed",
        "skills_contextual_areas_seed",
        "skills_workflows_seed",
        "skills_expansion_seed",
    ],
)
def test_seed_sem_url_falha_antes_de_abrir_banco(name, monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL_SYNC", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(
        "sqlalchemy.create_engine",
        lambda *args, **kwargs: pytest.fail("Não deve abrir banco"),
    )
    with pytest.raises(SystemExit) as exc:
        load_seed(name).seed()
    assert exc.value.code == 1
    assert "DATABASE_URL(_SYNC) não configurada" in capsys.readouterr().out
