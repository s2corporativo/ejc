"""Etapa 13 — Testes do Núcleo Único de IA (policy, gateway, providers, core).

Todos os dados são FICTÍCIOS (CPF sintético 123.456.789-09, nomes inventados).
Nenhum teste toca rede: providers são mockados; settings via monkeypatch nos
ATRIBUTOS da instância cacheada de get_settings() (lru_cache).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.config import get_settings

CPF_FAKE = "123.456.789-09"
CNPJ_FAKE = "12.345.678/0001-99"
EMAIL_FAKE = "maria.exemplo@teste-ficticio.com.br"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def s(monkeypatch):
    """Settings cacheada com baseline determinística p/ os testes do núcleo:
    Anthropic habilitado c/ chave fake, Groq c/ chave fake, Ollama desligado."""
    st = get_settings()
    monkeypatch.setattr(st, "ANTHROPIC_ENABLED", True)
    monkeypatch.setattr(st, "ANTHROPIC_API_KEY", "sk-ant-fake-para-testes")
    monkeypatch.setattr(st, "GROQ_API_KEY", "gsk-fake-para-testes")
    monkeypatch.setattr(st, "OLLAMA_ENABLED", False)
    monkeypatch.setattr(st, "AI_EXTERNAL_PROVIDERS_ALLOWED", True)
    monkeypatch.setattr(st, "AI_REQUIRE_SANITIZATION_FOR_EXTERNAL", True)
    monkeypatch.setattr(st, "AI_PROVIDER_PRIORITY", "ollama,anthropic,groq")
    monkeypatch.setattr(st, "AI_PROVIDER", "auto")
    monkeypatch.setattr(st, "AI_REQUIRE_HITL", True)
    return st


def _providers(decisao) -> list[str]:
    return [p for p, _ in decisao.provider_chain]


# ══════════════════════════════════════════════════════════════════════════════
# 1. AIProviderPolicy
# ══════════════════════════════════════════════════════════════════════════════

class TestAIProviderPolicy:
    def test_anthropic_elegivel_com_chave_e_externos_permitidos(self, s):
        from app.services.ai.provider_policy import AIProviderPolicy
        d = AIProviderPolicy().avaliar("texto limpo sem dados pessoais", "analise_juridica")
        assert d.permitido is True
        assert "anthropic" in _providers(d)

    def test_anthropic_inelegivel_sem_chave(self, s, monkeypatch):
        from app.services.ai.provider_policy import AIProviderPolicy
        monkeypatch.setattr(s, "ANTHROPIC_API_KEY", "")
        d = AIProviderPolicy().avaliar("texto limpo", "analise_juridica")
        assert "anthropic" not in _providers(d)

    def test_externos_inelegiveis_com_flag_desligada(self, s, monkeypatch):
        from app.services.ai.provider_policy import AIProviderPolicy
        monkeypatch.setattr(s, "AI_EXTERNAL_PROVIDERS_ALLOWED", False)
        d = AIProviderPolicy().avaliar("texto limpo", "analise_juridica")
        assert "anthropic" not in _providers(d)
        assert "groq" not in _providers(d)
        # Sem Ollama local, nada resta → bloqueado com motivo seguro.
        assert d.permitido is False
        assert d.bloqueio_motivo

    def test_pii_residual_remove_externos_e_bloqueia_sem_local(self, s, monkeypatch):
        # Simula PII residual pós-sanitização (segunda barreira acusando).
        from app.services.ai import provider_policy as pp
        monkeypatch.setattr(pp, "validar_sem_pii", lambda t: ["CPF"])
        texto = f"cliente fictício com CPF {CPF_FAKE} no caso"
        d = pp.AIProviderPolicy().avaliar(texto, "analise_juridica")
        assert d.permitido is False
        assert d.provider_chain == []
        assert "PII residual" in d.motivo
        # Motivo de bloqueio SEGURO: nunca ecoa o texto/valores de PII.
        assert CPF_FAKE not in (d.bloqueio_motivo or "")
        assert texto not in (d.bloqueio_motivo or "")

    def test_pii_residual_mantem_provider_local(self, s, monkeypatch):
        from app.services.ai import provider_policy as pp
        monkeypatch.setattr(s, "OLLAMA_ENABLED", True)
        monkeypatch.setattr(pp, "validar_sem_pii", lambda t: ["CPF"])
        d = pp.AIProviderPolicy().avaliar(f"texto com {CPF_FAKE}", "analise_juridica")
        assert d.permitido is True
        assert _providers(d) == ["ollama"]  # externos saíram da cadeia (LGPD)

    def test_caminho_nao_sanitizado_com_texto_limpo_permite(self, s):
        from app.services.ai.provider_policy import AIProviderPolicy
        d = AIProviderPolicy().avaliar(
            "consulta teórica sobre prescrição sem dados pessoais",
            "analise_juridica",
            ja_sanitizado=False,
        )
        assert d.permitido is True
        assert d.sanitizar_antes is True  # destino externo exige sanitização

    def test_tarefa_complexa_prioriza_anthropic(self, s, monkeypatch):
        from app.services.ai.provider_policy import AIProviderPolicy
        monkeypatch.setattr(s, "OLLAMA_ENABLED", True)
        d = AIProviderPolicy().avaliar("texto limpo", "analise_juridica")
        assert _providers(d)[0] == "anthropic"

    def test_tarefa_economica_prioriza_local_barato(self, s, monkeypatch):
        from app.services.ai.provider_policy import AIProviderPolicy
        monkeypatch.setattr(s, "OLLAMA_ENABLED", True)
        d = AIProviderPolicy().avaliar("texto limpo", "resumo")
        assert _providers(d)[0] in ("ollama", "groq")
        assert _providers(d)[0] == "ollama"  # prioridade ollama,anthropic,groq
        # Sem Ollama, cai no Groq (custo ~zero) antes do Anthropic.
        monkeypatch.setattr(s, "OLLAMA_ENABLED", False)
        d2 = AIProviderPolicy().avaliar("texto limpo", "resumo")
        assert _providers(d2)[0] == "groq"


# ══════════════════════════════════════════════════════════════════════════════
# 2. Barreira do gateway (_sanitizar_messages_externo + chat bloqueado)
# ══════════════════════════════════════════════════════════════════════════════

class TestGatewayBarreiraLGPD:
    def test_sanitizar_messages_externo_mascara_pii(self, s):
        # Sanitização reativada (LGPD art. 33/46): a barreira final mascara
        # CPF/CNPJ/e-mail antes de qualquer provedor externo e não deixa
        # residual (nenhuma PII estrutural segue em claro).
        from app.services.ai_gateway import _sanitizar_messages_externo
        messages = [
            {"role": "system", "content": "Você é um assistente jurídico."},
            {"role": "user", "content": f"CPF {CPF_FAKE}, CNPJ {CNPJ_FAKE}, e-mail {EMAIL_FAKE}"},
        ]
        limpos, residual = _sanitizar_messages_externo(messages)
        assert residual == []
        conteudo = " ".join(m["content"] for m in limpos)
        assert CPF_FAKE not in conteudo and CNPJ_FAKE not in conteudo and EMAIL_FAKE not in conteudo
        assert "[CPF]" in conteudo and "[CNPJ]" in conteudo and "[EMAIL]" in conteudo

    async def test_chat_bloqueia_cadeia_so_externa_com_pii_residual(self, s, monkeypatch):
        from app.services import ai_gateway, sanitizer
        from app.services.ai import pseudonymizer

        # Segunda barreira acusa residual mesmo após sanitizar/pseudonimizar
        # (simulado). "resumo" agora é EXTERNO_PSEUDONIMIZADO (2026-07-06), então a
        # barreira final usa `validar_sem_pii_pseudonimizado`; forçamos residual nela
        # (e no sanitizer, defesa em profundidade) para exercitar o bloqueio.
        monkeypatch.setattr(sanitizer, "validar_sem_pii", lambda t: ["CPF"])
        monkeypatch.setattr(pseudonymizer, "validar_sem_pii_pseudonimizado", lambda t: ["CPF"])

        chamadas: list = []

        async def _nao_chamar(*a, **kw):  # provider nunca deve ser tocado
            chamadas.append(a)
            raise AssertionError("provider externo foi chamado com PII residual")

        monkeypatch.setattr(ai_gateway, "_chamar_provedor", _nao_chamar)

        # Ollama OFF → cadeia de "resumo" fica só-externa (groq).
        with pytest.raises(RuntimeError) as exc:
            await ai_gateway.chat(
                [{"role": "user", "content": f"resumir caso do CPF {CPF_FAKE}"}],
                task_type="resumo",
            )
        msg = str(exc.value)
        assert "dados pessoais" in msg
        assert CPF_FAKE not in msg  # mensagem segura: não ecoa PII
        assert chamadas == []       # nenhuma chamada de rede/provider


# ══════════════════════════════════════════════════════════════════════════════
# 2b. Modos de sanitização por tarefa (pseudonimização reversível + LOCAL_COMPLETO)
# ══════════════════════════════════════════════════════════════════════════════

class TestModosSanitizacaoGateway:
    async def test_externo_pseudonimizado_reidrata_resposta(self, s, monkeypatch):
        """Tarefa EXTERNO_PSEUDONIMIZADO com provider externo: o provider recebe
        conteúdo COM marcadores e SEM PII real; a resposta devolvida está
        REIDRATADA (PII real de volta); nada de PII/mapa vai ao Langfuse."""
        from app.services import ai_gateway

        capturado: dict = {}

        async def _fake_provedor(provider, model, messages, temperature, max_tokens):
            capturado["provider"] = provider
            capturado["conteudo"] = " ".join(m.get("content", "") for m in messages)
            # O modelo devolve a resposta usando o MARCADOR (como faria de fato).
            return "Análise do CPF [CPF_1] concluída.", {
                "model": model or provider, "input_tokens": 5, "output_tokens": 9,
            }

        monkeypatch.setattr(ai_gateway, "_chamar_provedor", _fake_provedor)

        # Langfuse: captura o que seria logado (nunca pode conter PII real).
        from app.services.observability import langfuse_client as _lf
        logados: dict = {}
        monkeypatch.setattr(
            _lf, "registrar_generation",
            lambda trace, **kw: logados.update(kw),
        )

        # analise_caso → EXTERNO_PSEUDONIMIZADO; sem Ollama → anthropic externo.
        resp = await ai_gateway.chat(
            [{"role": "user", "content": f"Analise o caso do CPF {CPF_FAKE}."}],
            task_type="analise_caso",
        )
        assert capturado["provider"] in ("anthropic", "groq")
        # Provider recebeu marcador, nunca o CPF real.
        assert "[CPF_1]" in capturado["conteudo"]
        assert CPF_FAKE not in capturado["conteudo"]
        # Resposta ao chamador está REIDRATADA (CPF real de volta).
        assert CPF_FAKE in resp.texto
        assert "[CPF_1]" not in resp.texto
        # Langfuse recebeu a saída PSEUDONIMIZADA (sem PII real).
        assert CPF_FAKE not in str(logados.get("output_text", ""))
        assert CPF_FAKE not in str(logados.get("input_messages", ""))

    async def test_criminal_local_completo_bloqueia_sem_ollama(self, s, monkeypatch):
        """Auditoria de segurança (2026-07-06): `criminal` MANTIDO em LOCAL_COMPLETO
        por DEFAULT (sem override). Sem Ollama elegível, a análise criminal BLOQUEIA:
        o provider externo (Anthropic/Groq) NUNCA é chamado — nomes de vítima/
        testemunha não estruturais jamais saem da VPS. A mensagem de erro não vaza PII."""
        from app.services import ai_gateway

        chamadas: list = []

        async def _nao_chamar(*a, **kw):
            chamadas.append(a)
            raise AssertionError("provider externo chamado em tarefa LOCAL_COMPLETO")

        monkeypatch.setattr(ai_gateway, "_chamar_provedor", _nao_chamar)

        with pytest.raises(RuntimeError) as exc:
            await ai_gateway.chat(
                [{"role": "user", "content": f"Defesa criminal do CPF {CPF_FAKE}."}],
                task_type="criminal",
            )
        msg = str(exc.value)
        assert "local" in msg.lower()   # bloqueio LOCAL_COMPLETO
        assert CPF_FAKE not in msg       # mensagem segura, sem PII
        assert chamadas == []            # externo nunca tocado

    async def test_local_completo_via_override_bloqueia_sem_ollama(self, s, monkeypatch):
        """O MECANISMO LOCAL_COMPLETO permanece: se o escritório REFORÇAR criminal
        para local_completo (AI_SANITIZATION_MODE_MAP) e não houver Ollama, bloqueia
        e o provider externo NUNCA é chamado — mensagem de erro não vaza PII."""
        from app.services import ai_gateway

        monkeypatch.setattr(s, "AI_SANITIZATION_MODE_MAP", '{"criminal":"local_completo"}')
        chamadas: list = []

        async def _nao_chamar(*a, **kw):
            chamadas.append(a)
            raise AssertionError("provider externo chamado em tarefa LOCAL_COMPLETO")

        monkeypatch.setattr(ai_gateway, "_chamar_provedor", _nao_chamar)

        with pytest.raises(RuntimeError) as exc:
            await ai_gateway.chat(
                [{"role": "user", "content": f"Defesa criminal do CPF {CPF_FAKE}."}],
                task_type="criminal",
            )
        msg = str(exc.value)
        assert "local" in msg.lower()
        assert CPF_FAKE not in msg      # mensagem segura
        assert chamadas == []           # externo nunca tocado

    async def test_local_completo_via_override_usa_ollama_com_conteudo_real(self, s, monkeypatch):
        """Com LOCAL_COMPLETO (reforçado por override) e Ollama ligado, roda no
        provider LOCAL recebendo o conteúdo REAL (sem pseudonimizar) — soberania."""
        from app.services import ai_gateway

        monkeypatch.setattr(s, "AI_SANITIZATION_MODE_MAP", '{"criminal":"local_completo"}')
        monkeypatch.setattr(s, "OLLAMA_ENABLED", True)
        capturado: dict = {}

        async def _fake_provedor(provider, model, messages, temperature, max_tokens):
            capturado["provider"] = provider
            capturado["conteudo"] = " ".join(m.get("content", "") for m in messages)
            return "resposta local", {"model": "ollama-x", "input_tokens": 1, "output_tokens": 1}

        monkeypatch.setattr(ai_gateway, "_chamar_provedor", _fake_provedor)

        resp = await ai_gateway.chat(
            [{"role": "user", "content": f"Caso criminal com CPF {CPF_FAKE}."}],
            task_type="criminal",
        )
        assert capturado["provider"] == "ollama"
        assert CPF_FAKE in capturado["conteudo"]   # local recebe o dado real
        assert resp.provedor == "ollama"

    async def test_entidades_pseudonimizadas_e_reidratadas(self, s, monkeypatch):
        """FIX 3 — nomes próprios via `entidades` são pseudonimizados antes do
        provider externo e reidratados na resposta devolvida."""
        from app.services import ai_gateway

        capturado: dict = {}

        async def _fake_provedor(provider, model, messages, temperature, max_tokens):
            capturado["conteudo"] = " ".join(m.get("content", "") for m in messages)
            return "Parecer sobre [CLIENTE_1] concluído.", {
                "model": model or provider, "input_tokens": 3, "output_tokens": 4,
            }

        monkeypatch.setattr(ai_gateway, "_chamar_provedor", _fake_provedor)

        resp = await ai_gateway.chat(
            [{"role": "user", "content": "Analise o caso de João da Silva."}],
            task_type="analise_caso",
            entidades={"cliente": ["João da Silva"]},
        )
        assert "[CLIENTE_1]" in capturado["conteudo"]
        assert "João da Silva" not in capturado["conteudo"]   # nome não vaza ao externo
        assert "João da Silva" in resp.texto                  # resposta reidratada
        assert "[CLIENTE_1]" not in resp.texto

    async def test_deliverable_cpf_cnpj_nome_rg_email_so_marcadores_e_reidrata(self, s, monkeypatch):
        """ENTREGÁVEL (2026-07-06): texto com CPF + CNPJ + nome + RG + e-mail →
        (a) o provider externo recebe SÓ marcadores (nenhum valor real);
        (b) a resposta é REIDRATADA localmente (valores reais de volta ao chamador).
        Prova a barreira final do gateway intacta mesmo sem o abort de entrada."""
        from app.services import ai_gateway

        RG_FAKE = "RG 12.345.678-9"
        EMAIL2 = "joao@exemplo.com"
        capturado: dict = {}

        async def _fake_provedor(provider, model, messages, temperature, max_tokens):
            capturado["provider"] = provider
            capturado["conteudo"] = " ".join(m.get("content", "") for m in messages)
            # O modelo raciocina e responde usando SOMENTE os marcadores.
            return "Parecer sobre [CLIENTE_1]: [CPF_1], [CNPJ_1], [RG_1], [EMAIL_1].", {
                "model": model or provider, "input_tokens": 8, "output_tokens": 12,
            }

        monkeypatch.setattr(ai_gateway, "_chamar_provedor", _fake_provedor)

        texto = (
            f"Cliente João da Silva, CPF {CPF_FAKE}, CNPJ {CNPJ_FAKE}, "
            f"{RG_FAKE}, e-mail {EMAIL2}."
        )
        resp = await ai_gateway.chat(
            [{"role": "user", "content": texto}],
            task_type="analise_caso",
            entidades={"cliente": ["João da Silva"]},
        )
        # (a) provider externo recebeu SÓ marcadores — nenhum valor real de PII.
        assert capturado["provider"] in ("anthropic", "groq")
        for real in (CPF_FAKE, CNPJ_FAKE, "João da Silva", RG_FAKE, EMAIL2):
            assert real not in capturado["conteudo"], f"vazou ao externo: {real!r}"
        for marc in ("[CLIENTE_1]", "[CPF_1]", "[CNPJ_1]", "[RG_1]", "[EMAIL_1]"):
            assert marc in capturado["conteudo"]
        # (b) resposta ao chamador está REIDRATADA (todos os valores reais de volta).
        for real in (CPF_FAKE, CNPJ_FAKE, "João da Silva", RG_FAKE, EMAIL2):
            assert real in resp.texto, f"reidratação falhou para {real!r}"
        for marc in ("[CLIENTE_1]", "[CPF_1]", "[CNPJ_1]", "[RG_1]", "[EMAIL_1]"):
            assert marc not in resp.texto


# ══════════════════════════════════════════════════════════════════════════════
# 2c. executar_tarefa_ia — política de modo (FIX 1: 2º ponto de entrada por-tarefa)
# ══════════════════════════════════════════════════════════════════════════════

class TestExecutarTarefaIAModos:
    async def test_criminal_sem_ollama_local_completo_bloqueia(self, s, monkeypatch):
        """Auditoria de segurança (2026-07-06): `criminal` em executar_tarefa_ia é
        LOCAL_COMPLETO por DEFAULT. Sem Ollama elegível, BLOQUEIA: o provider externo
        (Anthropic/Groq) NUNCA é chamado — espelha o chat(). Erro sem PII."""
        from app.services import ai_gateway
        from app.services.system_prompts import TarefaIA

        chamadas: list = []

        async def _nao_chamar(*a, **kw):
            chamadas.append(a)
            raise AssertionError("provider externo chamado em tarefa LOCAL_COMPLETO")

        monkeypatch.setattr(ai_gateway, "_chamar_provedor", _nao_chamar)

        with pytest.raises(RuntimeError) as exc:
            await ai_gateway.executar_tarefa_ia(
                TarefaIA.CRIMINAL, f"Defesa do CPF {CPF_FAKE}.",
            )
        msg = str(exc.value)
        assert "local" in msg.lower()   # bloqueio LOCAL_COMPLETO
        assert CPF_FAKE not in msg       # mensagem segura, sem PII
        assert chamadas == []            # externo nunca tocado

    async def test_criminal_local_completo_via_override_usa_ollama(self, s, monkeypatch):
        """Mecanismo LOCAL_COMPLETO preservado em executar_tarefa_ia: reforçado por
        override + Ollama ligado → roda no Ollama local com conteúdo real."""
        from app.services import ai_gateway
        from app.services.system_prompts import TarefaIA

        monkeypatch.setattr(s, "AI_SANITIZATION_MODE_MAP", '{"criminal":"local_completo"}')
        monkeypatch.setattr(s, "OLLAMA_ENABLED", True)
        capturado: dict = {}

        async def _fake_provedor(provider, model, messages, temperature, max_tokens):
            capturado["provider"] = provider
            return "rascunho local", {"model": "ollama-x", "input_tokens": 1, "output_tokens": 1}

        monkeypatch.setattr(ai_gateway, "_chamar_provedor", _fake_provedor)

        out = await ai_gateway.executar_tarefa_ia(
            TarefaIA.CRIMINAL, f"Caso do CPF {CPF_FAKE}.",
        )
        assert capturado["provider"] == "ollama"
        assert out["provider"] == "ollama"

    async def test_pseudonimizado_reidrata_e_ailog_sem_pii(self, s, monkeypatch):
        """EXTERNO_PSEUDONIMIZADO (analise_caso) sem Ollama: provider externo
        recebe marcador; resposta devolvida reidratada; AILog registra a versão
        PSEUDONIMIZADA (sem PII real)."""
        from app.services import ai_gateway
        from app.services.system_prompts import TarefaIA

        capturado: dict = {}

        async def _fake_provedor(provider, model, messages, temperature, max_tokens):
            capturado["provider"] = provider
            capturado["conteudo"] = " ".join(m.get("content", "") for m in messages)
            return "Análise do CPF [CPF_1] pronta.", {
                "model": model or provider, "input_tokens": 2, "output_tokens": 3,
            }

        monkeypatch.setattr(ai_gateway, "_chamar_provedor", _fake_provedor)

        registrado: dict = {}

        async def _fake_registrar(db, **kw):
            registrado.update(kw)
            return "log-1"

        import app.services.ai_guard as ai_guard_mod
        monkeypatch.setattr(ai_guard_mod, "registrar_ai_log", _fake_registrar)

        out = await ai_gateway.executar_tarefa_ia(
            TarefaIA.ANALISE_CASO, f"Analise o caso do CPF {CPF_FAKE}.",
            user_id="u1", db=object(),
        )
        assert capturado["provider"] in ("anthropic", "groq")
        assert "[CPF_1]" in capturado["conteudo"] and CPF_FAKE not in capturado["conteudo"]
        # Resposta devolvida está reidratada.
        assert CPF_FAKE in out["conteudo"] and "[CPF_1]" not in out["conteudo"]
        # AILog não guarda PII real (prompt e resposta pseudonimizados).
        assert CPF_FAKE not in str(registrado.get("prompt_sanitizado", ""))
        assert CPF_FAKE not in str(registrado.get("resposta", ""))
        assert registrado.get("pii_removida") is True


# ══════════════════════════════════════════════════════════════════════════════
# 3. _resolver_cadeia
# ══════════════════════════════════════════════════════════════════════════════

class TestResolverCadeia:
    def test_analise_juridica_inclui_anthropic_na_ordem_de_prioridade(self, s):
        from app.services.ai_gateway import _resolver_cadeia
        cadeia = _resolver_cadeia("analise_juridica", None, None)
        providers = [p for p, _ in cadeia]
        assert "anthropic" in providers
        # Ollama OFF → anthropic vem antes de groq (AI_PROVIDER_PRIORITY).
        assert providers.index("anthropic") < providers.index("groq")
        modelo_anthropic = dict(cadeia)["anthropic"]
        assert modelo_anthropic == (s.ANTHROPIC_MODEL_COMPLEXO or s.ANTHROPIC_MODEL_RAPIDO)

    def test_sem_externos_e_sem_ollama_cai_no_last_resort_groq(self, s, monkeypatch):
        from app.services.ai_gateway import _resolver_cadeia
        monkeypatch.setattr(s, "AI_EXTERNAL_PROVIDERS_ALLOWED", False)
        monkeypatch.setattr(s, "OLLAMA_ENABLED", False)
        cadeia = _resolver_cadeia("analise_juridica", None, None)
        assert cadeia == [("groq", None)]


# ══════════════════════════════════════════════════════════════════════════════
# 4. anthropic_provider
# ══════════════════════════════════════════════════════════════════════════════

class _FakeAnthropicClient:
    """Cliente fake que captura kwargs de messages.create — zero rede."""

    def __init__(self, box: dict):
        outer = self

        class _Messages:
            def create(self, **kwargs):
                box.update(kwargs)
                return SimpleNamespace(
                    # Contrato atual do provider: a resposta pode conter blocos
                    # "thinking" antes do texto; só blocos type=="text" contam.
                    content=[SimpleNamespace(type="text", text="resposta fake")],
                    usage=SimpleNamespace(input_tokens=7, output_tokens=3),
                )

        self.messages = _Messages()


class TestAnthropicProvider:
    async def test_chat_desabilitado_levanta_runtimeerror_sem_rede(self, s, monkeypatch):
        from app.services.providers import anthropic_provider
        monkeypatch.setattr(s, "ANTHROPIC_ENABLED", False)

        def _nao_criar_client():
            raise AssertionError("client não deveria ser criado com provider desabilitado")

        monkeypatch.setattr(anthropic_provider, "_get_client", _nao_criar_client)
        with pytest.raises(RuntimeError, match="desabilitado"):
            await anthropic_provider.chat(
                [{"role": "user", "content": "olá"}], None, 0.2, 100
            )

    async def test_health_false_sem_chave(self, s, monkeypatch):
        from app.services.providers import anthropic_provider
        monkeypatch.setattr(s, "ANTHROPIC_API_KEY", "")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert await anthropic_provider.health() is False
        # Com chave fake volta a True (ENABLED + chave).
        monkeypatch.setattr(s, "ANTHROPIC_API_KEY", "sk-ant-fake")
        assert await anthropic_provider.health() is True

    async def test_teto_de_max_tokens_aplicado(self, s, monkeypatch):
        from app.services.providers import anthropic_provider
        monkeypatch.setattr(s, "ANTHROPIC_MAX_TOKENS", 500)
        box: dict = {}
        monkeypatch.setattr(anthropic_provider, "_get_client",
                            lambda: _FakeAnthropicClient(box))

        texto, usage = await anthropic_provider.chat(
            [{"role": "system", "content": "instruções"},
             {"role": "user", "content": "pergunta fictícia"}],
            None, 0.2, 2000,  # pedido acima do teto
        )
        assert box["max_tokens"] == 500  # min(2000, 500)
        assert texto == "resposta fake"
        assert usage["input_tokens"] == 7 and usage["output_tokens"] == 3

        # Pedido abaixo do teto passa intacto.
        await anthropic_provider.chat(
            [{"role": "user", "content": "outra pergunta"}], None, 0.2, 100
        )
        assert box["max_tokens"] == 100  # min(100, 500)


# ══════════════════════════════════════════════════════════════════════════════
# 5. intent_classifier
# ══════════════════════════════════════════════════════════════════════════════

class TestIntentClassifier:
    def test_task_type_jurimetria(self):
        from app.services.ai.core.intent_classifier import classify_intent
        assert classify_intent("jurimetria").agente == "JurimetryAgent"

    def test_task_type_legal_draft_exige_fonte(self):
        from app.services.ai.core.intent_classifier import classify_intent
        r = classify_intent("legal_draft")
        assert r.agente == "LegalWritingAgent"
        assert r.exige_fonte is True

    def test_domain_ambiental_usa_tarefa_ambiental(self):
        from app.services.ai.core.intent_classifier import classify_intent
        from app.services.system_prompts import TarefaIA
        r = classify_intent("task_desconhecida", domain="ambiental")
        assert r.agente == "CaseAgent"
        assert r.tarefa == TarefaIA.AMBIENTAL

    def test_keywords_na_mensagem_redigir_peticao(self):
        from app.services.ai.core.intent_classifier import classify_intent
        r = classify_intent("outra_coisa", None, "preciso redigir petição inicial fictícia")
        assert r.agente == "LegalWritingAgent"

    def test_fallback_case_agent(self):
        from app.services.ai.core.intent_classifier import classify_intent
        r = classify_intent("xyz_inexistente", None, "bom dia, tudo bem?")
        assert r.agente == "CaseAgent"
        assert r.precisa_caso is True


# ══════════════════════════════════════════════════════════════════════════════
# 6. response_validator
# ══════════════════════════════════════════════════════════════════════════════

class TestResponseValidator:
    def test_detecta_promessas_de_resultado(self):
        from app.services.ai.core.response_validator import detectar_promessa_resultado
        assert detectar_promessa_resultado("Garantimos o êxito da ação trabalhista.")
        assert detectar_promessa_resultado("Há 100% de chance de vitória neste caso.")

    def test_ignora_texto_neutro(self):
        from app.services.ai.core.response_validator import detectar_promessa_resultado
        neutro = ("A análise indica riscos processuais moderados; recomenda-se "
                  "reunir provas documentais antes do ajuizamento.")
        assert detectar_promessa_resultado(neutro) == []

    async def test_validar_sem_fontes_prefixa_sem_base_verificavel(self):
        from app.services.ai.core import response_validator
        r = await response_validator.validar(
            None, "Resposta jurídica fictícia.", exige_fonte=True, fontes=[]
        )
        assert r["sem_base_verificavel"] is True
        assert r["conteudo"].startswith("SEM BASE VERIFICÁVEL")
        assert r["revisao_obrigatoria"] is True

    async def test_validar_promessa_gera_alerta_sem_reescrever(self):
        from app.services.ai.core import response_validator
        texto = "Garantimos o êxito total do processo."
        r = await response_validator.validar(None, texto, exige_fonte=False)
        assert r["alertas"]
        assert r["revisao_obrigatoria"] is True
        assert texto in r["conteudo"]  # nunca reescreve — alerta p/ o revisor


# ══════════════════════════════════════════════════════════════════════════════
# 7. hitl_policy
# ══════════════════════════════════════════════════════════════════════════════

class TestHITLPolicy:
    def test_aplicar_sempre_rascunho(self, s):
        from app.services.ai.core import hitl_policy
        r = hitl_policy.aplicar({"conteudo": "minuta fictícia"})
        assert r["is_rascunho"] is True
        assert r["status_hitl"] == "gerado"
        assert r["aviso_hitl"]

    def test_rascunho_mesmo_com_hitl_flag_desligada(self, s, monkeypatch):
        from app.services.ai.core import hitl_policy
        monkeypatch.setattr(s, "AI_REQUIRE_HITL", False)
        r = hitl_policy.aplicar({"conteudo": "x"})
        assert r["is_rascunho"] is True  # rótulo de rascunho é inegociável
        assert r["status_hitl"] == "gerado"


# ══════════════════════════════════════════════════════════════════════════════
# 8. SingleAICoreOrchestrator (tudo mockado — sem rede, sem banco)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def nucleo_mocks(s, monkeypatch):
    """Mocks do pipeline: gateway.chat, context_builder e audit_logger.
    Devolve um setter para controlar o texto 'gerado pelo modelo'."""
    from app.services import ai_gateway
    from app.services.ai.core import audit_logger, context_builder
    from app.services.ai.core.context_builder import ContextoMontado

    # Ollama ON p/ a policy permitir sem depender de sanitização externa.
    monkeypatch.setattr(s, "OLLAMA_ENABLED", True)

    estado = {"texto": "Análise estratégica fictícia, sem promessas."}

    async def fake_montar_contexto(db, **kw):
        return ContextoMontado()

    async def fake_registrar(db, **kw):
        return "log-fake"

    async def fake_chat(messages, **kw):
        return ai_gateway.GatewayResponse(
            texto=estado["texto"],
            modelo="modelo-fake",
            provedor="ollama",
            task_type=kw.get("task_type", ""),
            input_tokens=10,
            output_tokens=20,
        )

    monkeypatch.setattr(context_builder, "montar_contexto", fake_montar_contexto)
    monkeypatch.setattr(audit_logger, "registrar", fake_registrar)
    monkeypatch.setattr(ai_gateway, "chat", fake_chat)

    def set_texto(t: str):
        estado["texto"] = t

    return set_texto


def _user(role: str):
    return SimpleNamespace(id="usuario-fake-1", role=role)


class TestOrchestrator:
    async def test_cliente_externo_bloqueado_403(self, nucleo_mocks):
        from app.services.ai.core.orchestrator import orchestrator
        with pytest.raises(HTTPException) as exc:
            await orchestrator.run(
                db=None, user=_user("cliente_externo"),
                task_type="chat", mensagem="Qual o andamento do meu caso?",
            )
        assert exc.value.status_code == 403

    async def test_advogado_bloqueado_em_agente_tecnico_403(self, nucleo_mocks):
        from app.services.ai.core.orchestrator import orchestrator
        with pytest.raises(HTTPException) as exc:
            await orchestrator.run(
                db=None, user=_user("advogado"),
                task_type="saude_sistema", mensagem="diagnóstico geral do sistema",
            )
        assert exc.value.status_code == 403

    async def test_fluxo_feliz_chat(self, nucleo_mocks):
        from app.services.ai.core.orchestrator import orchestrator
        r = await orchestrator.run(
            db=None, user=_user("advogado"),
            task_type="chat",
            mensagem="Analise a estratégia geral de um caso trabalhista fictício.",
        )
        assert r["is_rascunho"] is True
        assert r["aviso_hitl"]
        assert r["agente"] == "CaseAgent"
        assert r["modelo"] == "ollama/modelo-fake"
        assert r["provider"] == "ollama"
        assert r["log_id"] == "log-fake"
        assert r["status_hitl"] == "gerado"
        assert r["custo_estimado_brl"] == 0.0  # provedor local não fatura

    async def test_promessa_do_modelo_gera_alerta_e_revisao(self, nucleo_mocks):
        from app.services.ai.core.orchestrator import orchestrator
        nucleo_mocks("Garantimos o êxito da causa com 100% de certeza.")
        r = await orchestrator.run(
            db=None, user=_user("advogado"),
            task_type="chat", mensagem="Como fica o caso fictício?",
        )
        assert r["alertas"]
        assert r["revisao_obrigatoria"] is True
        assert r["is_rascunho"] is True


# ══════════════════════════════════════════════════════════════════════════════
# 9. Registries (agentes e skills)
# ══════════════════════════════════════════════════════════════════════════════

AGENTES_CANONICOS = {
    "CaseAgent", "ProcessAgent", "DocumentAgent", "LegalWritingAgent",
    "RAGResearchAgent", "JurimetryAgent", "FinanceAgent", "BankForensicsAgent",
    "ConsumerLawAgent", "TaxLawAgent", "SocialSecurityAgent", "CorporateLawAgent",
    "LaborLawAgent", "CriminalLawAgent", "FamilyLawAgent",
    "AdministrativeLawAgent", "SuccessionLawAgent", "RealEstateLawAgent",
    "ConstitutionalLawAgent", "SpecialCourtsAgent", "CivilLawAgent",
    "TrafficLawAgent", "HealthLawAgent", "MedicalLawAgent", "AgrarianLawAgent",
    "AgribusinessLawAgent", "ElectoralLawAgent", "InternationalLawAgent",
    "ContractLawAgent",
    "ClientCommunicationAgent", "SystemHealthAgent",
    "RepairAgent", "UIUXAgent", "SecurityLGPDOABAgent",
}


class TestRegistries:
    def test_agentes_canonicos(self):
        from app.services.ai.core.agent_registry import AGENT_REGISTRY
        assert len(AGENT_REGISTRY) == len(AGENTES_CANONICOS)
        assert set(AGENT_REGISTRY.keys()) == AGENTES_CANONICOS
        for nome, ag in AGENT_REGISTRY.items():
            assert ag.nome == nome  # chave == nome canônico

    def test_27_skills_registradas(self):
        from app.services.ai.core.skill_registry import SKILL_REGISTRY
        assert len(SKILL_REGISTRY) == 27

    def test_skills_de_patch_nunca_automaticas(self):
        from app.services.ai.core.skill_registry import SKILL_REGISTRY
        assert SKILL_REGISTRY["apply_authorized_patch"].handler is None
        assert SKILL_REGISTRY["rollback_patch"].handler is None

    def test_listar_skills_nao_expoe_handlers(self):
        from app.services.ai.core.skill_registry import SKILL_REGISTRY, listar_skills
        skills = listar_skills()
        assert len(skills) == 27
        for item in skills:
            assert "handler" not in item
            assert not any(callable(v) for v in item.values())
            assert isinstance(item["automatica"], bool)
        por_nome = {i["nome"]: i for i in skills}
        assert por_nome["apply_authorized_patch"]["automatica"] is False
        assert por_nome["rollback_patch"]["automatica"] is False
        assert por_nome["classify_intent"]["automatica"] is True
        assert set(por_nome) == set(SKILL_REGISTRY)


# ══════════════════════════════════════════════════════════════════════════════
# 10. Router /ai/core (import + rotas presentes, sem subir servidor)
# ══════════════════════════════════════════════════════════════════════════════

class TestRouterAICore:
    def test_rotas_do_nucleo_presentes(self):
        from app.routers.ai_core import router
        paths = {r.path for r in router.routes}
        esperadas = {
            "/ai/core/chat", "/ai/core/task", "/ai/core/analyze",
            "/ai/core/generate", "/ai/core/report", "/ai/core/agents",
            "/ai/core/skills", "/ai/core/status",
        }
        assert esperadas <= paths
