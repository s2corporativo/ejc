"""Paridade de schema para Disaster Recovery (migrations 040-043 perdidas).

Contexto: as migrations 040-043 foram aplicadas direto no container e nunca
versionadas; `044_recover_head.py` é um stub `pass` que só religa o grafo
039 -> 044. A `053_reconcile_schema.py` (e migrations posteriores) compensa o
schema perdido. Este arquivo PROVA, de forma determinística, que a cadeia
completa de migrations reconstrói TODO o schema esperado em um banco limpo
(DR/staging) — ou seja, que o GAP das migrations perdidas é vazio.

Duas camadas (mesma prova de docs/audit/RECONCILIACAO_SCHEMA_DR_2026-07-26.md):

1. SEM banco (roda sempre): parse estático (AST) da função upgrade() de todas
   as migrations em ordem topológica -> conjunto A (tabelas/colunas criadas,
   com semântica Postgres: CREATE TABLE IF NOT EXISTS repetido é NO-OP, a
   primeira definição vence e coluna nova só entra via ADD COLUMN explícito);
   compara com o conjunto B = Base.metadata do APP COMPLETO (import app.main,
   que registra também models definidos em routers) + tabelas raw-SQL
   DESCOBERTAS por varredura AST das strings SQL de backend/app. Se um model
   ou consulta raw-SQL nova nascer sem migration, o teste quebra ANTES de
   chegar em produção.

2. COM banco (RUN_DB_TESTS=1, mesmo padrão dos *_dblevel.py): provisiona um
   BANCO NOVO E VAZIO (CREATE DATABASE), roda `alembic upgrade head` nele e
   verifica via inspector que todas as tabelas esperadas existem — prova real
   de reconstrução em DR, independente do estado do banco do CI.

Tabelas AUTO-BOOTSTRAP (criam-se sozinhas em runtime via CREATE TABLE IF NOT
EXISTS nos services) são descobertas dinamicamente e ficam FORA do escopo —
não precisam de migration.

Limitação documentada (ver seção "Limitações conhecidas" do doc de auditoria):
para tabelas raw-SQL, a paridade de COLUNA cobre apenas as colunas nomeadas em
`INSERT INTO tabela (col, ...)` — listas de INSERT são parseáveis de forma
determinística; extrair colunas de SELECT/WHERE arbitrários exigiria um parser
SQL completo com alto risco de falso positivo.
"""
from __future__ import annotations

import ast
import functools
import os
import re
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).resolve().parents[1]
VERSIONS_DIR = BACKEND_DIR / "alembic" / "versions"
APP_DIR = BACKEND_DIR / "app"

# Head canônico — atualizar no MESMO PR que adicionar migration nova
# (mesma regra de test_alembic_single_head.py).
HEAD_REVISION = "123_legal_doc_ai_log_vinculo"

# Inventário MÍNIMO de tabelas 100% raw-SQL (sem model ORM) que o código
# consulta e que a cadeia de migrations PRECISA criar (levantadas na auditoria
# de 2026-07-26; a maioria nasceu nas perdidas 040-043 e foi recriada pela
# 050/053). É um piso explícito e legível; a COBERTURA REAL vem da descoberta
# dinâmica em test_toda_tabela_raw_referenciada_esta_classificada.
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

# Views que o código consulta e que a cadeia precisa criar.
VIEWS_ESPERADAS = {"vw_atividades"}

# Nomes capturados pelo scanner de SQL que NÃO são tabelas do app — cada
# entrada precisa de justificativa. Crescer esta lista exige revisão humana.
FALSOS_POSITIVOS_SQL = {
    "alembic_version",  # tabela de controle do próprio Alembic
}

# Ruído estrutural do scanner (funções set-returning, catálogos, keywords).
_RUIDO_SQL = {
    "information_schema", "unnest", "generate_series", "jsonb_each",
    "jsonb_array_elements", "jsonb_array_elements_text",
    "regexp_split_to_table", "lateral", "only", "select", "current_date",
    "current_timestamp", "duplicate", "excluded",
}


# ── Regexes de DDL/DML ───────────────────────────────────────────────────────

