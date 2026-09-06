"""140_preliminares_fundacao_schema — Fase 1 da fusão Sala Jurídica + Raio-X.

Cobertura estática sempre roda. Com RUN_DB_TESTS=1, sobe banco descartável em
138, aplica somente 139, valida as quatro tabelas novas e prova downgrade para
138 sem tocar as seis tabelas legadas.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    BACKEND_DIR / "alembic" / "versions" / "140_preliminares_fundacao_schema.py"
)

PRELIMINAR_TABELAS = {
    "preliminares": {
        "id", "origem", "titulo", "status", "potencial_cliente", "area",
        "convertido_case_id", "converted_at", "created_by", "deleted_at",
        "created_at", "updated_at", "numero_processo", "subarea", "rito",
        "fase", "tribunal", "orgao", "unidade", "posicao_cliente",
        "risco_nivel", "prazo_urgente", "origem_contextual_case_id",
        "dados_extraidos", "relatorio", "revisao_humana", "alertas_conflito",
        "custo_ia", "retention_until", "archived_at", "discarded_at",
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

LEGADAS = {
    "raio_x_analises",
    "raio_x_documentos",
    "legal_chat_sessions",
    "legal_chat_messages",
    "legal_chat_attachments",
    "legal_chat_state_versions",
}


def _script_directory() -> ScriptDirectory:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(config)


def test_migration_139_encadeia_em_138_e_e_o_head():
    # Consolidado em 2026-08-12: bifurcação 138 → {139, 140} linearizada em
    # 138 → 139 → 140 (frete independente: 139 altera document_intake_batches,
    # 140 cria/dropa apenas tabelas preliminares).
    script = _script_directory()
    # Issue #1272 (24/08/2026): 148/149 do plano-mestre renumeradas para
    # 151/152 ao mesclar a main (149/150 ocupadas pelo #1238). A migration
    # 153 isola cliente-documento, 154 cria saneamento, 155 adiciona índices
    # de listagem e 156 adiciona despesas processuais por caso.
    assert script.get_heads() == ["157_ajuizamento_judicial"]
    revisao = script.get_revision("140_preliminares_fundacao_schema")
    assert revisao.down_revision == "139_dpt360_ciclo_vida_lgpd"
    assert (
        script.get_revision("141_dpt360_diagnostico").down_revision
        == "140_preliminares_fundacao_schema"
    )
    assert (
        script.get_revision("142_document_hash_rescan").down_revision
        == "141_dpt360_diagnostico"
    )
    # Consolidado na homologação M02/M11 (16/08/2026): o widening
    # varchar(32)->128 (antiga migration ``144a``) foi fundido no upgrade da
    # 143 — o guard ``test_migration_numbering_guard.py`` rejeita prefixo
    # não numérico.
    assert (
        script.get_revision("143_signature_documento_visualizado").down_revision
        == "142_document_hash_rescan"
    )
    assert (
        script.get_revision("144_alembic_version_varchar128").down_revision
        == "143_signature_documento_visualizado"
    )
    assert (
        script.get_revision("145_drop_orphan_db_only_columns").down_revision
        == "144_alembic_version_varchar128"
    )
    assert (
        script.get_revision("146_case_sigilo_reforcado").down_revision
        == "145_drop_orphan_db_only_columns"
    )
    assert (
        script.get_revision("147_pendencia_impacto_providencia").down_revision
        == "146_case_sigilo_reforcado"
    )
    assert (
        script.get_revision("139_dpt360_ciclo_vida_lgpd").down_revision
        == "138_consolida_fontes_ingestao"
    )


def test_migration_139_e_estritamente_aditiva_sobre_o_legado():
    fonte = MIGRATION_PATH.read_text(encoding="utf-8")
    upgrade = fonte.split("def upgrade()", 1)[1].split("def downgrade()", 1)[0]
    downgrade = fonte.split("def downgrade()", 1)[1]

    for tabela in PRELIMINAR_TABELAS:
        assert f'"{tabela}"' in upgrade, f"migration não cria {tabela}"
        assert f'"{tabela}"' in downgrade, f"downgrade não remove {tabela}"

    for tabela in LEGADAS:
        assert tabela not in upgrade, f"upgrade toca tabela legada {tabela}"
        assert tabela not in downgrade, f"downgrade toca tabela legada {tabela}"


def test_models_preliminar_estao_registrados_no_metadata():
    from app.core.database import Base
    import app.models  # noqa: F401

    for tabela, colunas_esperadas in PRELIMINAR_TABELAS.items():
        assert tabela in Base.metadata.tables, f"{tabela} ausente do metadata ORM"
        colunas_reais = set(Base.metadata.tables[tabela].columns.keys())
        assert colunas_esperadas <= colunas_reais, (
            f"{tabela}: faltando {colunas_esperadas - colunas_reais}"
        )


# O guard precisa cobrir as DUAS variáveis que o teste consome. Só
# `RUN_DB_TESTS` deixava `os.environ["SCHEMA_CHECK_DATABASE_URL"]` estourar
# KeyError: o teste FALHAVA por configuração ausente em vez de pular, e um
# erro de ambiente ficava indistinguível de uma quebra real de schema no log.
# No CI (ci.yml define ambas) o teste segue rodando exatamente como antes.
@pytest.mark.skipif(
    not (os.getenv("RUN_DB_TESTS") and os.getenv("SCHEMA_CHECK_DATABASE_URL")),
    reason="requer PostgreSQL (RUN_DB_TESTS=1 e SCHEMA_CHECK_DATABASE_URL)",
)
def test_upgrade_139_e_downgrade_138_preservam_tabelas_legadas():
    import subprocess

    import psycopg2
    from sqlalchemy import create_engine, inspect

    url = os.environ["SCHEMA_CHECK_DATABASE_URL"]
    parsed = urlsplit(url)
    nome_db = f"ejc_preliminares_139_{os.getpid()}"
    sync_url = urlunsplit(
        ("postgresql+psycopg2", parsed.netloc, f"/{nome_db}", "", "")
    )

    def admin():
        conn = psycopg2.connect(
            dbname="postgres",
            user=unquote(parsed.username or ""),
            password=unquote(parsed.password or ""),
            host=parsed.hostname,
            port=parsed.port,
        )
        conn.autocommit = True
        return conn

    conn = admin()
    try:
        with conn.cursor() as cursor:
            cursor.execute(f'CREATE DATABASE "{nome_db}"')
    finally:
        conn.close()

    def rodar_alembic(*args: str) -> None:
        env = {
            **os.environ,
            "DATABASE_URL_SYNC": sync_url,
            "SCHEMA_CHECK_DATABASE_URL": sync_url,
        }
        resultado = subprocess.run(
            [__import__('sys').executable, "-m", "alembic", *args],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
        )
        assert resultado.returncode == 0, resultado.stderr or resultado.stdout

    try:
        rodar_alembic("upgrade", "138_consolida_fontes_ingestao")
        engine = create_engine(sync_url)
        try:
            antes = set(inspect(engine).get_table_names())
            assert not set(PRELIMINAR_TABELAS) & antes
            assert LEGADAS <= antes
        finally:
            engine.dispose()

        # Cadeia linearizada: aplica primeiro 139 (ciclo de vida LGPD) e depois
        # 140 (fundação preliminares), validando a ordem real da migração.
        rodar_alembic("upgrade", "139_dpt360_ciclo_vida_lgpd")
        rodar_alembic("upgrade", "140_preliminares_fundacao_schema")
        engine = create_engine(sync_url)
        try:
            inspector = inspect(engine)
            tabelas = set(inspector.get_table_names())
            assert set(PRELIMINAR_TABELAS) <= tabelas
            assert LEGADAS <= tabelas
            for tabela, colunas_esperadas in PRELIMINAR_TABELAS.items():
                colunas_reais = {c["name"] for c in inspector.get_columns(tabela)}
                assert colunas_esperadas <= colunas_reais
        finally:
            engine.dispose()

        rodar_alembic("downgrade", "138_consolida_fontes_ingestao")
        engine = create_engine(sync_url)
        try:
            depois = set(inspect(engine).get_table_names())
            assert not set(PRELIMINAR_TABELAS) & depois
            assert LEGADAS <= depois
        finally:
            engine.dispose()
    finally:
        conn = admin()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (nome_db,),
                )
                cursor.execute(f'DROP DATABASE IF EXISTS "{nome_db}"')
        finally:
            conn.close()
