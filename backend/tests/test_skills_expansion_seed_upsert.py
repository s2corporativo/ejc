"""Prova, contra um banco real (sqlite em memória — mesma técnica de
test_vault_service.py/test_schema_sync.py para dispensar Postgres), que rodar
o seed de novo CORRIGE o prompt de instalações já feitas para as duas skills
da Issue #554 — não só ignora nomes já existentes como o comportamento antigo.

Problema reproduzido (Issue #554, problema 2): "O seed hoje só ignora nomes já
existentes ao rodar de novo — ou seja, corrigir só o texto do seed NÃO corrige
instalações já feitas." Este teste falha se essa regressão voltar.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from app.seeds.skills_expansion_seed import SKILLS, seed


def _engine_sqlite_com_tabela():
    # DDL manual (não `EjcSkill.__table__.create()`): o model declara
    # `vezes_executado` com `default=0` (client-side, só a ORM aplica), mas em
    # produção a coluna tem `server_default='0'` (migration 130) — é esse o
    # comportamento que o INSERT bruto de `seed()` (fora da ORM) depende.
    # Reproduz aqui o schema real, não o metadata incompleto do model.
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE ejc_skills (
                id VARCHAR(36) PRIMARY KEY,
                name VARCHAR(100) NOT NULL UNIQUE,
                display_name VARCHAR(200) NOT NULL,
                description TEXT,
                system_prompt TEXT NOT NULL,
                engine VARCHAR(20) NOT NULL DEFAULT 'groq',
                area VARCHAR(50) NOT NULL DEFAULT 'juridico',
                active BOOLEAN NOT NULL DEFAULT 1,
                requires_case BOOLEAN NOT NULL DEFAULT 0,
                requires_human_review BOOLEAN NOT NULL DEFAULT 1,
                oab_restricted BOOLEAN NOT NULL DEFAULT 0,
                version INTEGER NOT NULL DEFAULT 1,
                vezes_executado INTEGER NOT NULL DEFAULT 0,
                ultima_execucao DATETIME,
                created_at DATETIME,
                updated_at DATETIME
            )
        """))
    return engine