_RE_CREATE_TABLE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?\"?([a-zA-Z_]\w*)\"?", re.I
)
_RE_CREATE_TABLE_GUARDADO = re.compile(
    r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+\"?([a-zA-Z_]\w*)\"?", re.I
)
_RE_DROP_TABLE = re.compile(
    r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?\"?([a-zA-Z_]\w*)\"?", re.I
)
_RE_ALTER_TABLE = re.compile(r"ALTER\s+TABLE\s+(?:ONLY\s+)?\"?([a-zA-Z_]\w*)\"?", re.I)
_RE_ADD_COLUMN = re.compile(
    r"ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?\"?([a-zA-Z_]\w*)\"?", re.I
)
_RE_DROP_COLUMN = re.compile(
    r"DROP\s+COLUMN\s+(?:IF\s+EXISTS\s+)?\"?([a-zA-Z_]\w*)\"?", re.I
)
_RE_RENAME_TABLE = re.compile(
    r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?\"?([a-zA-Z_]\w*)\"?\s+RENAME\s+TO\s+"
    r"\"?([a-zA-Z_]\w*)\"?",
    re.I,
)
_RE_CREATE_VIEW = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:MATERIALIZED\s+)?VIEW\s+"
    r"(?:IF\s+NOT\s+EXISTS\s+)?\"?([a-zA-Z_]\w*)\"?",
    re.I,
)
_RE_REF_FROM = re.compile(r"\b(?:FROM|JOIN)\s+\"?([a-z_][a-z0-9_]*)\"?", re.I)
_RE_REF_INSERT = re.compile(r"\bINSERT\s+INTO\s+\"?([a-z_][a-z0-9_]*)\"?", re.I)
_RE_REF_UPDATE = re.compile(
    r"\bUPDATE\s+\"?([a-z_][a-z0-9_]*)\"?\s+SET\b", re.I
)
_RE_REF_DELETE = re.compile(r"\bDELETE\s+FROM\s+\"?([a-z_][a-z0-9_]*)\"?", re.I)
_RE_INSERT_COLUNAS = re.compile(
    r"\bINSERT\s+INTO\s+\"?([a-z_][a-z0-9_]*)\"?\s*\(([^()]*)\)", re.I | re.S
)
_SQL_CONSTRAINT_KEYWORDS = {
    "primary", "constraint", "unique", "foreign", "check", "like", "exclude",
}


def _script_directory() -> ScriptDirectory:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(config)


def _strings_do_call(node: ast.Call) -> list[str]:
    """Todas as constantes-string dentro do call (cobre sa.text, f-strings)."""
    return [
        n.value
        for n in ast.walk(node)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]


def _colunas_do_ddl(sql: str, tabela: str) -> set[str]:
    """Extrai nomes de coluna de um CREATE TABLE em SQL bruto."""
    sql = re.sub(r"--[^\n]*", "", sql)  # remove comentários SQL inline
    m = re.search(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?\"?%s\"?\s*\((.*)\)\s*;?"
        % re.escape(tabela),
        sql,
        re.I | re.S,
    )
    if not m:
        return set()
    partes: list[str] = []
    atual: list[str] = []
    profundidade = 0
    for ch in m.group(1):
        if ch == "(":
            profundidade += 1
        elif ch == ")":
            profundidade -= 1
        if ch == "," and profundidade == 0:
            partes.append("".join(atual))
            atual = []
        else:
            atual.append(ch)
    partes.append("".join(atual))
    colunas: set[str] = set()
    for parte in partes:
        tokens = parte.strip().split()
        if not tokens:
            continue
        nome = tokens[0].strip('"').lower()
        if nome in _SQL_CONSTRAINT_KEYWORDS:
            continue
        colunas.add(nome)
    return colunas


# ── Conjunto A: o que a cadeia de migrations cria ────────────────────────────


def _definir_tabela(tabelas: dict[str, set[str]], nome: str, colunas: set[str]) -> None:
    """Semântica Postgres: se a tabela JÁ existe neste ponto da cadeia, um
    CREATE TABLE IF NOT EXISTS repetido é NO-OP — a primeira definição vence e
    colunas novas só entram via ADD COLUMN explícito. (Um CREATE TABLE sem
    guarda sobre tabela existente falharia o upgrade real; na cadeia válida ele
    só ocorre quando a tabela não existe, então a mesma regra serve.)"""
    if nome not in tabelas:
        tabelas[nome] = {c.lower() for c in colunas}


