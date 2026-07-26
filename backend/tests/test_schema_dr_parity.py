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
HEAD_REVISION = "120_chunk_pagina"

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
        tree = ast.parse(Path(rev.module.__file__).read_text())
        upgrades = [
            n
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "upgrade"
        ]
        for node in (x for u in upgrades for x in ast.walk(u)):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (
                isinstance(func, ast.Attribute)
                and getattr(func.value, "id", None) == "op"
            ):
                continue
            attr = func.attr
            args = node.args
            if attr == "create_table" and args and isinstance(args[0], ast.Constant):
                colunas = {
                    a.args[0].value
                    for a in args[1:]
                    if isinstance(a, ast.Call)
                    and getattr(a.func, "attr", None) == "Column"
                    and a.args
                    and isinstance(a.args[0], ast.Constant)
                }
                _definir_tabela(tabelas, args[0].value, colunas)
            elif attr == "add_column" and len(args) >= 2 and isinstance(args[0], ast.Constant):
                col = args[1]
                if (
                    isinstance(col, ast.Call)
                    and col.args
                    and isinstance(col.args[0], ast.Constant)
                ):
                    tabelas.setdefault(args[0].value, set()).add(
                        col.args[0].value.lower()
                    )
            elif attr == "drop_table" and args and isinstance(args[0], ast.Constant):
                tabelas.pop(args[0].value, None)
            elif attr == "drop_column" and len(args) >= 2 and all(
                isinstance(a, ast.Constant) for a in args[:2]
            ):
                tabelas.get(args[0].value, set()).discard(args[1].value.lower())
            elif attr == "rename_table" and len(args) >= 2 and all(
                isinstance(a, ast.Constant) for a in args[:2]
            ):
                tabelas[args[1].value] = tabelas.pop(args[0].value, set())
            elif attr == "alter_column" and len(args) >= 2 and all(
                isinstance(a, ast.Constant) for a in args[:2]
            ):
                for kw in node.keywords:
                    if kw.arg == "new_column_name" and isinstance(kw.value, ast.Constant):
                        tabelas.get(args[0].value, set()).discard(args[1].value.lower())
                        tabelas.setdefault(args[0].value, set()).add(
                            kw.value.value.lower()
                        )
            elif attr == "execute":
                for sql in _strings_do_call(node):
                    for antigo, novo in _RE_RENAME_TABLE.findall(sql):
                        if antigo.lower() in tabelas:
                            tabelas[novo.lower()] = tabelas.pop(antigo.lower())
                    for t in _RE_CREATE_TABLE.findall(sql):
                        t = t.lower()
                        _definir_tabela(tabelas, t, _colunas_do_ddl(sql, t))
                    for t in _RE_DROP_TABLE.findall(sql):
                        tabelas.pop(t.lower(), None)
                    for v in _RE_CREATE_VIEW.findall(sql):
                        views.add(v.lower())
                    for stmt in sql.split(";"):
                        alter = _RE_ALTER_TABLE.search(stmt)
                        if not alter:
                            continue
                        t = alter.group(1).lower()
                        for c in _RE_ADD_COLUMN.findall(stmt):
                            tabelas.setdefault(t, set()).add(c.lower())
                        for c in _RE_DROP_COLUMN.findall(stmt):
                            tabelas.get(t, set()).discard(c.lower())
    return (
        {t: frozenset(cols) for t, cols in tabelas.items()},
        frozenset(views),
    )


# ── Conjunto B: o que o código espera ────────────────────────────────────────


@functools.lru_cache(maxsize=1)
def _metadata_dos_models() -> dict[str, frozenset[str]]:
    """Importa o APP COMPLETO (não só app.models): routers montados em main.py
    definem models inline (ex.: DataRoomSala/dataroom_salas em data_room_v4,
    TeseJuridica/teses_juridicas_v4 em teses_v4) — mesmo racional do
    test_schema_sync._metadata()."""
    from app.core.database import Base
    import app.main  # noqa: F401 — registra TODOS os models no metadata

    return {
        t.name: frozenset(c.name.lower() for c in t.columns)
        for t in Base.metadata.tables.values()
    }


