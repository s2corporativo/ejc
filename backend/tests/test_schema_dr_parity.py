"""Paridade de schema e reconstrução de Disaster Recovery.

A prova compara o schema reconstruído pela cadeia Alembic com os models ORM e
com as consultas SQL brutas do aplicativo. Também cria um banco PostgreSQL
vazio e executa `alembic upgrade head` para validar a recuperação real.
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
VERSIONS_DIR = BACKEND_DIR / "alembic" / "versions"
APP_DIR = BACKEND_DIR / "app"
HEAD_REVISION = "123_legal_doc_ai_log_vinculo"

RAW_SQL_TABLES_ESPERADAS = {
    "agenda_eventos",
    "areas",
    "case_ambiental",
    "case_etiquetas",
    "client_pending_items",
    "document_access_log",
    "domain_events",
    "due_diligence_templates",
    "inadimplencia_alerts",
    "indice_risco_historico",
    "kanban_columns",
    "memoria_institucional",
    "modelos_documentos",
    "office_contracts",
    "office_expenses",
    "partner_withdrawals",
    "peca_codigo_contador",
    "portal_mensagens",
    "pricing_rules",
    "score_juridico",
    "teses_vitoriosas",
}
VIEWS_ESPERADAS = {"vw_atividades"}

# Catálogos/controladores do próprio PostgreSQL/Alembic, não tabelas da app.
FALSOS_POSITIVOS_SQL = {
    "alembic_version",
    "pg_extension",
    "pg_stat_activity",
}

_RUIDO_SQL = {
    "information_schema",
    "unnest",
    "generate_series",
    "jsonb_each",
    "jsonb_array_elements",
    "jsonb_array_elements_text",
    "regexp_split_to_table",
    "lateral",
    "only",
    "select",
    "current_date",
    "current_timestamp",
    "duplicate",
    "excluded",
}

_RE_CREATE_TABLE = re.compile(
    r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"?([a-zA-Z_]\w*)"?',
    re.I,
)
_RE_CREATE_TABLE_GUARDADO = re.compile(
    r'CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+"?([a-zA-Z_]\w*)"?',
    re.I,
)
_RE_DROP_TABLE = re.compile(
    r'DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?"?([a-zA-Z_]\w*)"?',
    re.I,
)
_RE_ALTER_TABLE = re.compile(
    r'ALTER\s+TABLE\s+(?:ONLY\s+)?"?([a-zA-Z_]\w*)"?',
    re.I,
)
_RE_ADD_COLUMN = re.compile(
    r'ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?"?([a-zA-Z_]\w*)"?',
    re.I,
)
_RE_DROP_COLUMN = re.compile(
    r'DROP\s+COLUMN\s+(?:IF\s+EXISTS\s+)?"?([a-zA-Z_]\w*)"?',
    re.I,
)
_RE_RENAME_TABLE = re.compile(
    r'ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?"?([a-zA-Z_]\w*)"?\s+RENAME\s+TO\s+'
    r'"?([a-zA-Z_]\w*)"?',
    re.I,
)
_RE_CREATE_VIEW = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:MATERIALIZED\s+)?VIEW\s+"
    r'(?:IF\s+NOT\s+EXISTS\s+)?"?([a-zA-Z_]\w*)"?',
    re.I,
)
_RE_REF_FROM = re.compile(
    r'\b(?:FROM|JOIN)\s+"?([a-z_][a-z0-9_]*)"?',
    re.I,
)
_RE_REF_INSERT = re.compile(
    r'\bINSERT\s+INTO\s+"?([a-z_][a-z0-9_]*)"?',
    re.I,
)
_RE_REF_UPDATE = re.compile(
    r'\bUPDATE\s+"?([a-z_][a-z0-9_]*)"?\s+SET\b',
    re.I,
)
_RE_REF_DELETE = re.compile(
    r'\bDELETE\s+FROM\s+"?([a-z_][a-z0-9_]*)"?',
    re.I,
)
_RE_INSERT_COLUNAS = re.compile(
    r'\bINSERT\s+INTO\s+"?([a-z_][a-z0-9_]*)"?\s*\(([^()]*)\)',
    re.I | re.S,
)
_SQL_CONSTRAINT_KEYWORDS = {
    "primary",
    "constraint",
    "unique",
    "foreign",
    "check",
    "like",
    "exclude",
}


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
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    ]


def _nome_coluna(column_call: ast.AST | None) -> str | None:
    if not isinstance(column_call, ast.Call) or not column_call.args:
        return None
    return _constante_string(column_call.args[0])


def _colunas_do_ddl(sql: str, tabela: str) -> set[str]:
    sql = re.sub(r"--[^\n]*", "", sql)
    match = re.search(
        r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"?%s"?\s*\((.*)\)\s*;?'
        % re.escape(tabela),
        sql,
        re.I | re.S,
    )
    if not match:
        return set()

    partes: list[str] = []
    atual: list[str] = []
    profundidade = 0
    for char in match.group(1):
        if char == "(":
            profundidade += 1
        elif char == ")":
            profundidade -= 1
        if char == "," and profundidade == 0:
            partes.append("".join(atual))
            atual = []
        else:
            atual.append(char)
    partes.append("".join(atual))

    colunas: set[str] = set()
    for parte in partes:
        tokens = parte.strip().split()
        if not tokens:
            continue
        nome = tokens[0].strip('"').lower()
        if nome not in _SQL_CONSTRAINT_KEYWORDS:
            colunas.add(nome)
    return colunas


def _definir_tabela(
    tabelas: dict[str, set[str]],
    nome: str,
    colunas: set[str],
) -> None:
    if nome not in tabelas:
        tabelas[nome] = {coluna.lower() for coluna in colunas}


def _aplicar_batch_alter(
    upgrade: ast.AST,
    tabelas: dict[str, set[str]],
) -> None:
    """Interpreta `with op.batch_alter_table('t') as batch_op`.

    A migration 038 usa esse formato para criar `teses.area_direito`. O parser
    antigo só reconhecia `op.add_column('t', Column(...))` e acusava um falso
    desvio de schema no DR.
    """
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
            alias = (
                item.optional_vars.id
                if isinstance(item.optional_vars, ast.Name)
                else None
            )
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
    script = _script_directory()
    revisoes = list(reversed(list(script.walk_revisions())))
    tabelas: dict[str, set[str]] = {}
    views: set[str] = set()

    for revision in revisoes:
        path = Path(revision.path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        upgrade = next(
            (
                node
                for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "upgrade"
            ),
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
                    coluna
                    for coluna in (
                        _nome_coluna(argumento) for argumento in node.args[1:]
                    )
                    if coluna
                }
                if tabela:
                    _definir_tabela(tabelas, tabela, colunas)
            elif attr == "drop_table" and node.args:
                tabela = _constante_string(node.args[0])
                if tabela:
                    tabelas.pop(tabela, None)
            elif attr == "add_column" and len(node.args) >= 2:
                tabela = _constante_string(node.args[0])
                coluna = _nome_coluna(node.args[1])
                if tabela and coluna:
                    tabelas.setdefault(tabela, set()).add(coluna.lower())
            elif attr == "drop_column" and len(node.args) >= 2:
                tabela = _constante_string(node.args[0])
                coluna = _constante_string(node.args[1])
                if tabela and coluna and tabela in tabelas:
                    tabelas[tabela].discard(coluna.lower())

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
                    origem, destino = (
                        match.group(1).lower(),
                        match.group(2).lower(),
                    )
                    if origem in tabelas:
                        tabelas[destino] = tabelas.pop(origem)
                for match in _RE_CREATE_VIEW.finditer(sql):
                    views.add(match.group(1).lower())

    return (
        {nome: frozenset(colunas) for nome, colunas in tabelas.items()},
        frozenset(views),
    )


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
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            tabelas.update(
                match.group(1).lower()
                for match in _RE_CREATE_TABLE_GUARDADO.finditer(node.value)
            )
    return tabelas


def _tabelas_referenciadas_raw() -> tuple[set[str], dict[str, set[str]]]:
    """Descobre referências somente em strings com estrutura SQL completa.

    O scanner anterior aplicava `FROM <palavra>` a qualquer docstring e produzia
    tabelas fictícias como `cryptography`, `created_at` e `d`. Agora cada família
    exige o verbo SQL correspondente no mesmo literal.
    """
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
            sql = node.value
            if re.search(r"\bSELECT\b", sql, re.I):
                tabelas.update(
                    match.group(1).lower() for match in _RE_REF_FROM.finditer(sql)
                )
            if _RE_REF_INSERT.search(sql):
                tabelas.update(
                    match.group(1).lower() for match in _RE_REF_INSERT.finditer(sql)
                )
                for match in _RE_INSERT_COLUNAS.finditer(sql):
                    tabela = match.group(1).lower()
                    colunas = {
                        coluna.strip().strip('"').lower()
                        for coluna in match.group(2).split(",")
                        if coluna.strip()
                    }
                    cols_por_tabela.setdefault(tabela, set()).update(colunas)
            if _RE_REF_UPDATE.search(sql):
                tabelas.update(
                    match.group(1).lower() for match in _RE_REF_UPDATE.finditer(sql)
                )
            if _RE_REF_DELETE.search(sql):
                tabelas.update(
                    match.group(1).lower() for match in _RE_REF_DELETE.finditer(sql)
                )
    tabelas -= _RUIDO_SQL
    return tabelas, cols_por_tabela


def test_grafo_alembic_head_unico_e_canonico():
    assert _script_directory().get_heads() == [HEAD_REVISION]


def test_schema_migrations_contem_todas_as_tabelas_e_colunas_do_orm():
    from app.core.database import Base

    _importar_app_completo()
    tabelas, _ = _conjunto_a()
    faltas_tabela: list[str] = []
    faltas_coluna: dict[str, list[str]] = {}
    for nome, tabela in Base.metadata.tables.items():
        if nome not in tabelas:
            faltas_tabela.append(nome)
            continue
        faltantes = sorted(set(tabela.columns.keys()) - set(tabelas[nome]))
        if faltantes:
            faltas_coluna[nome] = faltantes
    assert not faltas_tabela, f"Model ORM sem CREATE TABLE na cadeia: {faltas_tabela}"
    assert not faltas_coluna, f"Colunas ORM sem migration: {faltas_coluna}"


def test_toda_tabela_raw_referenciada_esta_classificada():
    tabelas, views = _conjunto_a()
    referenciadas, _ = _tabelas_referenciadas_raw()
    conhecidas = (
        set(tabelas)
        | set(views)
        | _tabelas_runtime_auto_bootstrap()
        | FALSOS_POSITIVOS_SQL
    )
    faltantes = sorted(referenciadas - conhecidas)
    assert not faltantes, (
        "Tabela(s) referenciada(s) em SQL de app/ sem migration, view, "
        f"auto-bootstrap ou justificativa: {faltantes}"
    )


def test_inventario_minimo_raw_sql_e_views_existe_na_cadeia():
    tabelas, views = _conjunto_a()
    assert RAW_SQL_TABLES_ESPERADAS <= set(tabelas)
    assert VIEWS_ESPERADAS <= set(views)


def test_colunas_de_insert_raw_existem_na_cadeia():
    tabelas, _ = _conjunto_a()
    _, cols_por_tabela = _tabelas_referenciadas_raw()
    runtime = _tabelas_runtime_auto_bootstrap()
    faltas: dict[str, list[str]] = {}
    for tabela, colunas in cols_por_tabela.items():
        if tabela in runtime or tabela in FALSOS_POSITIVOS_SQL:
            continue
        faltantes = sorted(colunas - set(tabelas.get(tabela, frozenset())))
        if faltantes:
            faltas[tabela] = faltantes
    assert not faltas, f"Colunas de INSERT raw-SQL sem migration: {faltas}"


@pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer PostgreSQL para criar banco DR temporário",
)
def test_upgrade_head_reconstroi_banco_vazio_real():
    import subprocess

    import psycopg2
    from sqlalchemy import create_engine, inspect

    url = os.environ["SCHEMA_CHECK_DATABASE_URL"]
    parsed = urlsplit(url)
    nome_db = f"ejc_dr_{os.getpid()}"
    admin_url = urlunsplit((parsed.scheme, parsed.netloc, "/postgres", "", ""))
    db_url = urlunsplit((parsed.scheme, parsed.netloc, f"/{nome_db}", "", ""))

    def conectar_admin():
        conn = psycopg2.connect(
            dbname="postgres",
            user=unquote(parsed.username or ""),
            password=unquote(parsed.password or ""),
            host=parsed.hostname,
            port=parsed.port,
        )
        conn.autocommit = True
        return conn

    with conectar_admin() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f'CREATE DATABASE "{nome_db}"')
    try:
        env = {**os.environ, "DATABASE_URL": db_url}
        subprocess.run(
            ["python", "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        engine = create_engine(db_url)
        try:
            inspector = inspect(engine)
            tabelas = set(inspector.get_table_names())
            views = set(inspector.get_view_names())
            _importar_app_completo()
            from app.core.database import Base

            faltantes_orm = sorted(set(Base.metadata.tables) - tabelas)
            faltantes_raw = sorted(RAW_SQL_TABLES_ESPERADAS - tabelas)
            faltantes_views = sorted(VIEWS_ESPERADAS - views)
            assert not faltantes_orm, f"Banco DR sem tabelas ORM: {faltantes_orm}"
            assert not faltantes_raw, f"Banco DR sem tabelas raw: {faltantes_raw}"
            assert not faltantes_views, f"Banco DR sem views: {faltantes_views}"
        finally:
            engine.dispose()
    finally:
        with conectar_admin() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (nome_db,),
                )
                cursor.execute(f'DROP DATABASE IF EXISTS "{nome_db}"')
