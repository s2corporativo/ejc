"""Teses — governança (migration 162): pinned, fluxo de aprovação, fork,
versionamento e injeção no system_prompt das ai_skills.

Testes de LÓGICA (sem banco): travam as regras de domínio do
``tese_governanca_service`` e a presença do ponto de integração em
``ai_skill_service`` por inspeção de fonte (mesmo padrão de
``test_ai_prompt_injection_delimitadores.py``).

Testes de BANCO (RUN_DB_TESTS=1): travam a migration, o CRUD e o fluxo
draft→approved em PostgreSQL real.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


def _source(path: str) -> str:
    return (Path(__file__).parents[1] / path).read_text(encoding="utf-8")


# ── Testes de inspeção de fonte (sem banco) ───────────────────────────────────


def test_migration_162_existe_e_encadeia():
    """A migration 162 deve existir, encadear na 161 e criar as 2 tabelas novas."""
    src = _source("alembic/versions/162_teses_pinned_flow_prompt.py")
    assert 'revision = "162_teses_pinned_flow_prompt"' in src
    assert 'down_revision = "161_fee_estornos"' in src
    assert "tese_forks" in src
    assert "tese_versions" in src
    assert "pinned" in src
    assert "revisor_id" in src


def test_model_tese_tem_novos_campos_e_classes():
    """O model tese.py deve ter pinned, experiencia_minima, revisor_id,
    revisao_em, conteudo_estruturado + TeseFork + TeseVersion."""
    src = _source("app/models/tese.py")
    assert "pinned" in src
    assert "experiencia_minima" in src
    assert "revisor_id" in src
    assert "revisao_em" in src
    assert "conteudo_estruturado" in src
    assert "class TeseFork" in src
    assert "class TeseVersion" in src
    assert "tese_forks" in src
    assert "tese_versions" in src


def test_router_governanca_existe_com_endpoints():
    src = _source("app/routers/teses_governanca.py")
    assert 'prefix="/teses"' in src
    assert "/{tese_id}/governanca" in src
    assert "/{tese_id}/submit" in src
    assert "/{tese_id}/approve" in src
    assert "/{tese_id}/fork" in src
    assert "/{tese_id}/versions" in src


def test_router_governanca_registrado_no_main():
    src = _source("app/main.py")
    assert "from app.routers import teses_governanca" in src
    assert "teses_governanca.router" in src


def test_integracao_injetada_no_ai_skill_service():
    """ai_skill_service deve chamar injetar_no_prompt nos dois pontos
    (executar_skill e executar_skill_documento_longo)."""
    src = _source("app/services/ai_skill_service.py")
    assert "from app.services.tese_governanca_service import injetar_no_prompt" in src
    # dois pontos de chamada (executar_skill + doc longo)
    assert src.count("injetar_no_prompt(") >= 2
    # o bloco deve ser envolvido em try/except (Teses = enriquecimento, não fatal)
    assert "Teses indisponíveis no prompt" in src


def test_service_tese_governanca_tem_regras_de_dominio():
    src = _source("app/services/tese_governanca_service.py")
    # RBAC: só sócio aprova
    assert "ROLES_APROVACAO" in src
    assert "_pode_aprovar" in src
    # Re-aprovação: editar conteudo de tese aprovada reverte para rascunho
    assert "TeseStatus.rascunho" in src
    # Injeção prefere fork do usuário
    assert "conteudo_para_prompt" in src
    assert "pinned" in src


# ── Testes de LÓGICA (sem banco) — regras de domínio ─────────────────────────


def test_pode_aprovar_restringe_a_socio():
    from app.services.tese_governanca_service import _pode_aprovar

    def mk(role):
        u = MagicMock()
        u.role = role
        return u

    assert _pode_aprovar(mk("socio")) is True
    assert _pode_aprovar(mk("admin")) is True
    assert _pode_aprovar(mk("socio_diretor")) is True
    assert _pode_aprovar(mk("advogado")) is False
    assert _pode_aprovar(mk("estagiario")) is False


def test_conteudo_para_prompt_prefere_fork():
    from app.services.tese_governanca_service import conteudo_para_prompt

    tese = MagicMock()
    tese.conteudo_estruturado = "CONTEUDO_BASE"
    tese.descricao = "DESC_LEGADA"

    # sem fork → usa conteudo_estruturado
    assert conteudo_para_prompt(tese, None) == "CONTEUDO_BASE"

    # com fork → prefere fork
    fork = MagicMock()
    fork.conteudo = "FORK_PERSONALIZADO"
    assert conteudo_para_prompt(tese, fork) == "FORK_PERSONALIZADO"

    # sem conteudo_estruturado → fallback descricao
    tese.conteudo_estruturado = None
    assert conteudo_para_prompt(tese, None) == "DESC_LEGADA"


def test_slugify_do_seed_normaliza_acentos():
    from app.seeds.teses_seed import _slugify

    assert _slugify("Tutela de urgência (CPC 300)") == "tutela-de-urgencia-cpc-300"
    assert _slugify("Habeas corpus (CPP 647)") == "habeas-corpus-cpp-647"
    assert _slugify("Ação de alimentos") == "acao-de-alimentos"


# ── Testes de BANCO (RUN_DB_TESTS=1) ──────────────────────────────────────────


@pytest.mark.skipif(
    not pytest.importorskip("os").environ.get("RUN_DB_TESTS"),
    reason="requer RUN_DB_TESTS=1 + PostgreSQL 16 com pgvector",
)
class TestTeseGovernancaDB:
    """Testes de integração que rodam contra PostgreSQL real.
    Ativados com RUN_DB_TESTS=1 (mesmo padrão do resto do EJC)."""

    @pytest.mark.asyncio
    async def test_editar_conteudo_aprovada_reverte_para_rascunho(self, db_session):
        from app.models.tese import Tese, TeseStatus
        from app.services.tese_governanca_service import editar_conteudo_estruturado
        from uuid import uuid4

        tese = Tese(
            id=str(uuid4()),
            titulo="Tese teste",
            descricao="desc",
            area_juridica="civel",
            tipo="escritorio",
            status=TeseStatus.ativa,
            revisor_id="socio-1",
            conteudo_estruturado="original",
        )
        db_session.add(tese)
        await db_session.commit()

        user = MagicMock()
        user.id = "adv-1"
        user.role = "advogado"

        await editar_conteudo_estruturado(
            db_session, tese.id, "novo conteudo", user
        )

        await db_session.refresh(tese)
        assert tese.conteudo_estruturado == "novo conteudo"
        assert tese.status == TeseStatus.rascunho
        assert tese.revisor_id is None