@functools.lru_cache(maxsize=1)
def _sql_strings_do_app() -> tuple[tuple[str, str], ...]:
    """Todas as constantes-string dos .py de backend/app (via AST)."""
    resultado: list[tuple[str, str]] = []
    for py in sorted(APP_DIR.rglob("*.py")):
        try:
            tree = ast.parse(py.read_text())
        except SyntaxError:  # pragma: no cover — app não compila = outro problema
            continue
        rel = str(py.relative_to(BACKEND_DIR))
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                resultado.append((rel, n.value))
    return tuple(resultado)


@functools.lru_cache(maxsize=1)
def _auto_bootstrap() -> dict[str, frozenset[str]]:
    """Tabelas que o próprio app cria em runtime (CREATE TABLE IF NOT EXISTS
    em services/seeds) -> colunas do DDL. Fora do escopo de migrations."""
    tabelas: dict[str, set[str]] = {}
    fontes = list(_sql_strings_do_app())
    for base in (BACKEND_DIR / "seeds", BACKEND_DIR / "app" / "seeds"):
        if not base.exists():
            continue
        for py in sorted(base.rglob("*.py")):
            try:
                fontes.append((str(py.relative_to(BACKEND_DIR)), py.read_text()))
            except (OSError, UnicodeDecodeError):  # pragma: no cover
                continue
    for _arquivo, s in fontes:
        for t in _RE_CREATE_TABLE_GUARDADO.findall(s):
            t = t.lower()
            tabelas.setdefault(t, set()).update(_colunas_do_ddl(s, t))
    # Evolução runtime dessas tabelas: ALTER TABLE ... ADD COLUMN IF NOT EXISTS
    # no próprio service (ex.: backup_drive_state.offsite_ok).
    for _arquivo, s in fontes:
        for stmt in s.split(";"):
            alter = _RE_ALTER_TABLE.search(stmt)
            if not alter:
                continue
            t = alter.group(1).lower()
            if t in tabelas:
                for c in _RE_ADD_COLUMN.findall(stmt):
                    tabelas[t].add(c.lower())
    return {t: frozenset(cols) for t, cols in tabelas.items()}


def _referencia_valida(texto: str, inicio: int, nome: str) -> bool:
    """Filtra falsos positivos estruturais do scanner de referências."""
    if len(nome) < 3 or nome.startswith("pg_") or nome in _RUIDO_SQL:
        return False
    contexto = texto[max(0, inicio - 40): inicio]
    # EXTRACT(EPOCH FROM col), EXTRACT(YEAR FROM col), ... — FROM de função
    # (o contexto antes do NOME capturado termina em "... FROM ")
    if re.search(r"EXTRACT\s*\(\s*\w+\s+FROM\s*$", contexto, re.I):
        return False
    # IS [NOT] DISTINCT FROM x
    if re.search(r"DISTINCT\s+FROM\s*$", contexto, re.I):
        return False
    # SUBSTRING(x FROM n), TRIM(... FROM x), OVERLAY(... FROM n)
    if re.search(r"(SUBSTRING|TRIM|OVERLAY)\s*\([^()]*$", contexto, re.I):
        return False
    return True


@functools.lru_cache(maxsize=1)
def _tabelas_referenciadas_no_app() -> dict[str, frozenset[str]]:
    """Tabelas referenciadas por SQL cru no código (FROM/JOIN/INSERT INTO/
    UPDATE...SET/DELETE FROM) -> arquivos onde aparecem."""
    refs: dict[str, set[str]] = {}
    for arquivo, s in _sql_strings_do_app():
        up = s.upper()
        if not any(k in up for k in ("SELECT", "INSERT", "UPDATE", "DELETE")):
            continue
        for regex in (_RE_REF_FROM, _RE_REF_INSERT, _RE_REF_UPDATE, _RE_REF_DELETE):
            for m in regex.finditer(s):
                nome = m.group(1).lower()
                if _referencia_valida(s, m.start(1), nome):
                    refs.setdefault(nome, set()).add(arquivo)
    return {t: frozenset(a) for t, a in refs.items()}


@functools.lru_cache(maxsize=1)
def _colunas_de_insert_no_app() -> dict[str, frozenset[str]]:
    """Colunas nomeadas em `INSERT INTO tabela (col, ...)` no código do app.
    Única extração de colunas raw-SQL 100% determinística sem parser SQL."""
    colunas: dict[str, set[str]] = {}
    for _arquivo, s in _sql_strings_do_app():
        for m in _RE_INSERT_COLUNAS.finditer(s):
            tabela = m.group(1).lower()
            for c in m.group(2).split(","):
                c = c.strip().strip('"').lower()
                if re.fullmatch(r"[a-z_][a-z0-9_]*", c):
                    colunas.setdefault(tabela, set()).add(c)
    return {t: frozenset(c) for t, c in colunas.items()}


