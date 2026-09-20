"""Fase 5 — Modo Duas IAs (crítica adversarial de peças).

Tudo mockado (gateway/citation_gate) — nenhum teste toca rede ou banco real.
Settings via monkeypatch nos atributos da instância cacheada de get_settings().
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.services.ai_gateway import GatewayResponse

TEXTO_PECA = (
    "EXCELENTÍSSIMO SENHOR DOUTOR JUIZ — petição inicial fictícia de "
    "indenização por danos morais, com fatos e pedidos inventados para teste."
)

RELATORIO_OK = (
    "## 1. CONTRADIÇÕES\nNenhuma identificada.\n"
    "## 2. LACUNAS FÁTICAS\nFalta a data exata do evento danoso.\n"
    "## 3. FRAGILIDADES PROBATÓRIAS\nDano moral afirmado sem prova.\n"
    "## 4. TESES DEFENSIVAS PROVÁVEIS\nCulpa exclusiva da vítima.\n"
    "## 5. JURISPRUDÊNCIA CONTRÁRIA A VERIFICAR\nLinha restritiva do STJ — verificar fonte.\n"
    "## 6. NOTA DE ROBUSTEZ\nNOTA DE ROBUSTEZ: 72\nPeça razoável, mas com lacunas."
)


@pytest.fixture
def s(monkeypatch):
    """Baseline: Anthropic e Groq elegíveis, Ollama OFF, Duas IAs OFF."""
    st = get_settings()
    monkeypatch.setattr(st, "ANTHROPIC_ENABLED", True)
    monkeypatch.setattr(st, "ANTHROPIC_API_KEY", "sk-ant-fake-para-testes")
    monkeypatch.setattr(st, "GROQ_API_KEY", "gsk-fake-para-testes")
    monkeypatch.setattr(st, "OLLAMA_ENABLED", False)
    monkeypatch.setattr(st, "AI_EXTERNAL_PROVIDERS_ALLOWED", True)
    monkeypatch.setattr(st, "AI_REQUIRE_SANITIZATION_FOR_EXTERNAL", True)
    monkeypatch.setattr(st, "AI_PROVIDER_PRIORITY", "ollama,anthropic,groq")
    monkeypatch.setattr(st, "AI_PROVIDER", "auto")
    monkeypatch.setattr(st, "DUAS_IAS_ENABLED", False)
    monkeypatch.setattr(st, "DUAS_IAS_TASK_TYPES", "elaboracao_peca,auditoria_peca")
    return st


def _fake_chat(box: dict, *, texto: str = RELATORIO_OK, provedor: str = "anthropic",
               falhar: bool = False):
    async def fake(messages, **kw):
        box["messages"] = messages
        box.update(kw)
        if falhar:
            raise RuntimeError("provider fora do ar (simulado)")
        return GatewayResponse(
            texto=texto, modelo="modelo-fake", provedor=provedor,
            task_type=kw.get("task_type", ""), input_tokens=10, output_tokens=20,
        )
    return fake


# ══════════════════════════════════════════════════════════════════════════════
# 1. Seleção de provider DIVERSO do proponente
# ══════════════════════════════════════════════════════════════════════════════

class TestProviderDiverso:
    def test_origem_ollama_prefere_anthropic(self, s):
        from app.services.ai.adversarial import escolher_provider_diverso
        assert escolher_provider_diverso("ollama") == "anthropic"

    def test_origem_anthropic_cai_no_groq_sem_ollama(self, s):
        from app.services.ai.adversarial import escolher_provider_diverso
        assert escolher_provider_diverso("anthropic") == "groq"

    def test_origem_anthropic_prefere_ollama_quando_ligado(self, s, monkeypatch):
        from app.services.ai.adversarial import escolher_provider_diverso
        monkeypatch.setattr(s, "OLLAMA_ENABLED", True)
        assert escolher_provider_diverso("anthropic") == "ollama"

    def test_nenhum_diverso_elegivel_devolve_none(self, s, monkeypatch):
        from app.services.ai.adversarial import escolher_provider_diverso
        monkeypatch.setattr(s, "ANTHROPIC_API_KEY", "")
        # Só groq elegível e groq é o próprio origem.
        assert escolher_provider_diverso("groq") is None


# ══════════════════════════════════════════════════════════════════════════════
# 2. Gate por flag/task_type (DUAS_IAS_ENABLED + DUAS_IAS_TASK_TYPES)
# ══════════════════════════════════════════════════════════════════════════════

class TestGatePorFlag:
    def test_flag_desligada_nunca_habilita(self, s):
        from app.services.ai.adversarial import critica_automatica_habilitada
        assert critica_automatica_habilitada("elaboracao_peca") is False

    def test_flag_ligada_task_elegivel(self, s, monkeypatch):
        from app.services.ai.adversarial import critica_automatica_habilitada
        monkeypatch.setattr(s, "DUAS_IAS_ENABLED", True)
        assert critica_automatica_habilitada("elaboracao_peca") is True
        assert critica_automatica_habilitada("auditoria_peca") is True
        assert critica_automatica_habilitada("resumo") is False
        assert critica_automatica_habilitada(None) is False

    def test_alias_de_task_type_normalizado(self, s, monkeypatch):
        # "redacao_peca" é alias de "elaboracao_peca" no gateway.
        from app.services.ai.adversarial import critica_automatica_habilitada
        monkeypatch.setattr(s, "DUAS_IAS_ENABLED", True)
        monkeypatch.setattr(s, "DUAS_IAS_TASK_TYPES", "redacao_peca")
        assert critica_automatica_habilitada("elaboracao_peca") is True

    def test_task_critica_tem_cadeia_no_gateway(self, s):
        from app.services.ai_gateway import _resolver_cadeia
        providers = [p for p, _ in _resolver_cadeia("critica_adversarial", None, None)]
        assert "anthropic" in providers  # tarefa complexa inclui Anthropic


# ══════════════════════════════════════════════════════════════════════════════
# 3. criticar_peca — sucesso, diversidade e gate de citações da crítica
# ══════════════════════════════════════════════════════════════════════════════

class TestCriticarPeca:
    async def test_sucesso_com_provider_diverso_e_nota(self, s, monkeypatch):
        from app.services import ai_gateway, citation_gate
        from app.services.ai import adversarial

        box: dict = {}
        monkeypatch.setattr(ai_gateway, "chat", _fake_chat(box, provedor="anthropic"))

        gate_calls: list[str] = []

        async def fake_validar(db, texto, **kw):
            gate_calls.append(texto)
            return citation_gate.RelatorioCitacoes(politica="marcar", total=1)

        monkeypatch.setattr(citation_gate, "validar_citacoes", fake_validar)

        c = await adversarial.criticar_peca(
            db=object(), texto_peca=TEXTO_PECA,
            task_type_origem="elaboracao_peca", provedor_origem="ollama",
        )
        assert c.disponivel is True
        assert c.nota_robustez == 72
        assert c.provider_diverso is True
        assert c.provedor == "anthropic" and c.provedor_origem == "ollama"
        # Pediu explicitamente o provider diverso ao gateway.
        assert box["provider_override"] == "anthropic"
        assert box["task_type"] == "critica_adversarial"
        # A PRÓPRIA crítica passou pelo gate de citações.
        assert gate_calls == [RELATORIO_OK]
        assert c.citacoes is not None and c.citacoes.politica == "marcar"

    async def test_critica_com_citacao_bloqueante_gera_alerta(self, s, monkeypatch):
        from app.services import ai_gateway, citation_gate
        from app.services.ai import adversarial

        monkeypatch.setattr(ai_gateway, "chat", _fake_chat({}))

        async def fake_validar(db, texto, **kw):
            return citation_gate.RelatorioCitacoes(
                politica="marcar", total=1, nao_verificadas=1,
                bloqueantes=[citation_gate.CitacaoBloqueante(
                    citacao="Súmula 999/STJ", tipo="sumula",
                    status="suspeita", motivo="fora de faixa",
                )],
            )

        monkeypatch.setattr(citation_gate, "validar_citacoes", fake_validar)
        c = await adversarial.criticar_peca(db=object(), texto_peca=TEXTO_PECA)
        assert c.disponivel is True
        assert any("alucinação" in a for a in c.alertas)

    async def test_sem_db_pula_gate_com_alerta(self, s, monkeypatch):
        from app.services import ai_gateway
        from app.services.ai import adversarial
        monkeypatch.setattr(ai_gateway, "chat", _fake_chat({}))
        c = await adversarial.criticar_peca(db=None, texto_peca=TEXTO_PECA)
        assert c.disponivel is True
        assert c.citacoes is None
        assert any("Gate de citações" in a for a in c.alertas)

    async def test_mesmo_provider_quando_nao_ha_diverso(self, s, monkeypatch):
        from app.services import ai_gateway
        from app.services.ai import adversarial
        # Só Anthropic elegível e a peça veio do Anthropic.
        monkeypatch.setattr(s, "GROQ_API_KEY", "")
        box: dict = {}
        monkeypatch.setattr(ai_gateway, "chat", _fake_chat(box, provedor="anthropic"))
        c = await adversarial.criticar_peca(
            db=None, texto_peca=TEXTO_PECA, provedor_origem="anthropic",
        )
        assert box["provider_override"] is None  # cadeia automática
        assert c.provider_diverso is False
        assert any("MESMO provider" in a for a in c.alertas)

    async def test_falha_de_provider_nao_levanta_excecao(self, s, monkeypatch):
        from app.services import ai_gateway
        from app.services.ai import adversarial
        monkeypatch.setattr(ai_gateway, "chat", _fake_chat({}, falhar=True))
        c = await adversarial.criticar_peca(
            db=object(), texto_peca=TEXTO_PECA, provedor_origem="ollama",
        )
        assert c.disponivel is False
        assert c.relatorio is None
        assert c.aviso == adversarial.AVISO_INDISPONIVEL
        assert any("Falha na IA Crítica" in a for a in c.alertas)

    async def test_falha_do_gate_nao_derruba_critica(self, s, monkeypatch):
        from app.services import ai_gateway, citation_gate
        from app.services.ai import adversarial
        monkeypatch.setattr(ai_gateway, "chat", _fake_chat({}))

        async def gate_quebrado(db, texto, **kw):
            raise RuntimeError("verificador fora")

        monkeypatch.setattr(citation_gate, "validar_citacoes", gate_quebrado)
        c = await adversarial.criticar_peca(db=object(), texto_peca=TEXTO_PECA)
        assert c.disponivel is True
        assert c.citacoes is None
        assert any("indisponível" in a for a in c.alertas)

    def test_extrair_nota_robustez(self):
        from app.services.ai.adversarial import extrair_nota_robustez
        assert extrair_nota_robustez("NOTA DE ROBUSTEZ: 85") == 85
        assert extrair_nota_robustez("nota de robustez - 7") == 7
        assert extrair_nota_robustez("NOTA DE ROBUSTEZ: 250") is None
        assert extrair_nota_robustez("sem nota") is None
        assert extrair_nota_robustez(None) is None


# ══════════════════════════════════════════════════════════════════════════════
# 3b. LGPD — a crítica pseudonimiza os NOMES do caso antes do provider externo
#     (issue #103: sem `entidades`, nome de cliente/parte contrária vazava)
# ══════════════════════════════════════════════════════════════════════════════

class _ResEnt:
    def __init__(self, val, sigilo: bool = False):
        self._val = val
        self._sigilo = sigilo

    def scalar_one_or_none(self):
        return self._val

    def first(self):
        # `criticar_peca` também consulta o PISO DE SIGILO do caso
        # (`SELECT sigilo_reforcado …`), que lê a linha por `.first()`.
        return (self._sigilo,)


class _CaseDB:
    """Sessão fake: execute() devolve o Case (entidades_do_caso) e, via
    `.first()`, o `sigilo_reforcado` do caso (piso de sigilo da crítica)."""

    def __init__(self, caso):
        self._caso = caso

    async def execute(self, *a, **k):
        return _ResEnt(self._caso, bool(getattr(self._caso, "sigilo_reforcado", False)))


class TestCriticaProtegeNomesLGPD:
    """A minuta criticada traz nomes reais (cliente/parte contrária) EM CLARO.
    A crítica prefere provider EXTERNO — os nomes NÃO podem vazar: devem virar
    marcadores consistentes antes do externo e ser reidratados na resposta."""

    def _caso_com_nomes(self):
        from app.models.case import Case
        from app.models.case_parte import CaseParte
        from app.models.client import Client, ClientTipo
        cli = Client(id="cli1", tipo=ClientTipo.PF, nome="João da Silva")
        parte = CaseParte(id="p1", case_id="c1", tipo="reu",
                          papel_processual="Réu", nome="Construtora Alfa Ltda")
        return Case(id="c1", titulo="Ação fictícia", client_id="cli1",
                    deleted_at=None, client=cli, partes=[parte],
                    advogado_responsavel=None, parte_contraria="Banco Omega S.A.")

    async def test_case_id_pseudonimiza_nomes_e_reidrata(self, s, monkeypatch):
        """Round-trip real (mocka só o provider de baixo nível): com case_id, os
        nomes do caso viram marcadores antes do externo e voltam reidratados."""
        from app.services import ai_gateway, citation_gate
        from app.services.ai import adversarial

        capturado: dict = {}

        async def _fake_provedor(provider, model, messages, temperature, max_tokens):
            capturado["provider"] = provider
            capturado["conteudo"] = " ".join(m.get("content", "") for m in messages)
            # A IA Crítica raciocina SÓ sobre os marcadores e cita a nota.
            return (
                "## 6. NOTA DE ROBUSTEZ\nNOTA DE ROBUSTEZ: 60\n"
                "Peça de [CLIENTE_1] contra [PARTE_CONTRARIA_1] e "
                "[PARTE_CONTRARIA_2] tem lacunas.",
                {"model": model or provider, "input_tokens": 5, "output_tokens": 9},
            )

        monkeypatch.setattr(ai_gateway, "_chamar_provedor", _fake_provedor)
        # Gate de citações mockado (o _CaseDB só serve à montagem de entidades).
        async def _fake_validar(db, texto, **kw):
            return citation_gate.RelatorioCitacoes(politica="marcar", total=0)
        monkeypatch.setattr(citation_gate, "validar_citacoes", _fake_validar)

        texto_peca = (
            "EXCELENTÍSSIMO JUIZ — o autor João da Silva move ação contra "
            "Construtora Alfa Ltda e Banco Omega S.A. por danos morais."
        )
        c = await adversarial.criticar_peca(
            db=_CaseDB(self._caso_com_nomes()),
            texto_peca=texto_peca,
            contexto_caso="Cliente João da Silva; parte contrária Construtora Alfa Ltda.",
            task_type_origem="elaboracao_peca",
            provedor_origem="ollama",  # crítica cai no anthropic (externo)
            case_id="c1",
        )

        # (a) provider EXTERNO recebeu SÓ marcadores — nenhum nome real vazou.
        assert capturado["provider"] in ("anthropic", "groq")
        for nome in ("João da Silva", "Construtora Alfa Ltda", "Banco Omega S.A."):
            assert nome not in capturado["conteudo"], f"vazou ao externo: {nome!r}"
        assert "[CLIENTE_1]" in capturado["conteudo"]
        assert "[PARTE_CONTRARIA_1]" in capturado["conteudo"]
        # (b) relatório devolvido ao chamador está REIDRATADO (nomes reais).
        assert c.disponivel is True
        for nome in ("João da Silva", "Banco Omega S.A.", "Construtora Alfa Ltda"):
            assert nome in c.relatorio, f"reidratação falhou para {nome!r}"
        assert "[CLIENTE_1]" not in c.relatorio
        assert "[PARTE_CONTRARIA_1]" not in c.relatorio
        assert "[PARTE_CONTRARIA_2]" not in c.relatorio

    async def test_sem_case_id_degrada_sem_crash_entidades_none(self, s, monkeypatch):
        """Sem case_id/entidades a crítica NÃO quebra: passa entidades=None ao
        gateway (barreira ESTRUTURAL do gateway segue ativa)."""
        from app.services import ai_gateway
        from app.services.ai import adversarial
        box: dict = {}
        monkeypatch.setattr(ai_gateway, "chat", _fake_chat(box))
        c = await adversarial.criticar_peca(db=None, texto_peca=TEXTO_PECA)
        assert c.disponivel is True
        assert box.get("entidades") is None  # degradou sem entidades, sem crash

    async def test_entidades_prontas_repassadas_sem_reconsultar_banco(self, s, monkeypatch):
        """Quando o chamador (orquestrador) já traz `entidades`, elas são
        repassadas ao gateway SEM tocar o banco (case_id é ignorado)."""
        from app.services import ai_gateway
        from app.services.ai import adversarial, entidades_caso
        box: dict = {}
        monkeypatch.setattr(ai_gateway, "chat", _fake_chat(box))

        async def _boom(*a, **k):  # entidades_do_caso NÃO deve ser chamado
            raise AssertionError("entidades_do_caso não deveria ser consultado")
        monkeypatch.setattr(entidades_caso, "entidades_do_caso", _boom)

        ent = {"cliente": ["João da Silva"], "parte_contraria": ["Construtora Alfa Ltda"]}
        c = await adversarial.criticar_peca(
            db=None, texto_peca=TEXTO_PECA, case_id="c1", entidades=ent,
        )
        assert c.disponivel is True
        assert box["entidades"] == ent


# ══════════════════════════════════════════════════════════════════════════════
# 4. Gravação da crítica em campo DEDICADO (migration 070 — NÃO em `resposta`)
# ══════════════════════════════════════════════════════════════════════════════

class _FakeDB:
    def __init__(self, log):
        self._log = log
        self.commits = 0

    async def get(self, model, pk):
        return self._log

    async def commit(self):
        self.commits += 1


class TestAnexarAoAILog:
    async def test_grava_relatorio_em_campo_dedicado(self, s):
        from app.services.ai import adversarial
        critica = adversarial.CriticaAdversarial(
            disponivel=True, relatorio=RELATORIO_OK, nota_robustez=72,
            provedor="anthropic", modelo="claude-fake",
            provedor_origem="ollama", provider_diverso=True,
        )
        log = SimpleNamespace(resposta="TEXTO DA PEÇA", critica_adversarial=None)
        db = _FakeDB(log)
        ok = await adversarial.anexar_critica_ao_log(db, "log-1", critica)
        assert ok is True and db.commits == 1
        # A crítica vai no campo DEDICADO — `resposta` (peça) fica INTACTA.
        assert log.resposta == "TEXTO DA PEÇA"
        assert adversarial.MARCADOR_AILOG not in (log.resposta or "")
        assert adversarial.MARCADOR_AILOG in log.critica_adversarial
        assert "Nota de robustez: 72/100" in log.critica_adversarial
        assert "DIVERSO" in log.critica_adversarial

    async def test_critica_nao_contamina_resposta(self, s):
        """A jurisprudência ESPECULATIVA da crítica não pode entrar em `resposta`
        (que alimenta o gate de aprovação e a ingestão RAG)."""
        from app.services.ai import adversarial
        critica = adversarial.CriticaAdversarial(
            disponivel=True, relatorio=RELATORIO_OK, nota_robustez=72,
            provedor="anthropic", modelo="claude-fake",
        )
        log = SimpleNamespace(resposta="PEÇA LIMPA", critica_adversarial=None)
        await adversarial.anexar_critica_ao_log(_FakeDB(log), "log-1", critica)
        assert log.resposta == "PEÇA LIMPA"
        # "verificar fonte" (jurisprudência especulativa) só no campo dedicado.
        assert "verificar fonte" in log.critica_adversarial
        assert "verificar fonte" not in log.resposta

    async def test_critica_indisponivel_grava_aviso_no_campo_dedicado(self, s):
        from app.services.ai import adversarial
        critica = adversarial.CriticaAdversarial(
            disponivel=False, aviso=adversarial.AVISO_INDISPONIVEL,
        )
        log = SimpleNamespace(resposta="PEÇA", critica_adversarial=None)
        assert await adversarial.anexar_critica_ao_log(_FakeDB(log), "log-1", critica) is True
        assert log.resposta == "PEÇA"
        assert adversarial.AVISO_INDISPONIVEL in log.critica_adversarial

    async def test_sem_db_ou_log_nao_quebra(self, s):
        from app.services.ai import adversarial
        critica = adversarial.CriticaAdversarial(disponivel=False)
        assert await adversarial.anexar_critica_ao_log(None, "x", critica) is False
        assert await adversarial.anexar_critica_ao_log(_FakeDB(None), "x", critica) is False


# ══════════════════════════════════════════════════════════════════════════════
# 4b. Isolamento: gate de aprovação e ingestão RAG NÃO veem a crítica
# ══════════════════════════════════════════════════════════════════════════════

class _CitacoesResult:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj

    def scalars(self):
        return self

    def first(self):
        return self._obj


class _ExecDB:
    """DB mínimo com execute()→scalar_one_or_none() e commit() (fluxos router)."""
    def __init__(self, obj):
        self._obj = obj
        self.commits = 0

    async def execute(self, *a, **kw):
        return _CitacoesResult(self._obj)

    async def commit(self):
        self.commits += 1


class TestIsolamentoCriticaDoGateEIngestao:
    async def test_gate_aprovacao_peca_ignora_critica_especulativa(self, s, monkeypatch):
        """política=bloquear: o gate varre SÓ `resposta` (peça) — a
        jurisprudência especulativa da crítica no campo dedicado NÃO bloqueia."""
        from app.services import citation_gate
        from app.services.ai.adversarial import MARCADOR_AILOG
        monkeypatch.setattr(s, "CITACOES_POLITICA", "bloquear")

        capturado = {}

        async def fake_validar(db, texto, **kw):
            capturado["texto"] = texto
            return citation_gate.RelatorioCitacoes(politica="bloquear")

        monkeypatch.setattr(citation_gate, "validar_citacoes", fake_validar)

        log = SimpleNamespace(
            id="log-x",
            resposta="Peça limpa, sem jurisprudência.",
            critica_adversarial=(
                MARCADOR_AILOG + "\n## 5. JURISPRUDÊNCIA CONTRÁRIA A VERIFICAR\n"
                "Linha adversa do STJ — verificar fonte."
            ),
            fontes_rag=None,
        )
        gate = await citation_gate.aplicar_gate_hitl(
            None, log, "revisado", False, None, SimpleNamespace(id="rev-1"),
        )
        # O texto verificado é SÓ a peça — a crítica especulativa ficou de fora.
        assert capturado["texto"] == "Peça limpa, sem jurisprudência."
        assert "verificar fonte" not in capturado["texto"]
        assert gate is not None and gate.bloqueia_aprovacao is False

    async def test_ingestao_ailog_aprovado_destila_so_a_peca(self, monkeypatch):
        """A ingestão RAG usa `resposta` — a crítica no campo dedicado nunca vai
        para a base de conhecimento."""
        import datetime as _dt
        from app.routers import rag as rag_router
        from app.routers.rag import ingerir_ai_log_aprovado, IngerirAILogRequest
        from app.services import ingestion_service
        from app.models.ai_log import AIStatusHITL, AITipoUso
        from app.services.ai.adversarial import MARCADOR_AILOG

        capturado = {}

        async def fake_upsert(
            db, *, titulo, categoria, conteudo, chave_origem, fonte, **kw
        ):
            capturado["conteudo"] = conteudo
            capturado["extra"] = kw.get("extra")
            return "novo"

        monkeypatch.setattr(ingestion_service, "upsert_documento", fake_upsert)
        monkeypatch.setattr(rag_router, "chunk_texto", lambda t: ["c1", "c2"])

        async def fake_audit(*a, **kw):
            return None

        monkeypatch.setattr(rag_router, "criar_audit_log", fake_audit)

        log = SimpleNamespace(
            id="log-1", user_id="user-1", case_id=None,
            status_hitl=AIStatusHITL.revisado,
            tipo_uso=AITipoUso.redacao_peca,
            created_at=_dt.datetime(2026, 7, 5),
            resposta="Peça institucional aprovada e limpa, com folga de cinquenta caracteres.",
            critica_adversarial=MARCADOR_AILOG + " verificar fonte STJ especulativo",
        )
        out = await ingerir_ai_log_aprovado(
            "log-1", IngerirAILogRequest(), db=_ExecDB(log),
            cu=SimpleNamespace(
                id="user-1",
                role=SimpleNamespace(value="advogado"),
            ),
        )
        assert out["ok"] is True
        assert capturado["conteudo"] == log.resposta
        assert capturado["extra"]["rag_status"] == "pendente"
        assert capturado["extra"]["requires_human_review"] is True
        assert capturado["extra"]["human_reviewed"] is False
        assert "verificar fonte" not in capturado["conteudo"]
        assert MARCADOR_AILOG not in capturado["conteudo"]


@pytest.mark.asyncio
async def test_ingestao_ailog_com_caso_revalida_ownership_e_propaga_escopo(monkeypatch):
    from app.routers import rag as rag_router
    from app.routers.rag import IngerirAILogRequest, ingerir_ai_log_aprovado
    from app.models.ai_log import AIStatusHITL, AITipoUso
    from app.services import ingestion_service, ai_service
    from app.core import ownership

    capturado = {}
    ownership_calls = []

    async def fake_upsert(db, **kw):
        capturado.update(kw)
        return "novo"

    async def fake_audit(*a, **kw):
        return None

    async def fake_scope(db, case_id):
        assert case_id == "caso-1"
        return "cli-1"

    async def fake_ownership(db, cu, case_id):
        ownership_calls.append((str(cu.id), case_id))
        return SimpleNamespace(id=case_id, client_id="cli-1")

    monkeypatch.setattr(ingestion_service, "upsert_documento", fake_upsert)
    monkeypatch.setattr(rag_router, "chunk_texto", lambda t: ["c1"])
    monkeypatch.setattr(rag_router, "criar_audit_log", fake_audit)
    monkeypatch.setattr(ai_service, "_escopo_cliente_do_caso", fake_scope)
    monkeypatch.setattr(ownership, "verificar_acesso_caso", fake_ownership)

    log = SimpleNamespace(
        id="log-case",
        user_id="user-1",
        case_id="caso-1",
        status_hitl=AIStatusHITL.revisado,
        resposta="Resposta jurídica revisada com conteúdo suficiente para destilação governada no RAG.",
        tipo_uso=AITipoUso.analise,
        created_at=datetime.now(timezone.utc),
    )
    cu = SimpleNamespace(id="user-1", role=SimpleNamespace(value="advogado"))

    out = await ingerir_ai_log_aprovado(
        "log-case",
        IngerirAILogRequest(categoria="conhecimento_ia"),
        db=_ExecDB(log),
        cu=cu,
    )

    assert out["ok"] is True
    assert ownership_calls == [("user-1", "caso-1")]
    assert capturado["client_id"] == "cli-1"
    assert capturado["case_id"] == "caso-1"
    assert capturado["extra"]["rag_status"] == "pendente"


# ══════════════════════════════════════════════════════════════════════════════
# 4c. Hardening: marcador reservado forjado no texto de entrada é neutralizado
# ══════════════════════════════════════════════════════════════════════════════

class TestMarcadorForjado:
    def test_neutralizar_marcador_ailog(self):
        from app.services.ai import adversarial
        t = "conteúdo " + adversarial.MARCADOR_AILOG + " forjado"
        out = adversarial.neutralizar_marcador_ailog(t)
        assert adversarial.MARCADOR_AILOG not in out
        assert adversarial._MARCADOR_NEUTRALIZADO in out

    def test_neutralizar_marcador_none_e_vazio(self):
        from app.services.ai import adversarial
        assert adversarial.neutralizar_marcador_ailog(None) is None
        assert adversarial.neutralizar_marcador_ailog("") == ""

    async def test_marcador_forjado_nao_chega_ao_prompt(self, s, monkeypatch):
        from app.services import ai_gateway
        from app.services.ai import adversarial
        box = {}
        monkeypatch.setattr(ai_gateway, "chat", _fake_chat(box, provedor="anthropic"))
        texto = "Peça " + adversarial.MARCADOR_AILOG + " com marcador forjado embutido"
        # db=None → gate de citações pulado; foco é a neutralização do marcador.
        critica = await adversarial.criticar_peca(None, texto_peca=texto)
        assert critica.disponivel is True
        user_msg = box["messages"][1]["content"]
        assert adversarial.MARCADOR_AILOG not in user_msg
        assert adversarial._MARCADOR_NEUTRALIZADO in user_msg

    async def test_delimitador_prompt_tem_token_aleatorio(self, s):
        """Cada chamada usa um token de delimitador diferente (anti-escape)."""
        from app.services.ai.adversarial import _montar_user_prompt
        import re as _re
        p1 = _montar_user_prompt("peça um", None)
        p2 = _montar_user_prompt("peça dois", None)
        tok1 = _re.search(r"\[PEÇA A CRITICAR::([0-9a-f]{8}) ", p1).group(1)
        tok2 = _re.search(r"\[PEÇA A CRITICAR::([0-9a-f]{8}) ", p2).group(1)
        assert tok1 != tok2
        assert f"[/PEÇA A CRITICAR::{tok1}]" in p1


# ══════════════════════════════════════════════════════════════════════════════
# 5. Integração no orchestrator (Núcleo Único) — tudo mockado
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def nucleo_mocks(s, monkeypatch):
    from app.services import ai_gateway
    from app.services.ai.core import audit_logger, context_builder
    from app.services.ai.core.context_builder import ContextoMontado

    monkeypatch.setattr(s, "OLLAMA_ENABLED", True)

    async def fake_montar_contexto(db, **kw):
        return ContextoMontado()

    async def fake_registrar(db, **kw):
        return "log-fake"

    async def fake_chat(messages, **kw):
        return GatewayResponse(
            texto="Minuta fictícia de petição, sem promessas.",
            modelo="modelo-fake", provedor="ollama",
            task_type=kw.get("task_type", ""), input_tokens=10, output_tokens=20,
        )

    monkeypatch.setattr(context_builder, "montar_contexto", fake_montar_contexto)
    monkeypatch.setattr(audit_logger, "registrar", fake_registrar)
    monkeypatch.setattr(ai_gateway, "chat", fake_chat)
    return s


@pytest.fixture
def critica_spy(monkeypatch):
    """Espião de criticar_peca/anexar_critica_ao_log no módulo adversarial."""
    from app.services.ai import adversarial
    calls = {"criticar": [], "anexar": []}

    async def fake_criticar(db, texto_peca, contexto_caso=None,
                            task_type_origem=None, provedor_origem=None,
                            case_id=None, entidades=None,
                            modo_sanitizacao=None):
        calls["criticar"].append({
            "texto_peca": texto_peca, "task_type_origem": task_type_origem,
            "provedor_origem": provedor_origem,
            "case_id": case_id, "entidades": entidades,
            "modo_sanitizacao": modo_sanitizacao,
        })
        return adversarial.CriticaAdversarial(
            disponivel=True, relatorio=RELATORIO_OK, nota_robustez=72,
            provedor="anthropic", modelo="claude-fake",
            provedor_origem=provedor_origem, task_type_origem=task_type_origem,
            provider_diverso=True,
        )

    async def fake_anexar(db, log_id, critica):
        calls["anexar"].append(log_id)
        return True

    monkeypatch.setattr(adversarial, "criticar_peca", fake_criticar)
    monkeypatch.setattr(adversarial, "anexar_critica_ao_log", fake_anexar)
    return calls


def _user(role: str = "advogado"):
    return SimpleNamespace(id="usuario-fake-1", role=role)


class TestOrchestratorDuasIAs:
    async def test_flag_desligada_nao_dispara_critica(self, nucleo_mocks, critica_spy):
        from app.services.ai.core.orchestrator import orchestrator
        r = await orchestrator.run(
            db=None, user=_user(), task_type="legal_draft",
            mensagem="Redigir petição inicial fictícia de cobrança.",
        )
        assert r["critica_adversarial"] is None
        assert critica_spy["criticar"] == []

    async def test_flag_ligada_task_elegivel_dispara_e_anexa(
        self, nucleo_mocks, critica_spy, monkeypatch,
    ):
        from app.services.ai.core.orchestrator import orchestrator
        monkeypatch.setattr(nucleo_mocks, "DUAS_IAS_ENABLED", True)
        r = await orchestrator.run(
            db=None, user=_user(), task_type="legal_draft",
            mensagem="Redigir petição inicial fictícia de cobrança.",
        )
        assert len(critica_spy["criticar"]) == 1
        chamada = critica_spy["criticar"][0]
        assert chamada["task_type_origem"] == "elaboracao_peca"
        assert chamada["provedor_origem"] == "ollama"
        # A crítica recebe o conteúdo JÁ validado (pós gate de citações da peça).
        assert r["conteudo"].endswith(chamada["texto_peca"]) or \
            chamada["texto_peca"] == r["conteudo"]
        assert critica_spy["anexar"] == ["log-fake"]
        assert r["critica_adversarial"]["disponivel"] is True
        assert r["critica_adversarial"]["nota_robustez"] == 72
        # HITL preservado: peça continua rascunho com revisão obrigatória.
        assert r["is_rascunho"] is True

    async def test_area_sigilosa_propaga_piso_local_para_a_critica(
        self, nucleo_mocks, critica_spy, monkeypatch,
    ):
        """O orquestrador resolvia o piso de sigilo para a GERAÇÃO da peça e não
        o repassava à CRÍTICA. Como `critica_adversarial` é
        EXTERNO_PSEUDONIMIZADO na política e a crítica PREFERE provider externo
        (diversidade), a peça gerada em local saía do VPS na etapa seguinte."""
        from app.services.ai.core.orchestrator import orchestrator
        from app.services.ai.sanitization_policy import ModoSanitizacao
        monkeypatch.setattr(nucleo_mocks, "DUAS_IAS_ENABLED", True)
        r = await orchestrator.run(
            db=None, user=_user(), task_type="legal_draft",
            domain="crimes_sexuais",  # área de SIGILO REFORÇADO
            mensagem="Redigir peça fictícia para teste de sigilo.",
        )
        assert r["conteudo"]
        chamada = critica_spy["criticar"][0]
        assert chamada["modo_sanitizacao"] == ModoSanitizacao.LOCAL_COMPLETO

    async def test_area_normal_nao_impoe_piso_local_a_critica(
        self, nucleo_mocks, critica_spy, monkeypatch,
    ):
        """Regressão inversa: fora de área sensível, a crítica segue livre para
        usar provider externo pseudonimizado (diversidade de modelo preservada)."""
        from app.services.ai.core.orchestrator import orchestrator
        from app.services.ai.sanitization_policy import ModoSanitizacao
        monkeypatch.setattr(nucleo_mocks, "DUAS_IAS_ENABLED", True)
        await orchestrator.run(
            db=None, user=_user(), task_type="legal_draft", domain="civel",
            mensagem="Redigir petição inicial fictícia de cobrança.",
        )
        chamada = critica_spy["criticar"][0]
        assert chamada["modo_sanitizacao"] != ModoSanitizacao.LOCAL_COMPLETO

    async def test_flag_ligada_task_inelegivel_nao_dispara(
        self, nucleo_mocks, critica_spy, monkeypatch,
    ):
        from app.services.ai.core.orchestrator import orchestrator
        monkeypatch.setattr(nucleo_mocks, "DUAS_IAS_ENABLED", True)
        r = await orchestrator.run(
            db=None, user=_user(), task_type="chat",
            mensagem="Resumo rápido de um caso fictício qualquer.",
        )
        assert r["critica_adversarial"] is None
        assert critica_spy["criticar"] == []

    async def test_falha_inesperada_da_critica_nao_bloqueia_peca(
        self, nucleo_mocks, monkeypatch,
    ):
        from app.services.ai import adversarial
        from app.services.ai.core.orchestrator import orchestrator
        monkeypatch.setattr(nucleo_mocks, "DUAS_IAS_ENABLED", True)

        async def explode(*a, **kw):
            raise RuntimeError("falha inesperada no pipeline de crítica")

        monkeypatch.setattr(adversarial, "criticar_peca", explode)
        r = await orchestrator.run(
            db=None, user=_user(), task_type="legal_draft",
            mensagem="Redigir petição inicial fictícia de cobrança.",
        )
        # Peça entregue normalmente, crítica marcada como indisponível.
        assert r["conteudo"]
        assert r["critica_adversarial"]["disponivel"] is False
        assert r["critica_adversarial"]["aviso"] == adversarial.AVISO_INDISPONIVEL


# ══════════════════════════════════════════════════════════════════════════════
# 6. Endpoint POST /ia/critica-adversarial (JWT + rate limit + AILog)
# ══════════════════════════════════════════════════════════════════════════════

class _EndpointDB:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


class TestEndpointCriticaAdversarial:
    def test_rota_registrada_com_rate_limit(self):
        from app.routers.ia_adversarial import router
        rotas = {r.path: r for r in router.routes}
        assert "/ia/critica-adversarial" in rotas
        rota = rotas["/ia/critica-adversarial"]
        assert "POST" in rota.methods
        assert rota.dependencies  # rate_limit("critica-adversarial", 10)

    def test_endpoint_exige_jwt(self):
        from app.core.security import get_current_user
        from app.routers.ia_adversarial import critica_adversarial_endpoint
        params = inspect.signature(critica_adversarial_endpoint).parameters
        assert params["cu"].default.dependency is get_current_user

    async def test_endpoint_executa_critica_e_grava_ailog(self, s, monkeypatch):
        from app.services import ai_gateway, citation_gate
        from app.routers.ia_adversarial import (
            CriticaAdversarialRequest, critica_adversarial_endpoint,
        )
        monkeypatch.setattr(ai_gateway, "chat", _fake_chat({}, provedor="anthropic"))

        async def fake_validar(db, texto, **kw):
            return citation_gate.RelatorioCitacoes(politica="marcar")

        monkeypatch.setattr(citation_gate, "validar_citacoes", fake_validar)
        db = _EndpointDB()
        c = await critica_adversarial_endpoint(
            CriticaAdversarialRequest(texto_peca=TEXTO_PECA, provedor_origem="ollama"),
            db=db, cu=SimpleNamespace(id="user-1"),
        )
        assert c.disponivel is True and c.provider_diverso is True
        # AILog gravado (trilha LGPD/OAB).
        assert db.commits == 1 and len(db.added) == 1
        log = db.added[0]
        assert log.user_id == "user-1"
        assert "[CRITICA_ADVERSARIAL sob demanda]" in log.prompt_sanitizado
        assert log.resposta == RELATORIO_OK

    async def test_endpoint_falha_de_provider_devolve_indisponivel(self, s, monkeypatch):
        from app.services import ai_gateway
        from app.routers.ia_adversarial import (
            CriticaAdversarialRequest, critica_adversarial_endpoint,
        )
        monkeypatch.setattr(ai_gateway, "chat", _fake_chat({}, falhar=True))
        db = _EndpointDB()
        c = await critica_adversarial_endpoint(
            CriticaAdversarialRequest(texto_peca=TEXTO_PECA),
            db=db, cu=SimpleNamespace(id="user-1"),
        )
        assert c.disponivel is False
        assert db.added == [] and db.commits == 0  # nada de log sem chamada de IA


def test_config_padrao_critica_analise_e_estrategia(monkeypatch):
    """Qualidade jurídica: análise e estratégia entram no segundo olhar
    adversarial por padrão, além de elaboração/auditoria de peça."""
    from app.core.config import Settings
    s = Settings(_env_file=None)
    tipos = {x.strip() for x in s.DUAS_IAS_TASK_TYPES.split(",") if x.strip()}
    assert {"elaboracao_peca", "auditoria_peca", "analise_juridica", "estrategia"} <= tipos