@functools.lru_cache(maxsize=1)
def _conjunto_a() -> tuple[dict[str, frozenset[str]], frozenset[str]]:
    """(tabelas -> colunas, views) criadas pela cadeia completa em ordem
    topológica (base -> head), considerando drops/renames intermediários.
    SOMENTE a função upgrade() é analisada (downgrade contém os drops reversos).
    """
    script = _script_directory()
    ordenadas = list(reversed(list(script.walk_revisions())))  # base -> head
    tabelas: dict[str, set[str]] = {}
    views: set[str] = set()

    for rev in ordenadas:
        path = Path(rev.path)
        fonte = path.read_text(encoding="utf-8")
        tree = ast.parse(fonte, filename=str(path))
        upgrade = next(
            (
                n
                for n in tree.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name == "upgrade"
            ),
            None,
        )
        if upgrade is None:
            continue
        for node in ast.walk(upgrade):
            if not isinstance(node, ast.Call):
                continue
            strings = _strings_do_call(node)
            func = node.func
            attr = func.attr if isinstance(func, ast.Attribute) else ""

            if attr == "create_table" and node.args:
                nome = node.args[0].value if isinstance(node.args[0], ast.Constant) else ""
                colunas = {
                    arg.args[0].value
                    for arg in node.args[1:]
                    if isinstance(arg, ast.Call)
                    and isinstance(arg.func, ast.Attribute)
                    and arg.func.attr == "Column"
                    and arg.args
                    and isinstance(arg.args[0], ast.Constant)
                    and isinstance(arg.args[0].value, str)
                }
                if nome:
                    _definir_tabela(tabelas, nome, colunas)

            elif attr == "drop_table" and node.args:
                nome = node.args[0].value if isinstance(node.args[0], ast.Constant) else ""
                tabelas.pop(nome, None)

            elif attr == "add_column" and len(node.args) >= 2:
                tabela = node.args[0].value if isinstance(node.args[0], ast.Constant) else ""
                col_call = node.args[1]
                coluna = (
                    col_call.args[0].value
                    if isinstance(col_call, ast.Call)
                    and col_call.args
                    and isinstance(col_call.args[0], ast.Constant)
                    else ""
                )
                if tabela and coluna:
                    tabelas.setdefault(tabela, set()).add(coluna.lower())

            elif attr == "drop_column" and len(node.args) >= 2:
                tabela = node.args[0].value if isinstance(node.args[0], ast.Constant) else ""
                coluna = node.args[1].value if isinstance(node.args[1], ast.Constant) else ""
                if tabela in tabelas:
                    tabelas[tabela].discard(coluna.lower())

            for sql in strings:
                for m in _RE_CREATE_TABLE.finditer(sql):
                    nome = m.group(1).lower()
                    _definir_tabela(tabelas, nome, _colunas_do_ddl(sql, nome))
                for m in _RE_DROP_TABLE.finditer(sql):
                    tabelas.pop(m.group(1).lower(), None)
                for m in _RE_ALTER_TABLE.finditer(sql):
                    tabela = m.group(1).lower()
                    for c in _RE_ADD_COLUMN.findall(sql):
                        tabelas.setdefault(tabela, set()).add(c.lower())
                    for c in _RE_DROP_COLUMN.findall(sql):
                        if tabela in tabelas:
                            tabelas[tabela].discard(c.lower())
                for m in _RE_RENAME_TABLE.finditer(sql):
                    old, new = m.group(1).lower(), m.group(2).lower()
                    if old in tabelas:
                        tabelas[new] = tabelas.pop(old)
                for m in _RE_CREATE_VIEW.finditer(sql):
                    views.add(m.group(1).lower())

    return (
        {nome: frozenset(cols) for nome, cols in tabelas.items()},
        frozenset(views),
    )


def _importar_app_completo():
    # Registra modelos declarados em routers/services além dos imports explícitos.
    import app.main  # noqa: F401


def _tabelas_runtime_auto_bootstrap() -> set[str]:
    """Descobre tabelas criadas em runtime por CREATE TABLE IF NOT EXISTS."""
    out: set[str] = set()
    for path in APP_DIR.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            for m in _RE_CREATE_TABLE_GUARDADO.finditer(node.value):
                out.add(m.group(1).lower())
    return out