# ── 1. Testes SEM banco (rodam sempre) ───────────────────────────────────────


def test_grafo_alembic_head_unico_e_canonico():
    """DR exige grafo íntegro: head ÚNICO e igual ao canônico."""
    assert _script_directory().get_heads() == [HEAD_REVISION]


def test_ponte_044_religa_039():
    """A ponte histórica das migrations perdidas segue intacta: 039 -> 044."""
    rev = _script_directory().get_revision("044")
    assert rev.down_revision == "039_jurimetria"


def test_053_reconcile_e_idempotente_por_construcao():
    """A migration de reconciliação usa apenas DDL idempotente — todo CREATE
    TABLE dela carrega IF NOT EXISTS (seguro em prod E em banco limpo)."""
    fonte = (VERSIONS_DIR / "053_reconcile_schema.py").read_text()
    creates = re.findall(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS)?", fonte, re.I)
    assert creates, "053 deveria conter CREATE TABLE"
    sem_guarda = [
        c for c in re.findall(r"CREATE\s+TABLE\s+(\S+)", fonte, re.I)
        if c.upper() != "IF"
    ]
    assert sem_guarda == [], f"CREATE TABLE sem IF NOT EXISTS na 053: {sem_guarda}"


def test_gap_dr_tabelas_dos_models_e_vazio():
    """Toda tabela de Base.metadata (app completo) é criada pela cadeia.

    Este era o risco das migrations perdidas 040-043: model existir sem create
    correspondente => banco limpo (DR) quebra com UndefinedTable. GAP deve ser
    vazio; se este teste quebrar, a tabela nova precisa de migration.
    """
    conjunto_a, _ = _conjunto_a()
    faltantes = sorted(t for t in _metadata_dos_models() if t not in conjunto_a)
    assert faltantes == [], (
        f"Tabelas de models SEM create em migration (GAP DR): {faltantes}"
    )


def test_gap_dr_colunas_dos_models_e_vazio():
    """Toda coluna dos models é criada pela cadeia (create_table + add_column
    + ALTER TABLE ADD COLUMN em SQL bruto, menos drops/renames — com CREATE
    TABLE IF NOT EXISTS repetido tratado como no-op, semântica Postgres)."""
    conjunto_a, _ = _conjunto_a()
    gap: dict[str, list[str]] = {}
    for tabela, colunas in _metadata_dos_models().items():
        if tabela not in conjunto_a:
            continue
        faltantes = sorted(colunas - conjunto_a[tabela])
        if faltantes:
            gap[tabela] = faltantes
    assert gap == {}, f"Colunas de models SEM migration (GAP DR): {gap}"


def test_gap_dr_tabelas_raw_sql_e_vazio():
    """O inventário mínimo de tabelas raw-SQL nasce da cadeia de migrations."""
    conjunto_a, _ = _conjunto_a()
    faltantes = sorted(RAW_SQL_TABLES_ESPERADAS - set(conjunto_a))
    assert faltantes == [], f"Tabelas raw-SQL SEM create em migration: {faltantes}"


def test_toda_tabela_raw_referenciada_esta_classificada():
    """Descoberta dinâmica: TODA tabela referenciada por SQL cru em backend/app
    precisa estar classificada — criada pela cadeia de migrations, mapeada em
    Base.metadata, auto-bootstrap (o service a cria em runtime) ou falso
    positivo documentado. Uma consulta nova a tabela sem migration quebra aqui.
    """
    conjunto_a, _ = _conjunto_a()
    conhecidas = (
        set(conjunto_a)
        | set(_metadata_dos_models())
        | set(_auto_bootstrap())
        | set(FALSOS_POSITIVOS_SQL)
        | VIEWS_ESPERADAS
    )
    refs = _tabelas_referenciadas_no_app()
    orfas = {t: sorted(refs[t])[:3] for t in sorted(set(refs) - conhecidas)}
    assert orfas == {}, (
        "Tabelas referenciadas por SQL cru sem migration/model/auto-bootstrap "
        f"(classifique ou crie migration): {orfas}"
    )


