"""Regressões críticas da auditoria do núcleo de IA e conhecimento jurídico."""
from __future__ import annotations

from types import SimpleNamespace

import pytest


async def test_gateway_fail_closed_nao_contorna_kill_switch(monkeypatch):
    from app.main import app  # noqa: F401
    from app.core.config import get_settings
    from app.services import ai_gateway

    s = get_settings()
    monkeypatch.setattr(s, "AI_EXTERNAL_PROVIDERS_ALLOWED", False)
    monkeypatch.setattr(s, "ANTHROPIC_ENABLED", True)
    monkeypatch.setattr(s, "ANTHROPIC_API_KEY", "fake")
    monkeypatch.setattr(s, "MARITACA_ENABLED", True)
    monkeypatch.setattr(s, "MARITACA_API_KEY", "fake")
    monkeypatch.setattr(s, "GROQ_API_KEY", "fake")

    chamados: list[str] = []

    async def _provider_nao_pode_ser_chamado(provider, *args, **kwargs):
        chamados.append(provider)
        raise AssertionError("kill-switch externo foi ignorado")

    monkeypatch.setattr(ai_gateway, "_chamar_provedor", _provider_nao_pode_ser_chamado)

    with pytest.raises(RuntimeError):
        await ai_gateway.chat(
            [{"role": "user", "content": "consulta jurídica sem dados pessoais"}],
            task_type="analise_juridica",
        )
    assert chamados == []


def test_ailog_pseudonimiza_resposta_e_critica_no_write_path():
    from app.models.ai_log import AILog, AITipoUso

    log = AILog(
        id="log-fake",
        user_id="user-fake",
        tipo_uso=AITipoUso.analise_caso,
        modelo="llama-3.3-70b-versatile",
        prompt_sanitizado="consulta limpa",
        resposta=(
            "A cliente Maria da Silva, CPF 123.456.789-09, "
            "deve revisar o processo 0000001-02.2020.8.13.0000."
        ),
        critica_adversarial="A testemunha João de Souza confirmou o fato.",
    )
    assert "123.456.789-09" not in (log.resposta or "")
    assert "Maria da Silva" not in (log.resposta or "")
    assert "0000001-02.2020.8.13.0000" not in (log.resposta or "")
    assert "João de Souza" not in (log.critica_adversarial or "")
    assert "[CPF_" in (log.resposta or "")
    assert "[PROCESSO_" in (log.resposta or "")


def test_ailog_preserva_cnj_quando_e_referencia_jurisprudencial_auditavel():
    from app.models.ai_log import AILog, AITipoUso

    cnj = "0000002-03.2021.8.26.0001"
    log = AILog(
        id="log-citacao",
        user_id="user-fake",
        tipo_uso=AITipoUso.consulta_rag,
        modelo="claude-sonnet",
        prompt_sanitizado="consulta limpa",
        resposta=(
            f"Conforme acórdão do TJSP no processo {cnj}, julgado em 15/04/2024, "
            "a tese exige análise do caso concreto."
        ),
    )
    assert cnj in (log.resposta or "")


def test_ailog_legado_tem_defaults_de_id_e_modelo():
    from app.models.ai_log import AILog, AITipoUso

    log = AILog(
        user_id="user-fake",
        tipo_uso=AITipoUso.outro,
        prompt_sanitizado="evento legado",
        resposta="resposta sem dados pessoais",
    )
    assert AILog.__table__.c.id.default is not None
    assert AILog.__table__.c.modelo.default is not None
    assert log.modelo is None


@pytest.mark.asyncio
async def test_context_builder_repassa_escopo_do_cliente_ao_rag(monkeypatch):
    from app.services.ai.core import context_builder
    from app.services import case_context, ai_service

    async def _dossie(_db, _case_id, sanitizar=True):
        return {"texto": "Dossiê sanitizado", "nomes_proteger": []}

    async def _escopo(_db, _case_id):
        return "cliente-escopo-1"

    capturado: dict = {}

    async def _buscar(_db, consulta, **kwargs):
        capturado["consulta"] = consulta
        capturado.update(kwargs)
        return []

    monkeypatch.setattr(case_context, "montar_dossie", _dossie)
    monkeypatch.setattr(ai_service, "_escopo_cliente_do_caso", _escopo)
    monkeypatch.setattr(ai_service, "buscar_contexto_rag", _buscar)

    ctx = await context_builder.montar_contexto(
        object(),
        mensagem="qual a tese aplicável?",
        case_id="caso-1",
        user=SimpleNamespace(id="u1"),
        usar_rag=True,
    )
    assert capturado["scope_client_id"] == "cliente-escopo-1"
    assert capturado["limite"] == 6
    assert "Dossiê sanitizado" in ctx.texto


@pytest.mark.asyncio
async def test_categoria_restrita_sem_cliente_e_bloqueada():
    from app.services.ingestion_service import upsert_documento

    with pytest.raises(ValueError, match="exige client_id"):
        await upsert_documento(
            object(),
            titulo="Precedente sem escopo",
            categoria="precedente_interno",
            conteudo="Conteúdo jurídico restrito suficientemente longo para o teste. " * 2,
            chave_origem="precedente:sem-escopo",
            client_id=None,
            embutir_vetores=False,
        )


class _ResultadoVazio:
    def scalar(self):
        return 0

    def scalars(self):
        return self

    def all(self):
        return []


class _DBCaptura:
    def __init__(self):
        self.statements: list[str] = []

    async def execute(self, statement):
        self.statements.append(str(statement))
        return _ResultadoVazio()


@pytest.mark.asyncio
async def test_listagem_rag_nao_gestao_recebe_filtro_de_ownership():
    from app.services.ai_core_hardening_patch import _listar_docs_escopado

    db = _DBCaptura()
    cu = SimpleNamespace(id="adv-1", role="advogado", client_id=None)
    resposta = await _listar_docs_escopado(db=db, cu=cu)
    sql = "\n".join(db.statements).lower()

    assert resposta["data"] == [] and resposta["total"] == 0
    assert "knowledge_docs.client_id is null" in sql
    assert "cases.advogado_responsavel_id" in sql
    assert "cases.advogado_auxiliar_id" in sql


def test_rota_listar_docs_usa_callable_escopado_apos_startup():
    from app.main import app  # noqa: F401
    from app.routers import rag
    from app.services.ai_core_hardening_patch import _listar_docs_escopado

    rota = next(r for r in rag.router.routes if getattr(r, "name", "") == "listar_docs")
    assert rota.endpoint is _listar_docs_escopado
    assert rota.dependant.call is _listar_docs_escopado
