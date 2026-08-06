"""Paridade de schema e reconstrução de Disaster Recovery.

Compara a cadeia Alembic com os models ORM e com SQL bruto do aplicativo. Em
modo RUN_DB_TESTS também cria um banco vazio e prova `alembic upgrade head`.
"""
from __future__ import annotations

import ast
import functools
import os
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).resolve().parents[1]
APP_DIR = BACKEND_DIR / "app"
HEAD_REVISION = "131_audit_logs_worm"

RAW_SQL_TABLES_ESPERADAS = {
    "agenda_eventos", "areas", "case_ambiental", "case_etiquetas",
    "client_pending_items", "document_access_log", "domain_events",
    "due_diligence_templates", "inadimplencia_alerts",
    "indice_risco_historico", "kanban_columns", "memoria_institucional",
    "modelos_documentos", "office_contracts", "office_expenses",
    "partner_withdrawals", "peca_codigo_contador", "portal_mensagens",
    "pricing_rules", "score_juridico", "teses_vitoriosas",
}
VIEWS_ESPERADAS = {"vw_atividades"}
FALSOS_POSITIVOS_SQL = {"alembic_version", "pg_extension", "pg_stat_activity"}
_RUIDO_SQL = {
    "information_schema", "unnest", "generate_series", "jsonb_each",
    "jsonb_array_elements", "jsonb_array_elements_text",
    "regexp_split_to_table", "lateral", "only", "select", "current_date",
    "current_timestamp", "duplicate", "excluded", "now",
}

_RE_CREATE_TABLE = re.compile(
    r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"?([a-zA-Z_]\w*)"?', re.I
)
_RE_CREATE_TABLE_GUARDADO = re.compile(
    r'CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+"?([a-zA-Z_]\w*)"?', re.I
)
_RE_DROP_TABLE = re.compile(
    r'DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?"?([a-zA-Z_]\w*)"?', re.I
)
_RE_ALTER_TABLE = re.compile(
    r'ALTER\s+TABLE\s+(?:ONLY\s+)?"?([a-zA-Z_]\w*)"?', re.I
)
_RE_ADD_COLUMN = re.compile(
    r'ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?"?([a-zA-Z_]\w*)"?', re.I
)
_RE_DROP_COLUMN = re.compile(
    r'DROP\s+COLUMN\s+(?:IF\s+EXISTS\s+)?"?([a-zA-Z_]\w*)"?', re.I
)
_RE_RENAME_TABLE = re.compile(
    r'ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?"?([a-zA-Z_]\w*)"?\s+'
    r'RENAME\s+TO\s+"?([a-zA-Z_]\w*)"?', re.I
)
_RE_CREATE_VIEW = re.compile(
    r'CREATE\s+(?:OR\s+REPLACE\s+)?(?:MATERIALIZED\s+)?VIEW\s+'
    r'(?:IF\s+NOT\s+EXISTS\s+)?"?([a-zA-Z_]\w*)"?', re.I
)
# Exige separador de cláusula depois da tabela. Assim `EXTRACT(YEAR FROM
# created_at)` e `EXTRACT(... FROM d.data_prazo)` não viram tabelas fictícias.
_RE_REF_FROM = re.compile(
    r'\b(?:FROM|JOIN)\s+(?:"?[a-z_][a-z0-9_]*"?\.)?'
    r'"?([a-z_][a-z0-9_]*)"?(?=\s|,|;|$)', re.I
)
_RE_REF_INSERT = re.compile(r'\bINSERT\s+INTO\s+"?([a-z_][a-z0-9_]*)"?', re.I)
_RE_REF_UPDATE = re.compile(r'\bUPDATE\s+"?([a-z_][a-z0-9_]*)"?\s+SET\b', re.I)
_RE_REF_DELETE = re.compile(r'\bDELETE\s+FROM\s+"?([a-z_][a-z0-9_]*)"?', re.I)
_RE_INSERT_COLUNAS = re.compile(
    r'\bINSERT\s+INTO\s+"?([a-z_][a-z0-9_]*)"?\s*\(([^()]*)\)', re.I | re.S
)
_SQL_CONSTRAINT_KEYWORDS = {
    "primary", "constraint", "unique", "foreign", "check", "like", "exclude"
}
_SQL_START = re.compile(
    r"^\s*(?:SELECT\b|WITH\b|INSERT\s+INTO\b|UPDATE\b|DELETE\s+FROM\b)", re.I
)


