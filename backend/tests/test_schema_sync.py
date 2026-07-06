"""Guarda de sincronização de schema (Bloco 3b — Etapa 6).

Objetivo: impedir que o drift model↔banco (achados C3/C4/M9 da auditoria)
volte a acontecer silenciosamente. Historicamente o EJC teve tabelas/colunas
criadas fora do Alembic e models faltando (a tabela `processes` ficou sem model
ORM até a Etapa 6). Este arquivo tem duas camadas:

1. Camada estática (SEMPRE roda, sem banco): trava as regressões concretas já
   corrigidas — `processes` registrada em Base.metadata, tabelas de negócio
   presentes, e a FK de clients.responsavel_id declarada. Além disso, faz um
   cross-check leve entre as tabelas criadas nas migrations e os models.

2. Camada de banco vivo (só roda se SCHEMA_CHECK_DATABASE_URL apontar para um
   Postgres acessível): compara Base.metadata com o schema real via inspector,
   reportando divergências nos dois sentidos. Sem banco, faz pytest.skip — não
   falha em CI sem Postgres.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest


# ── Camada 1 — estática, sempre roda ──────────────────────────────────────────

# Tabelas de negócio que DEVEM ter model ORM registrado em Base.metadata.
_TABELAS_NUCLEO = {
    "users", "clients", "cases", "processes", "documents", "deadlines",
    "fees", "knowledge_docs", "knowledge_chunks", "ai_logs", "audit_logs",
    "legal_docs", "notifications",
}


def _metadata():
    # Importa o APP COMPLETO (não só app.models): alguns routers montados em
    # main.py definem models inline (ex.: data_room_v4, teses_v4). Sem carregar
    # o app, esses models entrariam em Base.metadata só por poluição de ordem de
    # testes (quem importar app.main primeiro), tornando a checagem de drift
    # dependente da ordem. Carregar o app aqui torna a verificação determinística
    # e fiel ao schema real que a aplicação monta.
    import app.main  # noqa: F401 — popula Base.metadata com TODOS os models
    from app.core.database import Base
    return Base.metadata


def test_processes_tem_model_registrado():
    """Regressão direta do achado C3: `processes` existia só como tabela SQL cru.
    A partir da Etapa 6 tem model ORM — não pode sumir de Base.metadata de novo."""
    md = _metadata()
    assert "processes" in md.tables, (
        "Tabela `processes` não está em Base.metadata — o model ORM "
        "(app/models/process.py) deixou de ser importado em app/models/__init__.py?"
    )


def test_tabelas_nucleo_presentes():
    md = _metadata()
    faltando = _TABELAS_NUCLEO - set(md.tables)
    assert not faltando, f"Tabelas de negócio sem model em Base.metadata: {sorted(faltando)}"


def test_client_responsavel_id_tem_fk():
    """Regressão do achado M9: a FK existe no banco (migration 001) mas o model
    não a declarava. Garante que a declaração ORM permaneça."""
    import app.models as m
    col = m.Client.__table__.columns["responsavel_id"]
    alvos = {fk.target_fullname for fk in col.foreign_keys}
    assert "users.id" in alvos, "clients.responsavel_id perdeu a FK para users.id no model"


def _tabelas_criadas_nas_migrations() -> set[str]:
    """Extrai nomes de tabela criados nas migrations, cobrindo os dois padrões
    usados no projeto: op.create_table("x", ...) e op.execute("CREATE TABLE x")."""
    versions = Path(__file__).resolve().parent.parent / "alembic" / "versions"
    nomes: set[str] = set()
    pat_create_table = re.compile(r"""op\.create_table\(\s*["']([a-z_0-9]+)["']""")
    pat_raw_sql = re.compile(
        r"""CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["']?([a-z_0-9]+)""", re.I
    )
    # Palavras-chave SQL que o backtracking da regex pode capturar em comentários
    # como "CREATE TABLE IF NOT EXISTS — seguro" (sem nome de tabela real).
    keywords = {"if", "not", "exists", "table"}
    for f in versions.glob("*.py"):
        txt = f.read_text(encoding="utf-8", errors="ignore")
        nomes.update(pat_create_table.findall(txt))
        nomes.update(n.lower() for n in pat_raw_sql.findall(txt))
    return nomes - keywords


# Inventário de tabelas criadas por migration que HOJE não têm model ORM
# (acesso 100% SQL cru). Levantado na Etapa 6 — são 30 tabelas, bem mais do que
# a auditoria por amostragem da Etapa 3 sugeria (`processes` era só a mais crítica
# e já ganhou model). NÃO é um endosso: é dívida técnica conhecida, registrada
# aqui para que o teste abaixo passe a acusar apenas tabelas NOVAS que ninguém
# modelou nem decidiu deixar sem model. Modelar estas 30 é trabalho futuro
# (candidato a bloco próprio), a ser priorizado pelas mais usadas.
_SEM_MODEL_INTENCIONAL = {
    "agenda_eventos", "areas", "case_ambiental", "case_etiquetas",
    "client_pending_items", "document_access_log", "domain_events",
    "due_diligence_templates", "etiquetas", "inadimplencia_alerts",
    "indice_risco_historico", "jur_assuntos", "jur_classes", "jur_decisoes",
    "jur_ingestao_logs", "jur_modelos", "jur_movimentos", "jur_partes",
    "jur_processos", "jur_tribunais", "kanban_columns", "memoria_institucional",
    "modelos_documentos", "office_contracts", "office_expenses",
    "partner_withdrawals", "portal_mensagens", "pricing_rules",
    "score_juridico", "teses_vitoriosas",
    # Bookkeeping do próprio Alembic (criada por `alembic upgrade`, nunca por
    # uma migration nossa) — não é dívida técnica, é infraestrutura da
    # ferramenta. Só apareceu agora porque esta é a 1ª vez que a Camada 2
    # (comparação com banco real) roda de fato, contra Postgres no CI.
    "alembic_version",
}


def test_autogenerate_tem_guarda_include_name():
    """Trava a proteção do env.py (Etapa 6): sem a guarda `include_name`, um
    `alembic revision --autogenerate` geraria drop_table para as ~30 tabelas de
    acesso SQL cru (sem model). env.py não é importável fora do Alembic (roda
    migrations no import), então validamos por inspeção do fonte."""
    env = (Path(__file__).resolve().parent.parent / "alembic" / "env.py").read_text(
        encoding="utf-8"
    )
    assert "def include_name(" in env, "env.py perdeu a função include_name"
    # Precisa estar realmente conectada nos dois context.configure (online/offline).
    assert env.count("include_name=include_name") >= 2, (
        "include_name não está ligada nos dois context.configure — autogenerate "
        "voltaria a poder gerar drop_table destrutivo para tabelas sem model."
    )


def test_toda_tabela_de_migration_tem_model_ou_allowlist():
    """Cross-check estático (sem banco): toda tabela criada em migration deve ter
    model em Base.metadata OU estar na allowlist consciente. Isto teria pego o
    drift de `processes`. NÃO falha para o que já é conhecido/intencional — só
    para tabelas NOVAS que ninguém registrou nem decidiu deixar sem model."""
    md = _metadata()
    criadas = _tabelas_criadas_nas_migrations()
    modeladas = set(md.tables)
    orfas = criadas - modeladas - _SEM_MODEL_INTENCIONAL
    assert not orfas, (
        "Tabelas criadas em migration sem model ORM e fora da allowlist: "
        f"{sorted(orfas)}. Crie o model (recomendado) ou adicione a "
        "_SEM_MODEL_INTENCIONAL com justificativa."
    )


# ── Camada 2 — banco vivo, só com SCHEMA_CHECK_DATABASE_URL ────────────────────

def test_metadata_bate_com_banco_real():
    """Compara Base.metadata com o schema real. Requer um Postgres acessível via
    SCHEMA_CHECK_DATABASE_URL (ex.: cópia de dev/CI). Sem isso, pula — não deve
    rodar contra produção sem intenção explícita."""
    url = os.getenv("SCHEMA_CHECK_DATABASE_URL")
    if not url:
        pytest.skip("SCHEMA_CHECK_DATABASE_URL não definida — checagem contra banco vivo pulada")

    try:
        from sqlalchemy import create_engine, inspect
        engine = create_engine(url)
        insp = inspect(engine)
        tabelas_banco = set(insp.get_table_names())
    except Exception as e:  # driver ausente, conexão recusada, etc.
        pytest.skip(f"Banco inacessível para checagem de schema: {e}")

    md = _metadata()
    tabelas_model = set(md.tables)

    # Tabelas no model mas ausentes no banco = migration faltando (risco de quebra).
    no_model_sem_banco = tabelas_model - tabelas_banco
    # Tabelas no banco sem model e sem allowlist = drift na direção oposta.
    no_banco_sem_model = tabelas_banco - tabelas_model - _SEM_MODEL_INTENCIONAL

    problemas = []
    if no_model_sem_banco:
        problemas.append(f"em Base.metadata mas ausentes no banco: {sorted(no_model_sem_banco)}")
    if no_banco_sem_model:
        problemas.append(f"no banco mas sem model nem allowlist: {sorted(no_banco_sem_model)}")
    assert not problemas, "Drift model↔banco detectado — " + "; ".join(problemas)


# ── Camada 3 — drift de COLUNA (não só de tabela) ─────────────────────────────
# #20: a Camada 2 comparava só nomes de TABELA, então uma regressão de coluna
# (ex.: model declara `full_name` mas a migration nunca criou; ou uma coluna do
# model perdeu a migration correspondente) passava despercebida — "verde
# enganoso". Aqui, para cada tabela modelada, TODA coluna do MODEL precisa
# existir no banco (direção model→banco). Não sinaliza colunas SÓ no banco (há
# colunas intencionais acessadas via SQL cru, ex.: documents.sensitivity_level),
# evitando falso-positivo.
def test_colunas_do_model_existem_no_banco():
    url = os.getenv("SCHEMA_CHECK_DATABASE_URL")
    if not url:
        pytest.skip("SCHEMA_CHECK_DATABASE_URL não definida — checagem de coluna pulada")

    try:
        from sqlalchemy import create_engine, inspect
        engine = create_engine(url)
        insp = inspect(engine)
        tabelas_banco = set(insp.get_table_names())
    except Exception as e:
        pytest.skip(f"Banco inacessível para checagem de coluna: {e}")

    md = _metadata()
    faltando: list[str] = []
    for nome_tab, tabela in md.tables.items():
        if nome_tab not in tabelas_banco:
            continue  # ausência de tabela já é coberta pela Camada 2
        cols_banco = {c["name"] for c in insp.get_columns(nome_tab)}
        for col in tabela.columns:
            if col.name not in cols_banco:
                faltando.append(f"{nome_tab}.{col.name}")
    assert not faltando, (
        "Colunas declaradas no model mas AUSENTES no banco (migration faltando?): "
        f"{sorted(faltando)}"
    )
