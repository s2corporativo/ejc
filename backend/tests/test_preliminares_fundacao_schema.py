"""142_preliminares_fundacao_schema — F5 Fase 1: fundação de schema.

Cobertura estática (sempre roda, sem Postgres): a migration está encadeada
no head correto, é a única head e o downgrade existe.

Cobertura de banco vivo (RUN_DB_TESTS=1, requer Postgres — mesmo padrão de
`test_schema_dr_parity.test_upgrade_head_reconstroi_banco_vazio_real`):
sobe uma base vazia até `138_consolida_fontes_ingestao` (head anterior),
aplica só a migration 142 e confirma que as 4 tabelas novas existem com as
colunas esperadas; em seguida roda o `downgrade` de volta a 138 e confirma
que as 4 tabelas somem sem erro e sem afetar as tabelas antigas
(`raio_x_analises`/`legal_chat_sessions`), que continuam sendo a fonte de
dados em produção nesta fase.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).resolve().parents[1]
MIGRATION_PATH = BACKEND_DIR / "alembic" / "versions" / "142_preliminares_fundacao_schema.py"

PRELIMINAR_TABELAS = {
    "preliminares": {
        "id", "origem", "titulo", "status", "potencial_cliente", "area",
        "convertido_case_id", "converted_at", "created_by", "deleted_at",
        "created_at", "updated_at",
        "numero_processo", "subarea", "rito", "fase", "tribunal", "orgao",
        "unidade", "posicao_cliente", "risco_nivel", "prazo_urgente",
        "origem_contextual_case_id", "dados_extraidos", "relatorio",
        "revisao_humana", "alertas_conflito", "custo_ia", "retention_until",
        "archived_at", "discarded_at",
        "favorita", "client_id", "advogado_responsavel_id", "workspace_texto",
        "workspace_versao", "frozen_at", "custo_ia_total",
    },
    "preliminar_documentos": {
        "id", "preliminar_id", "nome_original", "filepath", "mimetype",
        "size_bytes", "sha256", "tipo_documento", "paginas", "ocr_utilizado",
        "resultado_analise", "uploaded_by", "created_at",
    },
    "preliminar_mensagens": {
        "id", "preliminar_id", "autor", "user_id", "modo", "conteudo",
        "modelo", "agente", "skills", "fontes", "citacoes", "alertas",
        "tokens_input", "tokens_output", "custo_estimado", "ai_log_id",
        "estado_versao", "created_at",
    },
    "preliminar_estados": {
        "id", "preliminar_id", "versao", "resumo", "estado", "autoria",
        "created_by", "created_at",
    },
}


def _script_directory() -> ScriptDirectory:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(config)


# ══════════════════════════════════════════════════════════════════════════
# Estática — sem Postgres
# ══════════════════════════════════════════════════════════════════════════

def test_migration_142_encadeia_apos_consolida_fontes_ingestao_e_e_o_head():
    script = _script_directory()
    assert script.get_heads() == ["142_preliminares_fundacao_schema"]
    revisao = script.get_revision("142_preliminares_fundacao_schema")
    assert revisao.down_revision == "138_consolida_fontes_ingestao"


def test_migration_142_e_aditiva_e_reversivel():
    fonte = MIGRATION_PATH.read_text(encoding="utf-8")
    # Corpo executável: da definição de `upgrade()` em diante — exclui o
    # docstring do módulo, que cita as tabelas antigas só como contexto.
    corpo = fonte.split("def upgrade()", 1)[1]
    for tabela in PRELIMINAR_TABELAS:
        assert f'"{tabela}"' in corpo, f"migration não cria {tabela}"
    # Estritamente aditiva: nenhum op.* nas tabelas antigas (ALTER/DROP/etc.).
    assert "raio_x_analises" not in corpo
    assert "raio_x_documentos" not in corpo
    assert "legal_chat_sessions" not in corpo
    assert "legal_chat_messages" not in corpo
    assert "legal_chat_attachments" not in corpo
    assert "legal_chat_state_versions" not in corpo
    # downgrade() dropa exatamente as 4 tabelas criadas, nada mais.
    corpo_downgrade = fonte.split("def downgrade()", 1)[1]
    for tabela in PRELIMINAR_TABELAS:
        assert f'"{tabela}"' in corpo_downgrade


def test_models_preliminar_estao_registrados_no_metadata():
    from app.core.database import Base
    import app.models  # noqa: F401 — registra todos os models

    for tabela, colunas_esperadas in PRELIMINAR_TABELAS.items():
        assert tabela in Base.metadata.tables, f"{tabela} ausente do metadata ORM"
        colunas_reais = set(Base.metadata.tables[tabela].columns.keys())
        assert colunas_esperadas <= colunas_reais, (
            f"{tabela}: colunas do ORM divergem do esperado — "
            f"faltando {colunas_esperadas - colunas_reais}"
        )


# ══════════════════════════════════════════════════════════════════════════
# Banco vivo — RUN_DB_TESTS=1
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not os.getenv("RUN_DB_TESTS"), reason="requer PostgreSQL")
def test_upgrade_cria_as_quatro_tabelas_e_downgrade_remove_tudo():
    import subprocess

    import psycopg2
    from sqlalchemy import create_engine, inspect

    url = os.environ["SCHEMA_CHECK_DATABASE_URL"]
    parsed = urlsplit(url)
    nome_db = f"ejc_preliminares_{os.getpid()}"
    sync_url = urlunsplit(("postgresql+psycopg2", parsed.netloc, f"/{nome_db}", "", ""))

    def _admin():
        conn = psycopg2.connect(
            dbname="postgres", user=unquote(parsed.username or ""),
            password=unquote(parsed.password or ""), host=parsed.hostname,
            port=parsed.port,
        )
        conn.autocommit = True
        return conn

    conn = _admin()
    try:
        cursor = conn.cursor()
        try:
            cursor.execute(f'CREATE DATABASE "{nome_db}"')
        finally:
            cursor.close()
    finally:
        conn.close()

    def _rodar_alembic(*args: str) -> None:
        env = {**os.environ, "DATABASE_URL_SYNC": sync_url, "SCHEMA_CHECK_DATABASE_URL": sync_url}
        resultado = subprocess.run(
            ["python", "-m", "alembic", *args],
            cwd=BACKEND_DIR, env=env, capture_output=True, text=True,
        )
        assert resultado.returncode == 0, resultado.stderr or resultado.stdout

    try:
        # Base num estado equivalente ao head real da `main` ANTES desta fase.
        _rodar_alembic("upgrade", "138_consolida_fontes_ingestao")

        engine = create_engine(sync_url)
        try:
            inspector = inspect(engine)
            antes = set(inspector.get_table_names())
            assert not (set(PRELIMINAR_TABELAS) & antes), (
                "tabelas preliminar_* já existiam antes da migration 142"
            )
            assert {"raio_x_analises", "legal_chat_sessions"} <= antes
        finally:
            engine.dispose()

        # Aplica só a migration desta fase.
        _rodar_alembic("upgrade", "142_preliminares_fundacao_schema")

        engine = create_engine(sync_url)
        try:
            inspector = inspect(engine)
            tabelas = set(inspector.get_table_names())
            assert set(PRELIMINAR_TABELAS) <= tabelas
            for tabela, colunas_esperadas in PRELIMINAR_TABELAS.items():
                colunas_reais = {c["name"] for c in inspector.get_columns(tabela)}
                assert colunas_esperadas <= colunas_reais, (
                    f"{tabela}: coluna(s) faltando no banco — "
                    f"{colunas_esperadas - colunas_reais}"
                )
            # Tabelas antigas intocadas — nenhuma migração/DROP nelas nesta fase.
            assert {
                "raio_x_analises", "raio_x_documentos", "legal_chat_sessions",
                "legal_chat_messages", "legal_chat_attachments",
                "legal_chat_state_versions",
            } <= tabelas
        finally:
            engine.dispose()

        # Downgrade reversível: some tudo, sem erro, sem afetar o resto.
        _rodar_alembic("downgrade", "138_consolida_fontes_ingestao")

        engine = create_engine(sync_url)
        try:
            inspector = inspect(engine)
            depois = set(inspector.get_table_names())
            assert not (set(PRELIMINAR_TABELAS) & depois), (
                "downgrade não removeu todas as tabelas preliminar_*"
            )
            assert {"raio_x_analises", "legal_chat_sessions"} <= depois
        finally:
            engine.dispose()
    finally:
        conn = _admin()
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
