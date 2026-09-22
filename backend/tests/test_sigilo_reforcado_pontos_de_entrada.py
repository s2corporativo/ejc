"""Achado CRÍTICO do `security-auditor` sobre a Issue #1194 (18/08): a redução
do piso LOCAL_COMPLETO a crimes sexuais/menores só chegava a `orchestrator.py`/
`agent/loop.py` — mas existem outros caminhos de IA vinculados a um caso que
nunca consultavam `Case.sigilo_reforcado` nem repassavam `modo_sanitizacao` ao
gateway: `analise_estrategica.analisar_caso` (botão "Análise estratégica com
IA" + hook automático de upload), o módulo legado `ai_service.py` (5 funções
via `_gateway_text`), `ia_defensiva_service.executar_ia_defensiva`,
`validador_juridico_service.validar_rascunho_juridico`,
`routers/ai_tools.py::executar_ia`, e a tool do agente
`agent/tools/escrita.py::gerar_minuta_peca` (defesa em profundidade — hoje
inalcançável porque `loop.py` já aborta antes, mas dependia só disso).

Cada teste prova que, com `Case.sigilo_reforcado=True`, a chamada ao gateway
recebe `modo_sanitizacao=ModoSanitizacao.LOCAL_COMPLETO` — e que sem a flag
(ou sem `case_id`), nada muda (regressão inversa). Dados fictícios; nenhum
teste toca rede ou banco real — `db` é um fake mínimo que só sabe responder à
consulta `SELECT sigilo_reforcado FROM cases WHERE id = :cid` (mesmo padrão de
`_escopo_cliente_do_caso`).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.ai.sanitization_policy import ModoSanitizacao

pytestmark = pytest.mark.anyio


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row

    def scalar_one_or_none(self):
        return self._row[0] if self._row else None


class _FakeDB:
    """`execute()` responde SÓ à consulta de `sigilo_reforcado`; `add`/`commit`
    são no-ops. Suficiente para exercitar o lookup sem Postgres real."""

    def __init__(self, sigilo_reforcado: bool | None):
        self._sigilo = sigilo_reforcado
        self.commits = 0
        self.added = []

    async def execute(self, *_a, **_kw):
        if self._sigilo is None:
            return _FakeResult(None)
        return _FakeResult((self._sigilo,))

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


# ── 1. analise_estrategica.analisar_caso ─────────────────────────────────────

class TestAnaliseEstrategica:
    async def test_caso_sigiloso_forca_local_completo(self, monkeypatch):
        from app.services import analise_estrategica

        capturado = {}

        async def fake_chat(**kw):
            capturado["modo_sanitizacao"] = kw.get("modo_sanitizacao")
            return SimpleNamespace(texto='{"ramo":"Penal"}')

        monkeypatch.setattr("app.services.ai_gateway.chat", fake_chat)

        await analise_estrategica.analisar_caso(
            titulo="Caso fictício", fatos="Fatos fictícios de teste.",
            case_id="caso-sigiloso-1", db=_FakeDB(True),
        )
        assert capturado["modo_sanitizacao"] == ModoSanitizacao.LOCAL_COMPLETO

    async def test_caso_normal_nao_forca_nada(self, monkeypatch):
        from app.services import analise_estrategica

        capturado = {}

        async def fake_chat(**kw):
            capturado["modo_sanitizacao"] = kw.get("modo_sanitizacao")
            return SimpleNamespace(texto='{"ramo":"Civel"}')

        monkeypatch.setattr("app.services.ai_gateway.chat", fake_chat)

        await analise_estrategica.analisar_caso(
            titulo="Caso fictício", fatos="Fatos fictícios de teste.",
            case_id="caso-normal-1", db=_FakeDB(False),
        )
        assert capturado["modo_sanitizacao"] is None


# ── 2. ai_service._modo_sigilo_caso + auditar_peca (representante das 5) ────

class TestAiServiceLegado:
    async def test_modo_sigilo_caso_true(self):
        from app.services.ai_service import _modo_sigilo_caso

        modo = await _modo_sigilo_caso(_FakeDB(True), "caso-1")
        assert modo == ModoSanitizacao.LOCAL_COMPLETO

    async def test_modo_sigilo_caso_false(self):
        from app.services.ai_service import _modo_sigilo_caso

        assert await _modo_sigilo_caso(_FakeDB(False), "caso-1") is None

    async def test_modo_sigilo_caso_sem_case_id(self):
        from app.services.ai_service import _modo_sigilo_caso

        assert await _modo_sigilo_caso(_FakeDB(True), None) is None

    async def test_auditar_peca_caso_sigiloso_forca_local_completo(self, monkeypatch):
        from app.services import ai_service

        capturado = {}

        async def fake_gateway_text(*a, **kw):
            capturado["modo_sanitizacao"] = kw.get("modo_sanitizacao")
            return "auditoria ok", SimpleNamespace(
                modelo="m", provedor="p", input_tokens=1, output_tokens=1,
            )

        monkeypatch.setattr(ai_service, "_gateway_text", fake_gateway_text)

        await ai_service.auditar_peca(
            _FakeDB(True), "user-1", "Conteúdo fictício da peça.", "inicial",
            case_id="caso-sigiloso-2",
        )
        assert capturado["modo_sanitizacao"] == ModoSanitizacao.LOCAL_COMPLETO

    async def test_auditar_peca_caso_normal_nao_forca_nada(self, monkeypatch):
        from app.services import ai_service

        capturado = {}

        async def fake_gateway_text(*a, **kw):
            capturado["modo_sanitizacao"] = kw.get("modo_sanitizacao")
            return "auditoria ok", SimpleNamespace(
                modelo="m", provedor="p", input_tokens=1, output_tokens=1,
            )

        monkeypatch.setattr(ai_service, "_gateway_text", fake_gateway_text)

        await ai_service.auditar_peca(
            _FakeDB(False), "user-1", "Conteúdo fictício da peça.", "inicial",
            case_id="caso-normal-2",
        )
        assert capturado["modo_sanitizacao"] is None


# ── 3. ia_defensiva_service.executar_ia_defensiva ────────────────────────────

class TestIaDefensiva:
    async def _rodar(self, monkeypatch, sigilo):
        from app.services.ia_defensiva_service import (
            IaDefensivaInput, executar_ia_defensiva,
        )
        import app.services.ia_defensiva_service as mod

        capturado = {}

        async def fake_chat(**kw):
            capturado["modo_sanitizacao"] = kw.get("modo_sanitizacao")
            return SimpleNamespace(
                texto="Análise fictícia.", modelo="m", provedor="p",
                input_tokens=1, output_tokens=1, fallback_ativado=False,
            )

        monkeypatch.setattr(mod, "chat", fake_chat)

        payload = IaDefensivaInput(
            etapa="analise_inicial",
            peticao_inicial="Petição inicial fictícia com fatos suficientes para análise.",
            case_id="caso-defensiva-1" if sigilo is not None else None,
        )
        await executar_ia_defensiva(payload, _FakeDB(sigilo), "user-1")
        return capturado

    async def test_caso_sigiloso_forca_local_completo(self, monkeypatch):
        capturado = await self._rodar(monkeypatch, True)
        assert capturado["modo_sanitizacao"] == ModoSanitizacao.LOCAL_COMPLETO

    async def test_caso_normal_nao_forca_nada(self, monkeypatch):
        capturado = await self._rodar(monkeypatch, False)
        assert capturado["modo_sanitizacao"] is None


# ── 4. validador_juridico_service.validar_rascunho_juridico ─────────────────

class TestValidadorJuridico:
    async def _rodar(self, monkeypatch, sigilo):
        from app.services.validador_juridico_service import (
            ValidacaoInput, validar_rascunho_juridico,
        )
        import app.services.validador_juridico_service as mod

        capturado = {}

        async def fake_chat(**kw):
            capturado["modo_sanitizacao"] = kw.get("modo_sanitizacao")
            return SimpleNamespace(
                texto='{"nota":8,"observacoes":[]}', modelo="m", provedor="p",
                input_tokens=1, output_tokens=1,
            )

        async def fake_rag(*a, **kw):
            return []

        monkeypatch.setattr(mod, "chat", fake_chat)
        monkeypatch.setattr(mod, "buscar_contexto_rag", fake_rag)

        payload = ValidacaoInput(
            rascunho=(
                "Rascunho fictício de peça jurídica com conteúdo suficiente "
                "para validação técnica — precisa passar dos cem caracteres "
                "mínimos exigidos pela função antes de chegar ao gateway."
            ),
            case_id="caso-validador-1",
        )
        try:
            await validar_rascunho_juridico(payload, _FakeDB(sigilo), "user-1", commit=False)
        except Exception:
            pass  # persistência de LegalDoc não é o alvo deste teste
        return capturado

    async def test_caso_sigiloso_forca_local_completo(self, monkeypatch):
        capturado = await self._rodar(monkeypatch, True)
        assert capturado.get("modo_sanitizacao") == ModoSanitizacao.LOCAL_COMPLETO

    async def test_caso_normal_nao_forca_nada(self, monkeypatch):
        capturado = await self._rodar(monkeypatch, False)
        assert capturado.get("modo_sanitizacao") is None


# ── 5. routers/ai_tools.py::executar_ia ──────────────────────────────────────

class TestAiToolsRouter:
    async def _rodar(self, monkeypatch, sigilo):
        from app.models.user import User, UserRole
        from app.services.system_prompts import TarefaIA
        import app.routers.ai_tools as ai_tools_mod
        import app.core.ownership as ownership_mod

        capturado = {}

        async def fake_acesso(db, cu, case_id):
            return SimpleNamespace(id=case_id, sigilo_reforcado=sigilo)

        async def fake_executar_tarefa_ia(**kw):
            capturado["modo_sanitizacao"] = kw.get("modo_sanitizacao")
            return {
                "conteudo": "ok", "modelo": "m", "provider": "p", "tarefa": "x",
                "tokens_usados": 1, "custo_estimado_brl": 0.0,
            }

        async def fake_escopo(db, case_id):
            return None

        async def fake_entidades(db, case_id):
            return {}

        monkeypatch.setattr(ownership_mod, "verificar_acesso_caso", fake_acesso)
        monkeypatch.setattr(ai_tools_mod, "executar_tarefa_ia", fake_executar_tarefa_ia)
        monkeypatch.setattr(ai_tools_mod, "_ai_enabled", lambda: True)
        monkeypatch.setattr(
            ai_tools_mod, "sanitizar_ou_abortar", lambda msg: (msg, False),
        )
        monkeypatch.setattr(
            "app.services.ai_service._escopo_cliente_do_caso", fake_escopo,
        )
        monkeypatch.setattr(
            "app.services.ai.entidades_caso.entidades_do_caso", fake_entidades,
        )

        req = ai_tools_mod.AiRequest(
            tarefa=TarefaIA.ANALISE_CASO,
            mensagem="Mensagem fictícia com mais de cinco caracteres.",
            case_id="caso-ai-tools-1",
        )
        cu = User(id="u-adv-1", role=UserRole.advogado)
        await ai_tools_mod.executar_ia(req, _FakeDB(sigilo), cu)
        return capturado

    async def test_caso_sigiloso_forca_local_completo(self, monkeypatch):
        capturado = await self._rodar(monkeypatch, True)
        assert capturado["modo_sanitizacao"] == ModoSanitizacao.LOCAL_COMPLETO

    async def test_caso_normal_nao_forca_nada(self, monkeypatch):
        capturado = await self._rodar(monkeypatch, False)
        assert capturado["modo_sanitizacao"] is None


# ── 6. agent/tools/escrita.py::gerar_minuta_peca (defesa em profundidade) ───

class TestAgentToolEscrita:
    async def _rodar(self, monkeypatch, sigilo):
        from app.services.ai.agent.tools import escrita
        from app.services.ai.agent.tools.context import AgentContext

        capturado = {}

        async def fake_acesso(db, cu, case_id):
            return SimpleNamespace(id=case_id, sigilo_reforcado=sigilo)

        async def fake_executar_tarefa_ia(*a, **kw):
            capturado["modo_sanitizacao"] = kw.get("modo_sanitizacao")
            return {"conteudo": "minuta ficticia"}

        async def fake_entidades(db, case_id):
            return {}

        # `escrita.py` importa verificar_acesso_caso e entidades_do_caso no
        # ESCOPO da função (não no módulo) — o patch precisa mirar o módulo de
        # ORIGEM, mas verificar_acesso_caso é importado no TOPO do arquivo
        # (`from app.core.ownership import verificar_acesso_caso`), então o
        # nome já está vinculado em `escrita` e o patch precisa ser lá.
        monkeypatch.setattr(escrita, "verificar_acesso_caso", fake_acesso)
        monkeypatch.setattr(
            "app.services.ai_gateway.executar_tarefa_ia", fake_executar_tarefa_ia,
        )
        monkeypatch.setattr(
            "app.services.ai.entidades_caso.entidades_do_caso", fake_entidades,
        )

        ctx = AgentContext(
            db=_FakeDB(sigilo), user=SimpleNamespace(id="u-adv-1"),
            case_id="caso-escrita-1", client_id="cli-1", role="advogado",
            area="civel",  # área NORMAL — só a flag do caso deveria proteger
        )
        await escrita.gerar_minuta_peca(
            {"tipo": "contestacao", "instrucoes": "Instruções fictícias."}, ctx,
        )
        return capturado

    async def test_caso_sigiloso_forca_local_completo_mesmo_com_area_normal(
            self, monkeypatch):
        capturado = await self._rodar(monkeypatch, True)
        assert capturado["modo_sanitizacao"] == ModoSanitizacao.LOCAL_COMPLETO

    async def test_caso_normal_usa_apenas_o_modo_da_area(self, monkeypatch):
        capturado = await self._rodar(monkeypatch, False)
        # área "civel" é EXTERNO_PSEUDONIMIZADO — não None, mas também não LOCAL.
        assert capturado["modo_sanitizacao"] != ModoSanitizacao.LOCAL_COMPLETO


# ── 7. Crítica adversarial (Modo Duas IAs) ───────────────────────────────────
# O caminho que a auditoria acima chamou de "outros caminhos" e não cobriu.
# É o mais grave dos que restavam: a crítica recebe a PEÇA INTEIRA mais o
# CONTEXTO DO CASO (dossiê/OCR/RAG) e, por design, PREFERE provider EXTERNO
# para ter diversidade de modelo. Como o task_type `critica_adversarial` é
# EXTERNO_PSEUDONIMIZADO na política, num caso `sigilo_reforcado=True` a
# GERAÇÃO da peça rodava local (correto) e a CRÍTICA saía do VPS logo depois,
# levando o mesmo conteúdo — anulando a proteção na etapa seguinte.

class TestCriticaAdversarial:
    """`adversarial.criticar_peca` — piso de sigilo do CASO e do CHAMADOR."""

    @pytest.fixture
    def gateway_ok(self, monkeypatch):
        """Providers externos e Ollama elegíveis; captura os kwargs do gateway."""
        from app.core.config import get_settings
        from app.services.ai_gateway import GatewayResponse
        st = get_settings()
        monkeypatch.setattr(st, "ANTHROPIC_ENABLED", True)
        monkeypatch.setattr(st, "ANTHROPIC_API_KEY", "sk-ant-fake-para-testes")
        monkeypatch.setattr(st, "MARITACA_ENABLED", True)
        monkeypatch.setattr(st, "MARITACA_API_KEY", "mk-fake-para-testes")
        monkeypatch.setattr(st, "GROQ_API_KEY", "gsk-fake-para-testes")
        monkeypatch.setattr(st, "OLLAMA_ENABLED", True)
        monkeypatch.setattr(st, "AI_EXTERNAL_PROVIDERS_ALLOWED", True)
        monkeypatch.setattr(st, "AI_PROVIDER", "auto")
        monkeypatch.setattr(st, "AI_PROVIDER_PRIORITY", "groq,maritaca,ollama,anthropic")
        monkeypatch.setattr(st, "ANTHROPIC_AUTO_ROUTING_ENABLED", False)
        capturado: dict = {}

        async def fake_chat(messages, **kw):
            capturado.update(kw)
            return GatewayResponse(
                texto="## 6. NOTA DE ROBUSTEZ\nNOTA DE ROBUSTEZ: 70",
                modelo="m-fake", provedor=kw.get("provider_override") or "anthropic",
                task_type=kw.get("task_type", ""), input_tokens=1, output_tokens=1,
            )

        monkeypatch.setattr("app.services.ai_gateway.chat", fake_chat)
        # Gate de citações da própria crítica: irrelevante aqui, e sem ele o
        # `_FakeDB` receberia consultas que não sabe responder.
        async def sem_gate(*_a, **_kw):
            raise RuntimeError("gate desligado no teste")
        monkeypatch.setattr(
            "app.services.citation_gate.validar_citacoes", sem_gate,
        )
        return capturado

    async def test_caso_sigiloso_forca_local_completo_no_gateway(
            self, gateway_ok, monkeypatch):
        from app.services.ai import adversarial
        # Entidades do caso: fail-safe, mas evita consulta que o fake não sabe.
        async def fake_entidades(db, case_id):
            return {}
        monkeypatch.setattr(
            "app.services.ai.entidades_caso.entidades_do_caso", fake_entidades,
        )

        c = await adversarial.criticar_peca(
            _FakeDB(True), texto_peca="Peça fictícia para crítica.",
            contexto_caso="Contexto fictício do caso.",
            task_type_origem="elaboracao_peca", provedor_origem="ollama",
            case_id="caso-sigiloso-critica",
        )
        assert c.disponivel is True
        assert gateway_ok["modo_sanitizacao"] == ModoSanitizacao.LOCAL_COMPLETO
        # E o provider forçado por DIVERSIDADE não pode ser externo: o sigilo
        # vence a diversidade (senão o override externo é o próprio vazamento).
        assert gateway_ok["provider_override"] not in ("anthropic", "groq", "maritaca")

    async def test_caso_normal_mantem_diversidade_externa(
            self, gateway_ok, monkeypatch):
        """Regressão inversa: sem a flag, nada muda (crítica segue preferindo
        provider externo diverso e o modo é o da política do task_type)."""
        from app.services.ai import adversarial
        async def fake_entidades(db, case_id):
            return {}
        monkeypatch.setattr(
            "app.services.ai.entidades_caso.entidades_do_caso", fake_entidades,
        )

        c = await adversarial.criticar_peca(
            _FakeDB(False), texto_peca="Peça fictícia para crítica.",
            task_type_origem="elaboracao_peca", provedor_origem="ollama",
            case_id="caso-normal-critica",
        )
        assert c.disponivel is True
        assert gateway_ok["modo_sanitizacao"] != ModoSanitizacao.LOCAL_COMPLETO
        assert gateway_ok["provider_override"] == "maritaca"

    async def test_modo_do_chamador_eleva_o_piso_sem_case_id(
            self, gateway_ok):
        """O orquestrador resolve o piso por ÁREA sensível e o informa — sem
        `case_id` no banco, ele sozinho já tem de bastar."""
        from app.services.ai import adversarial

        c = await adversarial.criticar_peca(
            None, texto_peca="Peça fictícia para crítica.",
            provedor_origem="ollama",
            modo_sanitizacao=ModoSanitizacao.LOCAL_COMPLETO,
        )
        assert c.disponivel is True
        assert gateway_ok["modo_sanitizacao"] == ModoSanitizacao.LOCAL_COMPLETO
        assert gateway_ok["provider_override"] not in ("anthropic", "groq", "maritaca")

    async def test_sigilo_sem_ia_local_pula_a_critica_em_vez_de_vazar(
            self, gateway_ok, monkeypatch):
        """Fail-closed explícito: sigilo reforçado + nenhum provider LOCAL
        elegível → crítica NÃO executada, com aviso próprio. Jamais externo."""
        from app.core.config import get_settings
        from app.services.ai import adversarial
        monkeypatch.setattr(get_settings(), "OLLAMA_ENABLED", False)
        async def fake_entidades(db, case_id):
            return {}
        monkeypatch.setattr(
            "app.services.ai.entidades_caso.entidades_do_caso", fake_entidades,
        )

        c = await adversarial.criticar_peca(
            _FakeDB(True), texto_peca="Peça fictícia para crítica.",
            contexto_caso="Contexto fictício do caso.",
            task_type_origem="elaboracao_peca", provedor_origem="ollama",
            case_id="caso-sigiloso-sem-local",
        )
        assert c.disponivel is False
        assert c.aviso == adversarial.AVISO_BLOQUEIO_SIGILO
        # Prova NEGATIVA: o gateway não foi chamado — nada saiu do VPS.
        assert gateway_ok == {}

    async def test_falha_ao_ler_o_sigilo_pula_a_critica(self, gateway_ok):
        """Sigilo INDETERMINADO (erro de banco) não vira "pode ir ao externo"."""
        from app.services.ai import adversarial

        class _DBQuebrado:
            async def execute(self, *_a, **_kw):
                raise RuntimeError("banco indisponível (simulado)")

        c = await adversarial.criticar_peca(
            _DBQuebrado(), texto_peca="Peça fictícia para crítica.",
            task_type_origem="elaboracao_peca", case_id="caso-indeterminado",
        )
        assert c.disponivel is False
        assert gateway_ok == {}
