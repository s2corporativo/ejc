"""Onda 1 do núcleo de IA (análise E2E 03/09, §9) — testes de regressão.

Cobre, sem rede e sem banco (fakes + monkeypatch, padrão dos vizinhos):
  I2 — nível por tarefa (piso decide quando o chamador não informa);
  I8 — cadeia completa de `resumo`/`chat_rapido` e deadline agregado;
  A4 — modelos/preços Anthropic + aviso único de modelo sem preço;
  A7 — custo de prompt caching até o AILog;
  A6 — cache só depois do kill-switch; cache hit grava AILog;
  A8 — despacho fail-closed e health() sem chamada real ao Groq;
  I9 — AILog em todo call site com db+user;
  S8 — vocabulário HITL canônico nas rotas que devolvem texto de modelo;
  I5 — agentes com fonte (loop, registry, catálogo, dimensão do embedding);
  C4 — escopo por caso nas buscas RAG de teses.
Todos os dados são FICTÍCIOS.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.models.ai_log import AILog, AITipoUso
from app.services import ai_gateway
from app.services.ai_gateway import GatewayResponse


# ── Fakes ─────────────────────────────────────────────────────────────────────

class _Res:
    """Resultado fake de db.execute: cobre mappings().first(), scalar_one_or_none(),
    scalars().all() e iteração."""

    def __init__(self, first=None, scalar=None, scalars=None):
        self._first, self._scalar, self._scalars = first, scalar, list(scalars or [])

    def mappings(self):
        return self

    def first(self):
        return self._first

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return self

    def all(self):
        return list(self._scalars)

    def __iter__(self):
        return iter(self._scalars)


class _FakeDB:
    def __init__(self, resultados=None):
        self._res = list(resultados or [])
        self.added: list = []
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def flush(self):
        pass

    async def rollback(self):
        pass

    async def execute(self, *a, **k):
        return self._res.pop(0) if self._res else _Res()


def _logs(db: _FakeDB) -> list[AILog]:
    return [o for o in db.added if isinstance(o, AILog)]


def _user(role="advogado", uid="u-fake-1"):
    return SimpleNamespace(id=uid, role=SimpleNamespace(value=role))


def _resp(texto="Resposta fictícia sem promessas.", **kw) -> GatewayResponse:
    base = dict(texto=texto, modelo="modelo-fake", provedor="ollama",
                task_type="analise_juridica", input_tokens=10, output_tokens=20,
                custo_estimado_brl=0.0)
    base.update(kw)
    return GatewayResponse(**base)


def _fake_chat(texto: str, captura: dict | None = None):
    async def _chat(messages, **kw):
        if captura is not None:
            captura["messages"] = messages
            captura["kw"] = kw
        return _resp(texto, task_type=kw.get("task_type", ""))
    return _chat


def _hitl_ok(d: dict) -> None:
    assert d["is_rascunho"] is True
    assert d["requer_revisao"] is True
    assert d["status_hitl"] == "gerado"
    assert d["aviso_hitl"]


@pytest.fixture
def st(monkeypatch):
    """Baseline determinística: IA ligada, Ollama local elegível, sem cache,
    sem roteamento inteligente, HITL obrigatório, deadline default."""
    s = get_settings()
    monkeypatch.setattr(s, "AI_ENABLED", True)
    monkeypatch.setattr(s, "OLLAMA_ENABLED", True)
    monkeypatch.setattr(s, "AI_PROVIDER", "auto")
    monkeypatch.setattr(s, "AI_PROVIDER_PRIORITY", "ollama,anthropic,groq")
    monkeypatch.setattr(s, "ANTHROPIC_ENABLED", False)
    monkeypatch.setattr(s, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(s, "GROQ_API_KEY", "")
    monkeypatch.setattr(s, "MARITACA_ENABLED", False)
    monkeypatch.setattr(s, "AI_EXTERNAL_PROVIDERS_ALLOWED", True)
    monkeypatch.setattr(s, "AI_RESPONSE_CACHE_ENABLED", False)
    monkeypatch.setattr(s, "ROTEAMENTO_INTELIGENTE_ENABLED", False)
    monkeypatch.setattr(s, "AI_REQUIRE_HITL", True)
    monkeypatch.setattr(s, "AI_NIVEL_INTELIGENCIA_MERITO", "maximo")
    monkeypatch.setattr(s, "AI_NIVEL_INTELIGENCIA_PADRAO", "alto")
    monkeypatch.setattr(s, "AI_CHAIN_DEADLINE_SECONDS", 240)
    return s


def _provedor_fake(captura: dict, texto="Resposta fictícia sem promessas.", usage=None):
    async def _prov(provider, model, messages, temperature, max_tokens):
        captura.setdefault("chamadas", []).append(
            {"provider": provider, "model": model, "messages": messages})
        u = {"model": model or "modelo-fake", "input_tokens": 5, "output_tokens": 7}
        u.update(usage or {})
        return texto, u
    return _prov


# ══════════════════════════════════════════════════════════════════════════════
# I2 — nível por tarefa, não por chamador
# ══════════════════════════════════════════════════════════════════════════════

class TestI2NivelPorTarefa:
    def test_schemas_e_orquestrador_sem_default_alto(self):
        from app.routers.ai_core import (
            CoreAnalyzeRequest, CoreChatRequest, CoreGenerateRequest, CoreTaskRequest,
        )
        from app.services.ai.core.orchestrator import orchestrator
        assert CoreChatRequest(mensagem="olá tudo bem").nivel_inteligencia is None
        assert CoreTaskRequest(task_type="chat", mensagem="olá tudo bem").nivel_inteligencia is None
        assert CoreAnalyzeRequest(domain="civil", mensagem="olá tudo bem").nivel_inteligencia is None
        assert CoreGenerateRequest(tipo="peca", mensagem="olá tudo bem").nivel_inteligencia is None
        assert inspect.signature(orchestrator.run).parameters["nivel_inteligencia"].default is None
        assert inspect.signature(ai_gateway.executar_tarefa_ia).parameters[
            "nivel_inteligencia"].default is None

    def test_piso_merito_aciona_firac_e_economica_nao(self, st):
        msgs = [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}]
        merito = ai_gateway._aplicar_nivel(msgs, None, task_label="elaboracao_peca")
        assert "NIVEL DE INTELIGENCIA: MAXIMO" in merito[0]["content"]
        assert "FIRAC" in merito[0]["content"]
        economica = ai_gateway._aplicar_nivel(msgs, None, task_label="chat_rapido")
        assert "FIRAC" not in " ".join(m["content"] for m in economica)
        assert "NIVEL DE INTELIGENCIA: PADRAO" in economica[0]["content"]

    @pytest.fixture
    def nucleo(self, st, monkeypatch):
        from app.services.ai import adversarial
        from app.services.ai.core import audit_logger, context_builder
        from app.services.ai.core.context_builder import ContextoMontado

        async def fake_ctx(db, **kw):
            return ContextoMontado()

        async def fake_reg(db, **kw):
            return "log-fake"

        monkeypatch.setattr(context_builder, "montar_contexto", fake_ctx)
        monkeypatch.setattr(audit_logger, "registrar", fake_reg)
        monkeypatch.setattr(adversarial, "critica_automatica_habilitada", lambda t: False)
        captura: dict = {}
        monkeypatch.setattr(ai_gateway, "_chamar_provedor", _provedor_fake(captura))
        return captura

    async def test_generate_sem_nivel_recebe_firac(self, nucleo):
        """/ai/core/generate (tipo=peca → legal_draft) sem nível → mérito → FIRAC."""
        from app.services.ai.core.orchestrator import orchestrator
        r = await orchestrator.run(
            db=None, user=_user(), task_type="legal_draft",
            mensagem="Redija minuta fictícia de contestação sobre cobrança indevida.",
        )
        sistema = " ".join(m["content"] for m in nucleo["chamadas"][0]["messages"]
                           if m["role"] == "system")
        assert "FIRAC" in sistema
        assert "NIVEL DE INTELIGENCIA: MAXIMO" in sistema
        assert r["is_rascunho"] is True

    async def test_tarefa_economica_sem_nivel_nao_recebe_firac(self, nucleo):
        """Tarefa econômica sem nível → piso 'padrao' (sem FIRAC).

        Nota registrada no relatório: `/ai/core/chat` (task_type "chat") é
        roteado pelo intent_classifier para CaseAgent/ANALISE_CASO → gateway
        `estrategia`, que É tarefa de mérito — portanto recebe FIRAC por
        desenho do classificador (fora deste pacote). A tarefa econômica do
        núcleo é `resumo` (DocumentAgent → TarefaIA.RESUMO → gateway `resumo`)."""
        from app.services.ai.core.orchestrator import orchestrator
        await orchestrator.run(db=None, user=_user(), task_type="resumo",
                               mensagem="Resuma este andamento fictício em duas linhas.")
        sistema = " ".join(m["content"] for m in nucleo["chamadas"][0]["messages"]
                           if m["role"] == "system")
        assert "FIRAC" not in sistema
        assert "NIVEL DE INTELIGENCIA: PADRAO" in sistema

    async def test_chat_do_nucleo_e_tarefa_de_merito_por_desenho(self, nucleo):
        """Documenta o comportamento atual: "chat" → CaseAgent (mérito) → FIRAC."""
        from app.services.ai.core.intent_classifier import classify_intent
        from app.services.ai.core.orchestrator import orchestrator
        assert classify_intent("chat", None, "Bom dia, tudo bem por aí?").agente == "CaseAgent"
        await orchestrator.run(db=None, user=_user(), task_type="chat",
                               mensagem="Bom dia, tudo bem por aí?")
        sistema = " ".join(m["content"] for m in nucleo["chamadas"][0]["messages"]
                           if m["role"] == "system")
        assert "NIVEL DE INTELIGENCIA: MAXIMO" in sistema

    async def test_nivel_explicito_continua_mandando(self, nucleo):
        from app.services.ai.core.orchestrator import orchestrator
        await orchestrator.run(db=None, user=_user(), task_type="chat",
                               mensagem="Bom dia, tudo bem por aí?", nivel_inteligencia="alto")
        sistema = " ".join(m["content"] for m in nucleo["chamadas"][0]["messages"]
                           if m["role"] == "system")
        assert "NIVEL DE INTELIGENCIA: ALTO" in sistema


# ══════════════════════════════════════════════════════════════════════════════
# I8 — cadeia completa e deadline agregado
# ══════════════════════════════════════════════════════════════════════════════

class TestI8CadeiaEDeadline:
    def test_resumo_e_chat_rapido_terminam_em_anthropic(self):
        for task in ("resumo", "chat_rapido"):
            assert ai_gateway.TASK_ROUTING[task][-1] == ("anthropic", None)

    def test_config_deadline_default(self):
        from app.core.config import Settings
        assert Settings.model_fields["AI_CHAIN_DEADLINE_SECONDS"].default == 240

    async def test_deadline_chat_erro_leigo_e_warning(self, st, monkeypatch, caplog):
        monkeypatch.setattr(st, "AI_CHAIN_DEADLINE_SECONDS", 1)

        async def lento(*a, **k):
            await asyncio.sleep(5)
            return "tarde demais", {}

        monkeypatch.setattr(ai_gateway, "_chamar_provedor", lento)
        with caplog.at_level(logging.WARNING, logger="ejc.ai.gateway"):
            with pytest.raises(RuntimeError) as exc:
                await ai_gateway.chat([{"role": "user", "content": "oi"}], task_type="chat_rapido")
        msg = str(exc.value).lower()
        for proibido in ("ollama", "groq", "anthropic", "maritaca", "ai_", "provider"):
            assert proibido not in msg, msg
        assert "tente novamente" in msg
        assert any("deadline" in r.getMessage() and r.levelno == logging.WARNING
                   for r in caplog.records)

    async def test_deadline_executar_tarefa_ia(self, st, monkeypatch, caplog):
        from app.services.system_prompts import TarefaIA
        monkeypatch.setattr(st, "AI_CHAIN_DEADLINE_SECONDS", 1)
        monkeypatch.setattr(ai_gateway, "_provider_elegivel", lambda p: True)
        monkeypatch.setattr(ai_gateway, "_preparar_mensagens_externo",
                            lambda m, modo, ent: (m, [], None))

        async def lento(*a, **k):
            await asyncio.sleep(5)
            return "tarde demais", {}

        monkeypatch.setattr(ai_gateway, "_chamar_provedor", lento)
        with caplog.at_level(logging.WARNING, logger="ejc.ai.gateway"):
            with pytest.raises(RuntimeError) as exc:
                await ai_gateway.executar_tarefa_ia(TarefaIA.RESUMO, "texto fictício qualquer")
        assert "tente novamente" in str(exc.value).lower()
        assert any("deadline" in r.getMessage() for r in caplog.records)

    async def test_sem_deadline_quando_zero(self, st, monkeypatch):
        monkeypatch.setattr(st, "AI_CHAIN_DEADLINE_SECONDS", 0)
        captura: dict = {}
        monkeypatch.setattr(ai_gateway, "_chamar_provedor", _provedor_fake(captura))
        r = await ai_gateway.chat([{"role": "user", "content": "oi"}], task_type="chat_rapido")
        assert r.texto and captura["chamadas"][0]["provider"] == "ollama"


# ══════════════════════════════════════════════════════════════════════════════
# A4 — modelos e preços
# ══════════════════════════════════════════════════════════════════════════════

class TestA4ModelosPrecos:
    def test_opus_5_e_superficie_moderna(self):
        from app.services.providers.anthropic_provider import _is_modern
        assert _is_modern("claude-opus-5")
        assert _is_modern("claude-opus-5-20260901")
        assert not _is_modern("claude-haiku-4-5")

    def test_tabela_vigente(self):
        from app.services.ai_cost import _PRECOS_ANTHROPIC_USD_MM as T
        assert T["claude-opus-5"] == {"input": 5.00, "output": 25.00}
        assert T["claude-sonnet-5"] == {"input": 2.00, "output": 10.00}
        assert T["claude-fable-5"] == {"input": 10.00, "output": 50.00}
        assert T["claude-fable-5-1"] == {"input": 10.00, "output": 50.00}
        assert T["claude-haiku-4-5"] == {"input": 1.00, "output": 5.00}

    def test_modelo_sem_preco_avisa_uma_vez(self, monkeypatch, caplog):
        from app.services import ai_cost
        monkeypatch.setattr(ai_cost, "_AVISADOS_SEM_PRECO", set())
        with caplog.at_level(logging.WARNING, logger="ejc.ai.cost"):
            assert ai_cost.estimar_custo_brl("anthropic", 10, 10, "claude-inexistente-9") == 0
            assert ai_cost.estimar_custo_brl("anthropic", 10, 10, "claude-inexistente-9") == 0
        avisos = [r for r in caplog.records if "claude-inexistente-9" in r.getMessage()]
        assert len(avisos) == 1 and avisos[0].levelno == logging.WARNING

    def test_id_com_sufixo_de_data_herda_preco(self, monkeypatch):
        from app.services import ai_cost
        monkeypatch.setenv("USD_BRL_RATE", "5.00")
        assert ai_cost.estimar_custo_brl(
            "anthropic", 1_000_000, 0, "claude-sonnet-5-20260101") == Decimal("10.000000")


# ══════════════════════════════════════════════════════════════════════════════
# A7 — custo de prompt caching
# ══════════════════════════════════════════════════════════════════════════════

class TestA7PromptCaching:
    def test_formula_criacao_1_25_e_leitura_0_10(self, monkeypatch):
        from app.services.ai_cost import estimar_custo_brl
        monkeypatch.setenv("USD_BRL_RATE", "5.00")
        # haiku: input US$1/M. 1M input + 1M criação (×1,25) + 1M leitura (×0,10)
        # = US$ 2,35 → R$ 11,75.
        custo = estimar_custo_brl("anthropic", 1_000_000, 0, "claude-haiku-4-5",
                                  cache_creation_input_tokens=1_000_000,
                                  cache_read_input_tokens=1_000_000)
        assert custo == Decimal("11.750000")
        sem_cache = estimar_custo_brl("anthropic", 1_000_000, 0, "claude-haiku-4-5")
        assert sem_cache == Decimal("5.000000")

    async def test_gateway_propaga_tokens_de_cache_ate_o_ailog(self, st, monkeypatch):
        from app.services.ai_cost import estimar_custo_brl
        monkeypatch.setenv("USD_BRL_RATE", "5.00")
        monkeypatch.setattr(st, "OLLAMA_ENABLED", False)
        monkeypatch.setattr(st, "ANTHROPIC_ENABLED", True)
        monkeypatch.setattr(st, "ANTHROPIC_API_KEY", "sk-ant-fake")
        monkeypatch.setattr(ai_gateway, "_preparar_mensagens_externo",
                            lambda m, modo, ent: (m, [], None))
        captura: dict = {}
        monkeypatch.setattr(ai_gateway, "_chamar_provedor", _provedor_fake(
            captura, usage={"model": "claude-haiku-4-5", "input_tokens": 1000,
                            "output_tokens": 100, "cache_creation_input_tokens": 400,
                            "cache_read_input_tokens": 100}))
        r = await ai_gateway.chat([{"role": "user", "content": "texto limpo"}],
                                  task_type="analise_juridica")
        assert r.provedor == "anthropic"
        assert (r.cache_creation_input_tokens, r.cache_read_input_tokens) == (400, 100)
        esperado = float(estimar_custo_brl("anthropic", 1000, 100, "claude-haiku-4-5",
                                           cache_creation_input_tokens=400,
                                           cache_read_input_tokens=100))
        assert r.custo_estimado_brl == pytest.approx(esperado)
        assert esperado > float(estimar_custo_brl("anthropic", 1000, 100, "claude-haiku-4-5"))

        db = _FakeDB()
        await ai_gateway.registrar_log_resposta(
            db, user_id="u1", tipo_uso=AITipoUso.outro, resp=r, prompt_sanitizado="p")
        (log,) = _logs(db)
        assert "[prompt_cache] criacao=400 leitura=100" in log.fontes_rag
        assert float(log.custo_estimado) == pytest.approx(esperado)
        assert log.modelo == "anthropic/claude-haiku-4-5"


# ══════════════════════════════════════════════════════════════════════════════
# A6 — cache × kill-switch × AILog
# ══════════════════════════════════════════════════════════════════════════════

class TestA6CacheKillSwitch:
    async def test_chat_nao_consulta_cache_com_killswitch_desligado(self, st, monkeypatch):
        from app.services import ai_cache
        monkeypatch.setattr(st, "AI_ENABLED", False)

        async def nunca(_k):
            raise AssertionError("cache consultado com a IA desligada")

        monkeypatch.setattr(ai_cache, "obter", nunca)
        with pytest.raises(RuntimeError, match="Nenhum provedor"):
            await ai_gateway.chat([{"role": "user", "content": "oi"}], task_type="chat_rapido")

    async def test_executar_tarefa_nao_consulta_cache_sem_provedor_elegivel(self, st, monkeypatch):
        from app.services import ai_cache
        from app.services.system_prompts import TarefaIA
        monkeypatch.setattr(ai_gateway, "_provider_elegivel", lambda p: False)

        async def nunca(_k):
            raise AssertionError("cache consultado sem cadeia elegível")

        monkeypatch.setattr(ai_cache, "obter", nunca)
        with pytest.raises(RuntimeError, match="Nenhum provedor"):
            await ai_gateway.executar_tarefa_ia(TarefaIA.RESUMO, "texto fictício")

    async def test_cache_hit_em_executar_tarefa_grava_ailog_zerado(self, st, monkeypatch):
        from app.services import ai_cache
        from app.services.system_prompts import TarefaIA
        monkeypatch.setattr(ai_gateway, "_provider_elegivel", lambda p: True)

        async def hit(_k):
            return {"texto": "resposta cacheada", "modelo": "ollama/m", "provedor": "ollama"}

        async def nunca_chamar(*a, **k):
            raise AssertionError("provedor chamado num cache hit")

        monkeypatch.setattr(ai_cache, "obter", hit)
        monkeypatch.setattr(ai_gateway, "_chamar_provedor", nunca_chamar)
        db = _FakeDB()
        r = await ai_gateway.executar_tarefa_ia(
            TarefaIA.RESUMO, "texto fictício", case_id="c1", user_id="u1", db=db)
        assert r["cache_hit"] is True and r["tokens_usados"] == 0
        assert r["nivel_inteligencia"] == "padrao"      # I2: piso econômico
        (log,) = _logs(db)
        assert (log.tokens_input, log.tokens_output) == (0, 0)
        assert float(log.custo_estimado) == 0.0
        assert "[cache_hit]" in log.fontes_rag
        assert log.case_id == "c1" and log.user_id == "u1"

    def test_local_completo_nao_cacheavel(self):
        from app.services import ai_cache
        from app.services.ai.sanitization_policy import modo_para_task, ModoSanitizacao
        # Tarefa cujo modo por política é LOCAL_COMPLETO (sigilo reforçado).
        candidatos = [t for t in ("menores", "infancia_juventude", "crimes_sexuais", "sexual")
                      if modo_para_task(t) == ModoSanitizacao.LOCAL_COMPLETO]
        if not candidatos:
            pytest.skip("nenhum rótulo LOCAL_COMPLETO na política atual")
        assert ai_cache._tarefa_cacheavel(candidatos[0]) is False


# ══════════════════════════════════════════════════════════════════════════════
# A8 — fail-closed
# ══════════════════════════════════════════════════════════════════════════════

class TestA8FailClosed:
    async def test_provedor_desconhecido_nao_cai_no_groq(self, monkeypatch):
        from app.services.providers import groq_provider

        async def nunca(*a, **k):
            raise AssertionError("groq chamado para provedor desconhecido")

        monkeypatch.setattr(groq_provider, "chat", nunca)
        with pytest.raises(RuntimeError, match="desconhecido"):
            await ai_gateway._chamar_provedor("provedor_x", None, [], 0.1, 10)

    async def test_health_usa_registry_e_nao_bate_no_groq(self, st, monkeypatch):
        from app.services.providers import groq_provider
        monkeypatch.setattr(st, "OLLAMA_ENABLED", False)
        monkeypatch.setattr(st, "GROQ_ENABLED", True)
        monkeypatch.setattr(st, "GROQ_API_KEY", "gsk-fake")

        async def nunca():
            raise AssertionError("health() gastou cota do Groq")

        monkeypatch.setattr(groq_provider, "health", nunca)
        h = await ai_gateway.health()
        assert h["groq"]["disponivel"] is True and h["groq"]["motivo"] is None
        assert h["anthropic"]["disponivel"] is False
        assert "ANTHROPIC" in (h["anthropic"]["motivo"] or "")
        assert h["ollama"]["disponivel"] is False and h["ollama"]["modelos"] == []

        monkeypatch.setattr(st, "GROQ_API_KEY", "")
        h2 = await ai_gateway.health()
        assert h2["groq"]["disponivel"] is False
        assert "GROQ_API_KEY" in h2["groq"]["motivo"]


# ══════════════════════════════════════════════════════════════════════════════
# I9 — AILog em todo call site com db+user (+ S8 onde a rota devolve texto)
# ══════════════════════════════════════════════════════════════════════════════

class TestI9AILogCallSites:
    async def test_jurisprudencia_classificar_grava_ailog_e_hitl(self, monkeypatch):
        from app.routers import jurisprudencia_interna as mod
        monkeypatch.setattr(mod, "_pode_editar", lambda u: True)
        monkeypatch.setattr(ai_gateway, "chat", _fake_chat('{"area": "civil", "temas": ["x"]}'))
        j = SimpleNamespace(ementa="Ementa fictícia sobre cobrança.", area_juridica=None,
                            classificacao_ia=None, updated_at=None)
        db = _FakeDB([_Res(scalar=j)])
        out = await mod.classificar_com_ia("j1", db=db, cu=_user())
        (log,) = _logs(db)
        assert log.tipo_uso == AITipoUso.outro and "[JURISPRUDENCIA_INTERNA" in log.prompt_sanitizado
        assert out["classificacao"]["area"] == "civil" and "aviso" in out
        _hitl_ok(out)

    async def test_analise_bancaria_grava_ailog_e_hitl(self, monkeypatch):
        from app.routers import analise_bancaria as mod
        monkeypatch.setattr(ai_gateway, "chat", _fake_chat('{"resumo": "contrato fictício"}'))
        db = _FakeDB()
        texto = "Contrato de financiamento fictício com CET de 30% ao ano. " * 5
        out = await mod._analisar(texto, "default", db=db, user_id="u1")
        (log,) = _logs(db)
        assert "[ANALISE_BANCARIA" in log.prompt_sanitizado
        assert out["_aviso"] and out["_modelo"]
        _hitl_ok(out)

    async def test_analise_bancaria_sem_db_nao_grava(self, monkeypatch):
        from app.routers import analise_bancaria as mod
        monkeypatch.setattr(ai_gateway, "chat", _fake_chat('{"resumo": "x"}'))
        out = await mod._analisar("Contrato fictício. " * 20, "default")
        _hitl_ok(out)

    async def test_checklist_ia_grava_ailog(self, monkeypatch):
        from app.services import checklist_ia as mod

        async def rag(*a, **k):
            return []

        monkeypatch.setattr("app.services.ai_service.buscar_contexto_rag", rag)
        monkeypatch.setattr(ai_gateway, "chat", _fake_chat(
            '{"itens": [{"texto": "Juntar contrato", "categoria": "documentos", "obrigatorio": true}]}'))
        caso = {"id": "c1", "area": "civil", "fase": "inicial", "tese_principal": None,
                "client_id": "cl1"}
        db = _FakeDB([_Res(first=caso)])
        r = await mod.gerar_checklist_ia(db, "c1", "geral", user_id="u1")
        assert r and r["total_itens"] == 1
        (log,) = _logs(db)
        assert log.case_id == "c1" and "[CHECKLIST_IA" in log.prompt_sanitizado

    async def test_movimento_ia_grava_ailog_quando_ha_usuario(self, monkeypatch):
        from app.services import movimento_ia as mod
        monkeypatch.setattr(ai_gateway, "chat", _fake_chat("O juiz pediu um documento."))
        mov = SimpleNamespace(descricao="Juntada de petição fictícia requerendo prazo.",
                              resumo_ia=None, case_id="c1")
        db = _FakeDB([_Res(scalar=mov)])
        assert await mod.traduzir_movimento(db, "m1", user_id="u1")
        (log,) = _logs(db)
        assert log.tipo_uso == AITipoUso.resumo_documento and log.case_id == "c1"
        # Sem usuário (event_bus) → sem AILog, comportamento anterior preservado.
        db2 = _FakeDB([_Res(scalar=SimpleNamespace(descricao=mov.descricao, resumo_ia=None,
                                                    case_id="c1"))])
        assert await mod.traduzir_movimento(db2, "m1")
        assert _logs(db2) == []

    async def test_document_classifier_grava_ailog(self, monkeypatch):
        from app.services import document_classifier as mod

        async def tipos(db):
            return [{"tipo_key": "contrato", "nome": "Contrato", "descricao": None},
                    {"tipo_key": "outro", "nome": "Outro", "descricao": None}]

        monkeypatch.setattr(mod, "_tipos_validos", tipos)
        monkeypatch.setattr(ai_gateway, "chat", _fake_chat(
            '{"tipo_sugerido": "contrato", "confianca": "alta", "justificativa": "j", "alternativas": []}'))
        db = _FakeDB()
        out = await mod.classificar_documento(db, "Contrato fictício de prestação de serviços. " * 4,
                                              user_id="u1")
        assert out["tipo_sugerido"] == "contrato"
        (log,) = _logs(db)
        assert "[DOCUMENT_CLASSIFIER]" in log.prompt_sanitizado

    async def test_visual_law_grava_ailog_e_hitl(self, monkeypatch):
        from app.services import visual_law as mod
        monkeypatch.setattr(ai_gateway, "chat", _fake_chat("```mermaid\ntimeline\n  title X\n```"))
        db = _FakeDB()
        out = await mod.gerar_diagrama("Dossiê fictício sanitizado.", db=db, user_id="u1", case_id="c1")
        assert "timeline" in out["mermaid_code"] and "```" not in out["mermaid_code"]
        (log,) = _logs(db)
        assert log.case_id == "c1" and "[VISUAL_LAW" in log.prompt_sanitizado
        _hitl_ok(out)

    async def test_analise_estrategica_grava_ailog(self, monkeypatch):
        from app.services import analise_estrategica as mod

        async def rag(*a, **k):
            return [{"fonte": "Súmula 1 fictícia", "titulo": "Súmula 1", "conteudo": "texto"}]

        async def validar(db, texto, **kw):
            return {"conteudo": texto, "citacoes": [], "alertas": [],
                    "sem_base_verificavel": False, "revisao_obrigatoria": False}

        monkeypatch.setattr("app.services.ai_service.buscar_contexto_rag", rag)
        monkeypatch.setattr("app.services.ai.core.response_validator.validar", validar)
        monkeypatch.setattr(ai_gateway, "chat", _fake_chat('{"resumo": "análise fictícia"}'))
        db = _FakeDB()
        out = await mod.analisar_caso(titulo="Caso fictício", fatos="Fatos fictícios sem dados pessoais.",
                                      db=db, user_id="u1")
        assert "erro" not in out
        (log,) = _logs(db)
        assert log.tipo_uso == AITipoUso.analise_caso
        assert "[ANALISE_ESTRATEGICA]" in log.prompt_sanitizado
        assert "rank=1" in (log.fontes_rag or "")
        _hitl_ok(out)

    async def test_motor_teses_grava_ailog_hitl_e_escopo_por_caso(self, monkeypatch):
        from app.routers import teses as mod
        chamadas: list[dict] = []

        async def rag(db, consulta, **kw):
            chamadas.append(kw)
            return []

        async def escopo(db, case_id):
            return "cl1"

        async def acesso(db, cu, case_id):
            return SimpleNamespace(id=case_id)

        monkeypatch.setattr(mod, "_pode_editar", lambda u: True)
        monkeypatch.setattr("app.services.ai_service.buscar_contexto_rag", rag)
        monkeypatch.setattr("app.services.ai_service._escopo_cliente_do_caso", escopo)
        monkeypatch.setattr("app.core.ownership.verificar_acesso_caso", acesso)
        monkeypatch.setattr(ai_gateway, "chat", _fake_chat(
            '{"teses": [{"titulo": "T1", "viabilidade": "alta"}], "sintese": "s"}'))
        req = mod.MotorTesesRequest(area="civil", case_id="c1",
                                    descricao_fatos="Fatos fictícios de cobrança indevida sem dados.")
        db = _FakeDB([_Res(scalars=[])])
        out = await mod._gerar_teses(req, db, _user())
        # C4: precedentes internos restritos ao caso.
        internos = [c for c in chamadas if c.get("categorias") == ["precedente_interno"]]
        assert internos and internos[0]["scope_client_id"] == "cl1"
        assert internos[0]["scope_case_id"] == "c1"
        (log,) = _logs(db)
        assert log.case_id == "c1" and "[MOTOR_TESES]" in log.prompt_sanitizado
        assert out["teses"][0]["titulo"] == "T1" and out["_aviso"]
        _hitl_ok(out)

    async def test_sugerir_teses_hitl_e_escopo_por_caso(self, monkeypatch):
        from app.routers import teses as mod
        chamadas: list[dict] = []

        async def rag(db, consulta, **kw):
            chamadas.append(kw)
            return []

        async def escopo(db, case_id):
            return "cl1"

        async def acesso(db, cu, case_id):
            return SimpleNamespace(id=case_id)

        async def reg(db, **kw):
            return "log-1"

        monkeypatch.setattr(mod, "_pode_editar", lambda u: True)
        monkeypatch.setattr("app.services.ai_service.buscar_contexto_rag", rag)
        monkeypatch.setattr("app.services.ai_service._escopo_cliente_do_caso", escopo)
        monkeypatch.setattr("app.core.ownership.verificar_acesso_caso", acesso)
        monkeypatch.setattr("app.services.ai_guard.registrar_ai_log", reg)
        monkeypatch.setattr(ai_gateway, "chat", _fake_chat("## Teses Novas Sugeridas\n- fictícia"))
        req = mod.SugestaoIARequest(area="civil", case_id="c1",
                                    descricao_fatos="Fatos fictícios de cobrança indevida sem dados.")
        db = _FakeDB([_Res(scalars=[])])
        out = await mod.sugerir_teses_ia(req, db=db, cu=_user())
        assert chamadas and chamadas[0]["scope_client_id"] == "cl1"
        assert chamadas[0]["scope_case_id"] == "c1"
        assert out["ai_log_id"] == "log-1" and out["aviso"]
        _hitl_ok(out)


# ══════════════════════════════════════════════════════════════════════════════
# S8 — vocabulário HITL nas demais rotas (provas, documento_ia)
# ══════════════════════════════════════════════════════════════════════════════

class TestS8HITL:
    @pytest.fixture
    def provas_env(self, monkeypatch):
        from app.routers import provas as mod

        async def acesso(db, cu, case_id):
            return SimpleNamespace(id=case_id)

        async def entidades(db, case_id):
            return {}

        monkeypatch.setattr(mod, "verificar_acesso_caso", acesso)
        monkeypatch.setattr("app.services.ai.entidades_caso.entidades_do_caso", entidades)
        monkeypatch.setattr(mod, "_contexto_sugestao", lambda case, provas: "contexto fictício")
        monkeypatch.setattr(mod, "_parse_sugestoes", lambda t, ex: [{"titulo": "Prova X"}])
        return mod

    async def test_provas_sucesso(self, provas_env, monkeypatch):
        monkeypatch.setattr(ai_gateway, "chat", _fake_chat('[{"titulo": "Prova X"}]'))
        db = _FakeDB([_Res(scalars=[])])
        out = await provas_env.sugerir_provas_faltantes("c1", db=db, cu=_user())
        assert out["total"] == 1 and "aviso" in out
        assert _logs(db)   # AILog já existia nesta rota — preservado
        _hitl_ok(out)

    async def test_provas_gateway_indisponivel_tambem_carimba(self, provas_env, monkeypatch):
        async def boom(*a, **k):
            raise RuntimeError("provider down")

        monkeypatch.setattr(ai_gateway, "chat", boom)
        out = await provas_env.sugerir_provas_faltantes("c1", db=_FakeDB([_Res(scalars=[])]),
                                                       cu=_user())
        assert out["data"] == [] and "aviso" in out
        _hitl_ok(out)

    # (Fase 7 — auditoria §3.6): os dois testes de HITL da porta legada
    # /documentos-ia (analisar_url_ramos e analisar_ramo_except_do_nucleo)
    # foram aposentados JUNTO com o router documento_ia.py — zero consumidores.
    # A garantia de carimbo HITL em superfícies de análise documental segue
    # travada na trilha canônica (test_entrada_universal_analise_ia.py e
    # test_entrada_unica.py).
# ══════════════════════════════════════════════════════════════════════════════
# I5 — agentes com fonte
# ══════════════════════════════════════════════════════════════════════════════

class TestI5AgentesComFonte:
    def test_registry_process_e_lgpd_exigem_fonte(self):
        from app.services.ai.core.agent_registry import AGENT_REGISTRY
        for nome in ("ProcessAgent", "SecurityLGPDOABAgent"):
            ag = AGENT_REGISTRY[nome]
            assert ag.exige_fonte is True
            assert "validate_citations" in ag.skills and "retrieve_rag_sources" in ag.skills

    def test_skill_registry_dimensao_1024(self):
        from app.services.ai.core.skill_registry import SKILL_REGISTRY
        assert "1024d" in SKILL_REGISTRY["retrieve_rag_sources"].finalidade
        assert "768d" not in SKILL_REGISTRY["retrieve_rag_sources"].finalidade
        assert "ramo_civil" in SKILL_REGISTRY and "ramo_criminal" in SKILL_REGISTRY
        assert "ramo_civel" not in SKILL_REGISTRY and "ramo_penal" not in SKILL_REGISTRY

    def test_contexto_acumula_fontes_sem_duplicar(self):
        from app.services.ai.agent.tools.context import AgentContext
        ctx = AgentContext(db=None, user=None, case_id="c1", client_id="cl1", role="advogado")
        f = {"doc_id": "d1", "chunk_id": "k1", "titulo": "Súmula 1", "fonte": "STJ"}
        ctx.registrar_fontes([f, dict(f), {"doc_id": "d2", "chunk_id": "k2", "titulo": "S2"}])
        ctx.registrar_fontes([f])
        assert len(ctx.fontes_rag) == 2

    async def test_tool_buscar_precedentes_escopa_por_caso_e_registra_fontes(self, monkeypatch):
        from app.services.ai.agent.tools import leitura
        from app.services.ai.agent.tools.context import AgentContext
        chamadas: list[dict] = []

        async def acesso(db, user, case_id):
            return None

        async def escopo(db, case_id):
            return "cl1"

        async def rag(db, consulta, **kw):
            chamadas.append(kw)
            return [{"doc_id": "d1", "chunk_id": "k1", "titulo": "Súmula 1", "fonte": "STJ",
                     "categoria": "sumula_stj", "conteudo": "texto", "score": 0.9}]

        monkeypatch.setattr(leitura, "verificar_acesso_caso", acesso)
        monkeypatch.setattr("app.services.ai_service._escopo_cliente_do_caso", escopo)
        monkeypatch.setattr("app.services.ai_service.buscar_contexto_rag", rag)
        ctx = AgentContext(db=None, user=None, case_id="c1", client_id="cl1", role="advogado")
        r = await leitura.buscar_precedentes({"consulta": "dano moral"}, ctx)
        await leitura.buscar_precedentes({"consulta": "dano moral"}, ctx)
        assert r["total"] == 1
        assert chamadas[0]["scope_client_id"] == "cl1" and chamadas[0]["scope_case_id"] == "c1"
        assert len(ctx.fontes_rag) == 1

    async def test_loop_valida_com_fontes_reais_e_grava_no_ailog(self, st, monkeypatch):
        import app.services.ai.agent.loop as loop
        import app.services.ai.entidades_caso as ent
        import app.services.ai.core.response_validator as rv
        import app.services.ai_guard as guard
        from app.services.ai.agent.tools.registry import REGISTRY

        async def acesso(db, user, case_id):
            return SimpleNamespace(client_id="cl1", area=SimpleNamespace(value="civil"),
                                   sigilo_reforcado=False)

        async def entidades(db, case_id):
            return {}

        ailogs: list[dict] = []

        async def ailog(db, **kw):
            ailogs.append(kw)
            return "log-id"

        validacoes: list[dict] = []

        async def validar(db, conteudo, **kw):
            validacoes.append(kw)
            return {"conteudo": conteudo, "alertas": [], "revisao_obrigatoria": False}

        monkeypatch.setattr(loop, "verificar_acesso_caso", acesso)
        monkeypatch.setattr(ent, "entidades_do_caso", entidades)
        monkeypatch.setattr(guard, "registrar_ai_log", ailog)
        monkeypatch.setattr(rv, "validar", validar)

        turnos = iter([
            {"text": "Vou buscar.", "text_para_log": "Vou buscar.",
             "tool_calls": [{"id": "t1", "name": "buscar_precedentes", "input": {"consulta": "x"}}],
             "stop_reason": "tool_use",
             "usage": {"model": "m", "input_tokens": 3, "output_tokens": 4},
             "provider": "anthropic", "model": "m"},
            {"text": "Conclusão fictícia com base na Súmula 1.", "text_para_log": "Conclusão",
             "tool_calls": [], "stop_reason": "end_turn",
             "usage": {"model": "m", "input_tokens": 3, "output_tokens": 4},
             "provider": "anthropic", "model": "m"},
        ])

        async def chat_agentico(*a, **k):
            return next(turnos)

        async def executar(nome, args, ctx):
            ctx.registrar_fontes([{"doc_id": "d1", "chunk_id": "k1", "titulo": "Súmula 1",
                                   "fonte": "STJ", "categoria": "sumula_stj"}])
            return {"total": 1}

        monkeypatch.setattr(ai_gateway, "chat_agentico", chat_agentico)
        monkeypatch.setattr(REGISTRY, "executar", executar)

        r = await loop.rodar_agente(db=None, user=_user(), case_id="c1",
                                    mensagem="Analise a tese fictícia.", apenas_leitura=True)
        assert r["status"] == "ok"
        # O gate final recebeu as fontes reais (não None).
        assert validacoes and validacoes[-1]["fontes"] and validacoes[-1]["fontes"][0]["titulo"] == "Súmula 1"
        # O AILog do turno seguinte à tool carrega a trilha das fontes.
        assert ailogs[-1]["fontes_rag"] and "chunk=k1" in ailogs[-1]["fontes_rag"]
        assert r["fontes"] == [{"titulo": "Súmula 1", "categoria": "sumula_stj", "fonte": "STJ"}]


# ── Revisão de segurança 03/09/2026 — P2-2: orçamento restante da cadeia ─────
# O SDK da Anthropic é síncrono e roda em `asyncio.to_thread`, que não é
# cancelável: sem repassar o que sobra do deadline, o estouro abandonava a
# task e a requisição seguia até ANTHROPIC_TIMEOUT_SECONDS — cobrada, sem
# AILog e fora do painel de custo.
def test_orcamento_restante_sem_deadline_e_none():
    import asyncio as _aio

    from app.services import ai_gateway as gw

    async def _cenario():
        return gw._orcamento_restante()

    assert _aio.run(_cenario()) is None


def test_orcamento_restante_dentro_do_deadline(monkeypatch):
    import asyncio as _aio

    from app.core.config import get_settings
    from app.services import ai_gateway as gw

    monkeypatch.setattr(get_settings(), "AI_CHAIN_DEADLINE_SECONDS", 30)

    async def _cenario():
        async with gw._deadline_cadeia():
            return gw._orcamento_restante()

    restante = _aio.run(_cenario())
    assert restante is not None
    assert 0 < restante <= 30


def test_orcamento_restante_nunca_zero_ou_negativo(monkeypatch):
    """Timeout <= 0 viraria erro de validação no SDK; o piso deixa o
    `asyncio.timeout` externo encerrar o laço."""
    import asyncio as _aio

    from app.core.config import get_settings
    from app.services import ai_gateway as gw

    monkeypatch.setattr(get_settings(), "AI_CHAIN_DEADLINE_SECONDS", 30)

    async def _cenario():
        async with gw._deadline_cadeia():
            # Simula deadline já vencido.
            gw._DEADLINE_ABS.set(_aio.get_running_loop().time() - 5)
            return gw._orcamento_restante()

    assert _aio.run(_cenario()) >= 1.0


def test_provider_anthropic_recebe_timeout_restante(monkeypatch):
    """`_chamar_provedor` repassa o orçamento restante só para a Anthropic."""
    import asyncio as _aio

    from app.core.config import get_settings
    from app.services import ai_gateway as gw
    from app.services.providers import anthropic_provider

    monkeypatch.setattr(get_settings(), "AI_CHAIN_DEADLINE_SECONDS", 30)
    recebidos: dict = {}

    async def _fake_chat(messages, model, temperature, max_tokens, timeout_s=None):
        recebidos["timeout_s"] = timeout_s
        return ("ok", {"model": "m"})

    monkeypatch.setattr(anthropic_provider, "chat", _fake_chat)

    async def _cenario():
        async with gw._deadline_cadeia():
            return await gw._chamar_provedor(
                "anthropic", None, [{"role": "user", "content": "oi"}], 0.2, 100,
            )

    texto, _ = _aio.run(_cenario())
    assert texto == "ok"
    assert recebidos["timeout_s"] is not None
    assert 0 < recebidos["timeout_s"] <= 30


def test_ai_executar_sem_nivel_deixa_o_piso_decidir():
    """I2 aplicado também em POST /ai/executar: o default fixo "alto" fazia
    esta porta ignorar AI_NIVEL_INTELIGENCIA_MERITO."""
    from app.routers.ai_tools import AiRequest
    from app.services.system_prompts import TarefaIA

    req = AiRequest(tarefa=TarefaIA.ANALISE_CASO, mensagem="fatos do caso para análise")
    assert req.nivel_inteligencia is None
    # Quem informar explicitamente continua sendo respeitado.
    req2 = AiRequest(
        tarefa=TarefaIA.ANALISE_CASO, mensagem="fatos do caso", nivel_inteligencia="maximo",
    )
    assert req2.nivel_inteligencia == "maximo"