def _instalar_versao_antiga(engine, name: str, prompt_antigo: str):
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO ejc_skills (
                    id, name, display_name, description, system_prompt,
                    engine, area, active, requires_case,
                    requires_human_review, oab_restricted, version,
                    vezes_executado, created_at, updated_at
                ) VALUES (
                    :id, :name, 'Nome antigo', 'Descrição antiga', :prompt,
                    'groq', 'estrategia', 1, 0, 1, 1, 1,
                    0, '2026-01-01 00:00:00', '2026-01-01 00:00:00'
                )
            """),
            {"id": f"velho-{name}", "name": name, "prompt": prompt_antigo},
        )


def test_seed_atualiza_prompt_ja_instalado_das_duas_skills_da_issue(monkeypatch):
    engine = _engine_sqlite_com_tabela()
    _instalar_versao_antiga(
        engine, "prescricao-decadencia",
        "Prompt antigo sem a instrução de mérito (versão pré-Issue #554).",
    )
    _instalar_versao_antiga(
        engine, "simulador-defesa-adversarial",
        "Prompt antigo sem a instrução de mérito (versão pré-Issue #554).",
    )

    # `seed()` faz `from sqlalchemy import create_engine` DENTRO da função
    # (import local) — o patch precisa mirar o módulo `sqlalchemy`, não o
    # namespace de `skills_expansion_seed`, senão o import local resolve para
    # o `create_engine` real e tenta abrir a URL de verdade.
    monkeypatch.setattr("sqlalchemy.create_engine", lambda *_a, **_k: engine)
    monkeypatch.setenv("DATABASE_URL_SYNC", "sqlite:///:memory:")

    seed()

    with engine.connect() as conn:
        linhas = {
            row.name: row.system_prompt
            for row in conn.execute(
                text(
                    "SELECT name, system_prompt FROM ejc_skills "
                    "WHERE name IN ('prescricao-decadencia', 'simulador-defesa-adversarial')"
                )
            )
        }

    prompt_novo = {s["name"]: s["system_prompt"] for s in SKILLS}
    for nome in ("prescricao-decadencia", "simulador-defesa-adversarial"):
        assert linhas[nome] == prompt_novo[nome]
        assert "art. 487, II" in linhas[nome]
        # A ID original (linha já existente) foi mantida — é UPDATE, não
        # delete+insert (não perde referências de outras tabelas via FK).
    with engine.connect() as conn:
        ids = {
            row.name: row.id
            for row in conn.execute(
                text(
                    "SELECT name, id FROM ejc_skills "
                    "WHERE name IN ('prescricao-decadencia', 'simulador-defesa-adversarial')"
                )
            )
        }
    assert ids["prescricao-decadencia"] == "velho-prescricao-decadencia"
    assert ids["simulador-defesa-adversarial"] == "velho-simulador-defesa-adversarial"


def test_seed_nao_sobrescreve_skill_ja_instalada_fora_do_escopo_da_issue(monkeypatch):
    # Controle: uma skill qualquer JÁ instalada, fora da allowlist de
    # atualização forçada, continua sendo apenas IGNORADA (comportamento
    # antigo, preservado) — o upsert não vira global.
    engine = _engine_sqlite_com_tabela()
    _instalar_versao_antiga(
        engine, "negativacao-indevida", "Texto customizado manualmente por um sócio.",
    )
    monkeypatch.setattr("sqlalchemy.create_engine", lambda *_a, **_k: engine)
    monkeypatch.setenv("DATABASE_URL_SYNC", "sqlite:///:memory:")

    seed()

    with engine.connect() as conn:
        prompt = conn.execute(
            text("SELECT system_prompt FROM ejc_skills WHERE name = 'negativacao-indevida'")
        ).scalar_one()
    assert prompt == "Texto customizado manualmente por um sócio."


def test_seed_grava_backup_do_prompt_anterior_antes_de_sobrescrever(monkeypatch, tmp_path):
    """Review do CodeRabbit no PR #703. O upsert forçado é a ÚNICA operação
    deste seed que destrói conteúdo já gravado: `git revert` devolve o código,
    não o prompt antigo do banco. O próprio PR registrava isso como "rollback
    parcial" nos riscos residuais — agora o estado anterior é persistido antes
    do commit, e o rollback deixa de depender de memória de ninguém."""
    import json

    engine = _engine_sqlite_com_tabela()
    _instalar_versao_antiga(
        engine, "prescricao-decadencia", "PROMPT ANTIGO QUE PRECISA SOBREVIVER",
    )
    destino = tmp_path / "backups"
    monkeypatch.setattr("sqlalchemy.create_engine", lambda *_a, **_k: engine)
    monkeypatch.setenv("DATABASE_URL_SYNC", "sqlite:///:memory:")
    monkeypatch.setattr(
        "app.seeds.skills_expansion_seed._DIR_BACKUP_SKILLS", str(destino))

    seed()

    arquivos = list(destino.glob("skills_pre_upsert_*.json"))
    assert len(arquivos) == 1, "o backup do prompt anterior não foi gravado"
    dados = json.loads(arquivos[0].read_text(encoding="utf-8"))
    salvo = {s["name"]: s for s in dados["skills"]}
    assert salvo["prescricao-decadencia"]["system_prompt"] == (
        "PROMPT ANTIGO QUE PRECISA SOBREVIVER"
    )
    # O backup guarda o suficiente para reconstruir a linha, não só o prompt.
    for campo in ("display_name", "description", "area", "version"):
        assert campo in salvo["prescricao-decadencia"]


def test_seed_nao_comita_se_o_backup_falhar(monkeypatch, tmp_path):
    """Prova por negação da ordem: o backup é gravado ANTES do commit e sua
    falha ABORTA a transação. Se a ordem se inverter, o prompt antigo já teria
    sido destruído quando a escrita falhasse — e este teste veria o prompt
    NOVO no banco."""
    engine = _engine_sqlite_com_tabela()
    _instalar_versao_antiga(
        engine, "prescricao-decadencia", "PROMPT ANTIGO QUE PRECISA SOBREVIVER",
    )
    monkeypatch.setattr("sqlalchemy.create_engine", lambda *_a, **_k: engine)
    monkeypatch.setenv("DATABASE_URL_SYNC", "sqlite:///:memory:")

    def _explode(*_a, **_k):
        raise OSError("disco cheio")

    monkeypatch.setattr(
        "app.seeds.skills_expansion_seed._persistir_backup", _explode)

    with pytest.raises(OSError):
        seed()

    with engine.connect() as conn:
        prompt = conn.execute(
            text("SELECT system_prompt FROM ejc_skills WHERE name='prescricao-decadencia'")
        ).scalar_one()
    assert prompt == "PROMPT ANTIGO QUE PRECISA SOBREVIVER", (
        "a transação foi comitada mesmo com o backup falhando — o prompt "
        "anterior ficou irrecuperável"
    )