def _tabelas_referenciadas_raw() -> tuple[set[str], dict[str, set[str]]]:
    """(tabelas, colunas de INSERT) descobertas nas strings SQL de app/."""
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
            for regex in (_RE_REF_FROM, _RE_REF_INSERT, _RE_REF_UPDATE, _RE_REF_DELETE):
                tabelas.update(m.group(1).lower() for m in regex.finditer(sql))
            for m in _RE_INSERT_COLUNAS.finditer(sql):
                tabela = m.group(1).lower()
                colunas = {
                    c.strip().strip('"').lower()
                    for c in m.group(2).split(",")
                    if c.strip()
                }
                cols_por_tabela.setdefault(tabela, set()).update(colunas)
    tabelas -= _RUIDO_SQL
    return tabelas, cols_por_tabela


def test_grafo_alembic_head_unico_e_canonico():
    script = _script_directory()
    assert script.get_heads() == [HEAD_REVISION]


def test_schema_migrations_contem_todas_as_tabelas_e_colunas_do_orm():
    from app.core.database import Base

    _importar_app_completo()
    tabelas_a, _ = _conjunto_a()
    faltas_tabela: list[str] = []
    faltas_coluna: dict[str, list[str]] = {}
    for nome, tabela in Base.metadata.tables.items():
        if nome not in tabelas_a:
            faltas_tabela.append(nome)
            continue
        faltantes = sorted(set(tabela.columns.keys()) - set(tabelas_a[nome]))
        if faltantes:
            faltas_coluna[nome] = faltantes
    assert not faltas_tabela, f"Model ORM sem CREATE TABLE na cadeia: {faltas_tabela}"
    assert not faltas_coluna, f"Colunas ORM sem migration: {faltas_coluna}"


def test_toda_tabela_raw_referenciada_esta_classificada():
    tabelas_a, views_a = _conjunto_a()
    referenciadas, _ = _tabelas_referenciadas_raw()
    runtime = _tabelas_runtime_auto_bootstrap()
    conhecidas = set(tabelas_a) | set(views_a) | runtime | FALSOS_POSITIVOS_SQL
    faltantes = sorted(referenciadas - conhecidas)
    assert not faltantes, (
        "Tabela(s) referenciada(s) em SQL de app/ sem migration, view, auto-bootstrap "
        f"ou justificativa: {faltantes}"
    )


def test_inventario_minimo_raw_sql_e_views_existe_na_cadeia():
    tabelas_a, views_a = _conjunto_a()
    assert RAW_SQL_TABLES_ESPERADAS <= set(tabelas_a)
    assert VIEWS_ESPERADAS <= set(views_a)


def test_colunas_de_insert_raw_existem_na_cadeia():
    tabelas_a, _ = _conjunto_a()
    _, cols_por_tabela = _tabelas_referenciadas_raw()
    runtime = _tabelas_runtime_auto_bootstrap()
    faltas: dict[str, list[str]] = {}
    for tabela, colunas in cols_por_tabela.items():
        if tabela in runtime or tabela in FALSOS_POSITIVOS_SQL:
            continue
        conhecidas = set(tabelas_a.get(tabela, frozenset()))
        faltantes = sorted(colunas - conhecidas)
        if faltantes:
            faltas[tabela] = faltantes
    assert not faltas, f"Colunas de INSERT raw-SQL sem migration: {faltas}"


@pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer PostgreSQL para criar banco DR temporário",
)
def test_upgrade_head_reconstroi_banco_vazio_real():
    """Prova real: cria banco novo, aplica head e verifica inventário esperado."""
    import subprocess
    from urllib.parse import urlsplit, urlunsplit

    import psycopg
    from sqlalchemy import create_engine, inspect

    url = os.environ["SCHEMA_CHECK_DATABASE_URL"]
    parsed = urlsplit(url)
    nome_db = f"ejc_dr_{os.getpid()}"
    admin_url = urlunsplit((parsed.scheme, parsed.netloc, "/postgres", "", ""))
    db_url = urlunsplit((parsed.scheme, parsed.netloc, f"/{nome_db}", "", ""))
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{nome_db}"')
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
            insp = inspect(engine)
            tabelas = set(insp.get_table_names())
            views = set(insp.get_view_names())
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
        with psycopg.connect(admin_url, autocommit=True) as conn:
            conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (nome_db,),
            )
            conn.execute(f'DROP DATABASE IF EXISTS "{nome_db}"')
