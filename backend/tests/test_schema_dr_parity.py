"""Paridade de schema para Disaster Recovery (migrations 040-043 perdidas).

Contexto: as migrations 040-043 foram aplicadas direto no container e nunca
versionadas; `044_recover_head.py` é um stub `pass` que só religa o grafo
039 -> 044. A `053_reconcile_schema.py` (e migrations posteriores) compensa o
schema perdido. Este arquivo PROVA, de forma determinística, que a cadeia
completa de migrations reconstrói TODO o schema esperado em um banco limpo
(DR/staging) — ou seja, que o GAP das migrations perdidas é vazio.

Duas camadas (mesma prova da auditoria docs/audit/RECONCILIACAO_SCHEMA_DR_2026-07-26.md):

1. SEM banco (roda sempre): parse estático (AST) da função upgrade() de todas
   as migrations em ordem topológica -> conjunto A (tabelas/colunas criadas);
   compara com o conjunto B = Base.metadata dos models + tabelas raw-SQL
   consultadas pelo código. Se um model/tabela nova nascer sem migration, o
   teste quebra ANTES de chegar em produção.

2. COM banco (RUN_DB_TESTS=1, mesmo padrão dos *_dblevel.py): roda
   `alembic upgrade head` (no-op se já aplicado) e verifica via inspector que
   todas as tabelas esperadas existem de fato.

Tabelas AUTO-BOOTSTRAP (criam-se sozinhas em runtime via CREATE TABLE IF NOT
EXISTS nos services) ficam FORA do escopo — não precisam de migration.
"""
from __future__ import annotations

import ast
import os
import re
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).resolve().parents[1]
VERSIONS_DIR = BACKEND_DIR / "alembic" / "versions"

# Head canônico — atualizar no MESMO PR que adicionar migration nova
# (mesma regra de test_alembic_single_head.py).
HEAD_REVISION = "120_chunk_pagina"

# Tabelas que se auto-criam em runtime (CREATE TABLE IF NOT EXISTS no service).
# Fora do escopo de migrations — ver docstring do módulo.
AUTO_BOOTSTRAP = {
    "backup_drive_state",        # services/backup_service.py
    "google_drive_sync_state",   # services/google_drive_service.py
    "indices_bcb_cache",         # services/indices_service.py
    "indices_bcb_cache_meta",    # services/indices_service.py
    "infosimples_uso",           # services/infosimples_service.py
    "radar_legislativo_visto",   # services/radar_legislativo.py
    "transparencia_cache",       # services/transparencia_service.py
}

# Tabelas 100% raw-SQL (sem model ORM) que o código consulta e que a cadeia de
# migrations PRECISA criar (levantadas na auditoria de 2026-07-26; a maioria
# nasceu nas perdidas 040-043 e foi recriada pela 050/053).
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


# ── Parser estático da cadeia de migrations (conjunto A) ─────────────────────

_RE_CREATE_TABLE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?\"?([a-zA-Z_]\w*)\"?", re.I
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


def _conjunto_a() -> tuple[dict[str, set[str]], set[str]]:
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
                nome = args[0].value
                colunas = {
                    a.args[0].value
                    for a in args[1:]
                    if isinstance(a, ast.Call)
                    and getattr(a.func, "attr", None) == "Column"
                    and a.args
                    and isinstance(a.args[0], ast.Constant)
                }
                tabelas.setdefault(nome, set()).update(c.lower() for c in colunas)
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
                        tabelas.setdefault(t, set()).update(_colunas_do_ddl(sql, t))
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
    return tabelas, views


def _metadata_dos_models() -> dict[str, set[str]]:
    from app.core.database import Base
    import app.models  # noqa: F401 — registra todos os models no metadata

    return {
        t.name: {c.name.lower() for c in t.columns}
        for t in Base.metadata.tables.values()
    }


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
    """Toda tabela de Base.metadata é criada pela cadeia de migrations.

    Este era o risco das migrations perdidas 040-043: model existir sem create
    correspondente => banco limpo (DR) quebra com UndefinedTable. GAP deve ser
    vazio; se este teste quebrar, a tabela nova precisa de migration.
    """
    conjunto_a, _ = _conjunto_a()
    faltantes = sorted(
        t for t in _metadata_dos_models() if t not in conjunto_a and t not in AUTO_BOOTSTRAP
    )
    assert faltantes == [], (
        f"Tabelas de models SEM create em migration (GAP DR): {faltantes}"
    )


def test_gap_dr_colunas_dos_models_e_vazio():
    """Toda coluna dos models é criada pela cadeia (create_table + add_column
    + ALTER TABLE ADD COLUMN em SQL bruto, menos drops/renames)."""
    conjunto_a, _ = _conjunto_a()
    gap: dict[str, list[str]] = {}
    for tabela, colunas in _metadata_dos_models().items():
        if tabela in AUTO_BOOTSTRAP or tabela not in conjunto_a:
            continue
        faltantes = sorted(colunas - conjunto_a[tabela])
        if faltantes:
            gap[tabela] = faltantes
    assert gap == {}, f"Colunas de models SEM migration (GAP DR): {gap}"


def test_gap_dr_tabelas_raw_sql_e_vazio():
    """Tabelas 100% raw-SQL consultadas pelo código (sem model, fora do
    autogenerate) também precisam nascer da cadeia de migrations."""
    conjunto_a, _ = _conjunto_a()
    faltantes = sorted(RAW_SQL_TABLES_ESPERADAS - set(conjunto_a))
    assert faltantes == [], f"Tabelas raw-SQL SEM create em migration: {faltantes}"


def test_views_consultadas_sao_criadas_pela_cadeia():
    _, views = _conjunto_a()
    faltantes = sorted(VIEWS_ESPERADAS - views)
    assert faltantes == [], f"Views SEM create em migration: {faltantes}"


# ── 2. Teste COM banco (RUN_DB_TESTS=1) ──────────────────────────────────────


@pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com pgvector (defina RUN_DB_TESTS=1)",
)
def test_upgrade_head_reconstroi_schema_completo_em_banco_limpo():
    """Prova viva de DR: `alembic upgrade head` (no-op se já aplicado — no CI
    o banco de serviço nasce vazio) deixa TODAS as tabelas esperadas (models +
    raw-SQL, menos auto-bootstrap) existindo de fato no Postgres."""
    from alembic import command
    from sqlalchemy import create_engine, inspect

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")

    url = os.environ.get(
        "DATABASE_URL_SYNC",
        "postgresql://ejc_user:ejc_pass@localhost:5432/ejc_db",
    )
    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        no_banco = set(inspector.get_table_names()) | set(inspector.get_view_names())
    finally:
        engine.dispose()

    esperadas = (
        set(_metadata_dos_models()) | RAW_SQL_TABLES_ESPERADAS | VIEWS_ESPERADAS
    ) - AUTO_BOOTSTRAP
    faltantes = sorted(esperadas - no_banco)
    assert faltantes == [], (
        f"Após upgrade head, tabelas/views esperadas AUSENTES no banco: {faltantes}"
    )