def _script_directory() -> ScriptDirectory:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(config)


def _constante_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _strings_do_call(node: ast.Call) -> list[str]:
    return [
        child.value for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    ]


def _nome_coluna(node: ast.AST | None) -> str | None:
    if not isinstance(node, ast.Call) or not node.args:
        return None
    return _constante_string(node.args[0])


def _colunas_do_ddl(sql: str, tabela: str) -> set[str]:
    sql = re.sub(r"--[^\n]*", "", sql)
    match = re.search(
        r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"?%s"?\s*\((.*)\)\s*;?'
        % re.escape(tabela), sql, re.I | re.S
    )
    if not match:
        return set()
    partes, atual, profundidade = [], [], 0
    for char in match.group(1):
        if char == "(":
            profundidade += 1
        elif char == ")":
            profundidade -= 1
        if char == "," and profundidade == 0:
            partes.append("".join(atual)); atual = []
        else:
            atual.append(char)
    partes.append("".join(atual))
    colunas = set()
    for parte in partes:
        tokens = parte.strip().split()
        if tokens:
            nome = tokens[0].strip('"').lower()
            if nome not in _SQL_CONSTRAINT_KEYWORDS:
                colunas.add(nome)
    return colunas


def _definir_tabela(tabelas: dict[str, set[str]], nome: str, colunas: set[str]) -> None:
    if nome not in tabelas:
        tabelas[nome] = {coluna.lower() for coluna in colunas}


def _aplicar_batch_alter(upgrade: ast.AST, tabelas: dict[str, set[str]]) -> None:
    for node in ast.walk(upgrade):
        if not isinstance(node, ast.With):
            continue
        for item in node.items:
            context = item.context_expr
            if not (
                isinstance(context, ast.Call)
                and isinstance(context.func, ast.Attribute)
                and context.func.attr == "batch_alter_table"
                and context.args
            ):
                continue
            tabela = _constante_string(context.args[0])
            alias = item.optional_vars.id if isinstance(item.optional_vars, ast.Name) else None
            if not tabela or not alias:
                continue
            for child in ast.walk(node):
                if not (
                    isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Attribute)
                    and isinstance(child.func.value, ast.Name)
                    and child.func.value.id == alias
                ):
                    continue
                if child.func.attr == "add_column" and child.args:
                    coluna = _nome_coluna(child.args[0])
                    if coluna:
                        tabelas.setdefault(tabela, set()).add(coluna.lower())
                elif child.func.attr == "drop_column" and child.args:
                    coluna = _constante_string(child.args[0])
                    if coluna and tabela in tabelas:
                        tabelas[tabela].discard(coluna.lower())