def test_colunas_de_insert_raw_sql_cobertas_pela_cadeia():
    """Paridade de COLUNA (parcial) para tabelas raw-SQL: toda coluna nomeada
    em `INSERT INTO tabela (...)` no app precisa existir na definição criada
    pela cadeia de migrations (ou no DDL runtime, para auto-bootstrap).
    Cobre o caminho de escrita; a limitação (SELECT/WHERE) está documentada."""
    conjunto_a, _ = _conjunto_a()
    metadata = _metadata_dos_models()
    auto = _auto_bootstrap()
    gap: dict[str, list[str]] = {}
    for tabela, colunas in _colunas_de_insert_no_app().items():
        if tabela in metadata:
            continue  # já coberto pela paridade de colunas dos models
        if tabela in auto:
            faltantes = sorted(colunas - auto[tabela])
        elif tabela in conjunto_a:
            faltantes = sorted(colunas - conjunto_a[tabela])
        else:
            continue  # órfã — já acusada no teste de classificação
        if faltantes:
            gap[tabela] = faltantes
    assert gap == {}, (
        f"Colunas de INSERT raw-SQL ausentes da definição criada (GAP DR): {gap}"
    )


def test_views_consultadas_sao_criadas_pela_cadeia():
    _, views = _conjunto_a()
    faltantes = sorted(VIEWS_ESPERADAS - views)
    assert faltantes == [], f"Views SEM create em migration: {faltantes}"


# ── 2. Teste COM banco (RUN_DB_TESTS=1) ──────────────────────────────────────


@pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com pgvector (defina RUN_DB_TESTS=1)",
)
def test_upgrade_head_reconstroi_schema_completo_em_banco_vazio():
    """Prova viva de DR: provisiona um banco NOVO (CREATE DATABASE — vazio por
    construção, independente do estado do banco do CI), roda `alembic upgrade
    head` nele (a própria cadeia cria as extensões vector/pg_trgm — 001/009) e
    afirma que TODAS as tabelas esperadas (models + raw-SQL, menos
    auto-bootstrap) existem de fato. O banco temporário é dropado ao final."""
    from alembic import command
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.engine import make_url

    url_ci = os.environ.get(
        "DATABASE_URL_SYNC",
        "postgresql://ejc_user:ejc_pass@localhost:5432/ejc_db",
    )
    nome_db = "ejc_dr_parity_check"
    admin = create_engine(make_url(url_ci), isolation_level="AUTOCOMMIT")
    try:
        try:
            with admin.connect() as conn:
                conn.execute(text(f"DROP DATABASE IF EXISTS {nome_db} WITH (FORCE)"))
                conn.execute(text(f"CREATE DATABASE {nome_db}"))
        except Exception as exc:  # sem privilégio CREATEDB — ambiente restrito
            pytest.skip(f"sem permissão para CREATE DATABASE ({exc!r})")

        url_dr = make_url(url_ci).set(database=nome_db)
        url_dr_str = url_dr.render_as_string(hide_password=False)
        url_original = os.environ.get("DATABASE_URL_SYNC")
        os.environ["DATABASE_URL_SYNC"] = url_dr_str  # lido pelo alembic/env.py
        try:
            config = Config(str(BACKEND_DIR / "alembic.ini"))
            config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
            command.upgrade(config, "head")
        finally:
            if url_original is None:  # pragma: no cover
                os.environ.pop("DATABASE_URL_SYNC", None)
            else:
                os.environ["DATABASE_URL_SYNC"] = url_original

        engine = create_engine(url_dr_str)
        try:
            inspector = inspect(engine)
            no_banco = set(inspector.get_table_names()) | set(
                inspector.get_view_names()
            )
        finally:
            engine.dispose()

        esperadas = (
            set(_metadata_dos_models()) | RAW_SQL_TABLES_ESPERADAS | VIEWS_ESPERADAS
        ) - set(_auto_bootstrap())
        faltantes = sorted(esperadas - no_banco)
        assert faltantes == [], (
            "Upgrade head em banco VAZIO não recriou tabelas/views esperadas "
            f"(GAP DR real): {faltantes}"
        )
    finally:
        try:
            with admin.connect() as conn:
                conn.execute(text(f"DROP DATABASE IF EXISTS {nome_db} WITH (FORCE)"))
        finally:
            admin.dispose()