@functools.lru_cache(maxsize=1)
def _conjunto_a() -> tuple[dict[str, frozenset[str]], frozenset[str]]:
    tabelas: dict[str, set[str]] = {}
    views: set[str] = set()
    for revision in reversed(list(_script_directory().walk_revisions())):
        path = Path(revision.path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        upgrade = next(
            (node for node in tree.body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
             and node.name == "upgrade"),
            None,
        )
        if upgrade is None:
            continue
        _aplicar_batch_alter(upgrade, tabelas)
        for node in ast.walk(upgrade):
            if not isinstance(node, ast.Call):
                continue
            attr = node.func.attr if isinstance(node.func, ast.Attribute) else ""
            if attr == "create_table" and node.args:
                tabela = _constante_string(node.args[0])
                colunas = {
                    coluna for coluna in (_nome_coluna(arg) for arg in node.args[1:])
                    if coluna
                }
                if tabela:
                    _definir_tabela(tabelas, tabela, colunas)
            elif attr == "drop_table" and node.args:
                tabela = _constante_string(node.args[0])
                if tabela:
                    tabelas.pop(tabela, None)
            elif attr == "add_column" and len(node.args) >= 2:
                tabela, coluna = _constante_string(node.args[0]), _nome_coluna(node.args[1])
                if tabela and coluna:
                    tabelas.setdefault(tabela, set()).add(coluna.lower())
            elif attr == "drop_column" and len(node.args) >= 2:
                tabela, coluna = _constante_string(node.args[0]), _constante_string(node.args[1])
                if tabela and coluna and tabela in tabelas:
                    tabelas[tabela].discard(coluna.lower())
            elif attr == "alter_column" and len(node.args) >= 2:
                tabela = _constante_string(node.args[0])
                coluna_atual = _constante_string(node.args[1])
                coluna_nova = next(
                    (
                        _constante_string(keyword.value)
                        for keyword in node.keywords
                        if keyword.arg == "new_column_name"
                    ),
                    None,
                )
                if tabela and coluna_atual and coluna_nova:
                    colunas = tabelas.setdefault(tabela, set())
                    colunas.discard(coluna_atual.lower())
                    colunas.add(coluna_nova.lower())
            for sql in _strings_do_call(node):
                for match in _RE_CREATE_TABLE.finditer(sql):
                    tabela = match.group(1).lower()
                    _definir_tabela(tabelas, tabela, _colunas_do_ddl(sql, tabela))
                for match in _RE_DROP_TABLE.finditer(sql):
                    tabelas.pop(match.group(1).lower(), None)
                for match in _RE_ALTER_TABLE.finditer(sql):
                    tabela = match.group(1).lower()
                    for coluna in _RE_ADD_COLUMN.findall(sql):
                        tabelas.setdefault(tabela, set()).add(coluna.lower())
                    for coluna in _RE_DROP_COLUMN.findall(sql):
                        if tabela in tabelas:
                            tabelas[tabela].discard(coluna.lower())
                for match in _RE_RENAME_TABLE.finditer(sql):
                    origem, destino = match.group(1).lower(), match.group(2).lower()
                    if origem in tabelas:
                        tabelas[destino] = tabelas.pop(origem)
                views.update(match.group(1).lower() for match in _RE_CREATE_VIEW.finditer(sql))
    return ({k: frozenset(v) for k, v in tabelas.items()}, frozenset(views))


def _importar_app_completo() -> None:
    import app.main  # noqa: F401


def _tabelas_runtime_auto_bootstrap() -> set[str]:
    tabelas: set[str] = set()
    for path in APP_DIR.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                tabelas.update(
                    match.group(1).lower()
                    for match in _RE_CREATE_TABLE_GUARDADO.finditer(node.value)
                )
    return tabelas


def _sql_executavel(valor: str) -> str | None:
    candidato = valor.lstrip()
    while candidato.startswith("--"):
        _, separador, resto = candidato.partition("\n")
        if not separador:
            return None
        candidato = resto.lstrip()
    return candidato if _SQL_START.match(candidato) else None


def _tabelas_referenciadas_raw() -> tuple[set[str], dict[str, set[str]]]:
    tabelas: set[str] = set()
    cols_por_tabela: dict[str, set[str]] = {}
    for path in APP_DIR.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            sql = _sql_executavel(node.value)
            if sql is None:
                continue
            if re.match(r"^(?:SELECT|WITH)\b", sql, re.I):
                tabelas.update(m.group(1).lower() for m in _RE_REF_FROM.finditer(sql))
            elif re.match(r"^INSERT\s+INTO\b", sql, re.I):
                tabelas.update(m.group(1).lower() for m in _RE_REF_INSERT.finditer(sql))
                for match in _RE_INSERT_COLUNAS.finditer(sql):
                    tabela = match.group(1).lower()
                    colunas = {
                        c.strip().strip('"').lower()
                        for c in match.group(2).split(",") if c.strip()
                    }
                    cols_por_tabela.setdefault(tabela, set()).update(colunas)
            elif re.match(r"^UPDATE\b", sql, re.I):
                tabelas.update(m.group(1).lower() for m in _RE_REF_UPDATE.finditer(sql))
            elif re.match(r"^DELETE\s+FROM\b", sql, re.I):
                tabelas.update(m.group(1).lower() for m in _RE_REF_DELETE.finditer(sql))
    return tabelas - _RUIDO_SQL, cols_por_tabela


def test_scanner_raw_ignora_prosa_com_palavras_sql():
    assert _sql_executavel("texto created_at from d select f") is None
    assert _sql_executavel("SELECT id FROM users") == "SELECT id FROM users"
    assert not _RE_REF_FROM.search("SELECT EXTRACT(YEAR FROM created_at)")
    assert not _RE_REF_FROM.search("SELECT EXTRACT(YEAR FROM d.data_prazo)")


def test_grafo_alembic_head_unico_e_canonico():
    assert _script_directory().get_heads() == [HEAD_REVISION]


def test_schema_migrations_contem_todas_as_tabelas_e_colunas_do_orm():
    from app.core.database import Base
    _importar_app_completo()
    tabelas, _ = _conjunto_a()
    faltas_tabela, faltas_coluna = [], {}
    for nome, tabela in Base.metadata.tables.items():
        if nome not in tabelas:
            faltas_tabela.append(nome)
        else:
            faltantes = sorted(set(tabela.columns.keys()) - set(tabelas[nome]))
            if faltantes:
                faltas_coluna[nome] = faltantes
    assert not faltas_tabela, f"Model ORM sem CREATE TABLE na cadeia: {faltas_tabela}"
    assert not faltas_coluna, f"Colunas ORM sem migration: {faltas_coluna}"


def test_toda_tabela_raw_referenciada_esta_classificada():
    tabelas, views = _conjunto_a()
    referenciadas, _ = _tabelas_referenciadas_raw()
    conhecidas = set(tabelas) | set(views) | _tabelas_runtime_auto_bootstrap() | FALSOS_POSITIVOS_SQL
    faltantes = sorted(referenciadas - conhecidas)
    assert not faltantes, f"Tabela(s) raw sem classificação: {faltantes}"


def test_inventario_minimo_raw_sql_e_views_existe_na_cadeia():
    tabelas, views = _conjunto_a()
    assert RAW_SQL_TABLES_ESPERADAS <= set(tabelas)
    assert VIEWS_ESPERADAS <= set(views)


def test_colunas_de_insert_raw_existem_na_cadeia():
    tabelas, _ = _conjunto_a()
    _, cols_por_tabela = _tabelas_referenciadas_raw()
    runtime = _tabelas_runtime_auto_bootstrap()
    faltas = {}
    for tabela, colunas in cols_por_tabela.items():
        if tabela in runtime or tabela in FALSOS_POSITIVOS_SQL:
            continue
        faltantes = sorted(colunas - set(tabelas.get(tabela, frozenset())))
        if faltantes:
            faltas[tabela] = faltantes
    assert not faltas, f"Colunas de INSERT raw-SQL sem migration: {faltas}"


@pytest.mark.skipif(not os.getenv("RUN_DB_TESTS"), reason="requer PostgreSQL")
def test_upgrade_head_reconstroi_banco_vazio_real():
    import subprocess
    import psycopg2
    from sqlalchemy import create_engine, inspect

    url = os.environ["SCHEMA_CHECK_DATABASE_URL"]
    parsed = urlsplit(url)
    nome_db = f"ejc_dr_{os.getpid()}"
    async_url = urlunsplit(("postgresql+asyncpg", parsed.netloc, f"/{nome_db}", "", ""))
    sync_url = urlunsplit(("postgresql+psycopg2", parsed.netloc, f"/{nome_db}", "", ""))

    def conectar_admin():
        conn = psycopg2.connect(
            dbname="postgres", user=unquote(parsed.username or ""),
            password=unquote(parsed.password or ""), host=parsed.hostname,
            port=parsed.port,
        )
        conn.autocommit = True
        return conn

    conn = conectar_admin()
    try:
        cursor = conn.cursor()
        try:
            cursor.execute(f'CREATE DATABASE "{nome_db}"')
        finally:
            cursor.close()
    finally:
        conn.close()

    try:
        env = {
            **os.environ,
            "DATABASE_URL": async_url,
            "DATABASE_URL_SYNC": sync_url,
            "SCHEMA_CHECK_DATABASE_URL": sync_url,
        }
        resultado = subprocess.run(
            ["python", "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR, env=env, capture_output=True, text=True,
        )
        assert resultado.returncode == 0, resultado.stderr or resultado.stdout

        engine = create_engine(sync_url)
        try:
            inspector = inspect(engine)
            tabelas, views = set(inspector.get_table_names()), set(inspector.get_view_names())
            _importar_app_completo()
            from app.core.database import Base
            assert not sorted(set(Base.metadata.tables) - tabelas)
            assert not sorted(RAW_SQL_TABLES_ESPERADAS - tabelas)
            assert not sorted(VIEWS_ESPERADAS - views)
        finally:
            engine.dispose()
    finally:
        conn = conectar_admin()
        try:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()", (nome_db,)
                )
                cursor.execute(f'DROP DATABASE IF EXISTS "{nome_db}"')
            finally:
                cursor.close()
        finally:
            conn.close()
