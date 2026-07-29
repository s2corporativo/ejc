"""Piso de sigilo por área (AI-019) — regressão da consolidação 2026-07-29.

O orquestrador converte `TarefaIA.FAMILIA` em "estrategia" ANTES de chamar o
gateway (`_TAREFA_PARA_GATEWAY`), e é o gateway que resolve o modo de
sanitização pelo `task_type`. Sem o piso, o rótulo da área sensível se perde no
meio da cadeia e o conteúdo sai do VPS como EXTERNO_PSEUDONIMIZADO.

Os testes de ponta a ponta abaixo CAPTURAM o `task_type` que efetivamente chega
ao gateway — provar a política só na função de policy não bastaria, porque o
achado original era justamente a transformação intermediária.

Regressão específica desta consolidação: a resolução era lookup de chave EXATA
sobre `.strip().lower()`, então "família" (acentuado), "Direito de Família" e
"familia_analysis" — este último é o `task_type` que `/api/ai-core/analyze`
monta como f"{domain}_analysis" — NÃO batiam com a chave "familia" e caíam no
fallback externo. Dados todos fictícios; nenhum teste toca rede.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.services.ai.sanitization_policy import (
    ModoSanitizacao,
    modo_para_task,
    normalizar_rotulo,
    rotulo_de_sigilo_reforcado,
)


# ── 1. Canonização do rótulo ─────────────────────────────────────────────────

class TestNormalizarRotulo:
    @pytest.mark.parametrize("bruto,esperado", [
        ("familia", "familia"),
        ("família", "familia"),
        ("Família", "familia"),
        ("  FAMÍLIA  ", "familia"),
        ("Direito de Família", "direito_de_familia"),
        ("familia_analysis", "familia"),
        ("família_analysis", "familia"),
        ("violência doméstica", "violencia_domestica"),
        ("infância e juventude", "infancia_e_juventude"),
        ("", ""),
        (None, ""),
    ])
    def test_canoniza(self, bruto, esperado):
        assert normalizar_rotulo(bruto) == esperado

    def test_nao_engole_rotulo_que_e_so_o_sufixo(self):
        # "_analysis" sozinho não vira string vazia (guarda do len()).
        assert normalizar_rotulo("_analysis") == "analysis"


# ── 2. Piso de sigilo por área ───────────────────────────────────────────────

AREAS_SIGILOSAS = [
    "familia", "família", "Família", "Direito de Família", "familia_analysis",
    "família_analysis", "direito_de_familia", "penal", "criminal",
    "criminal_analysis", "saude", "saúde", "plano de saude", "medico",
    "menores", "violencia", "violência doméstica", "infancia_juventude",
    "vara da infancia e juventude",
]

AREAS_NAO_SIGILOSAS = [
    "trabalhista", "civel", "cível", "estrategia", "analise_caso",
    "analise_juridica", "empresarial", "tributario", "ambiental",
    "consumidor", "imobiliario", "sucessoes", "chat", "resumo",
]


class TestModoParaTask:
    @pytest.mark.parametrize("rotulo", AREAS_SIGILOSAS)
    def test_area_sensivel_e_local_completo(self, rotulo):
        assert modo_para_task(rotulo) == ModoSanitizacao.LOCAL_COMPLETO

    @pytest.mark.parametrize("rotulo", AREAS_NAO_SIGILOSAS)
    def test_area_comum_nao_e_bloqueada_no_local(self, rotulo):
        """O piso não pode virar bloqueio geral: área comum segue externa
        pseudonimizada (senão a IA fica indisponível sem Ollama on-prem)."""
        assert modo_para_task(rotulo) != ModoSanitizacao.LOCAL_COMPLETO

    def test_tarefa_desconhecida_cai_no_fallback_reversivel(self):
        assert modo_para_task("tarefa_que_nao_existe_no_mapa") == (
            ModoSanitizacao.EXTERNO_PSEUDONIMIZADO
        )


class TestRotuloDeSigiloReforcado:
    def test_devolve_chave_canonica_e_nao_o_texto_cru(self):
        """O gateway precisa da CHAVE do mapa; devolver "Direito de Família"
        cru faria o gateway reconsultar um rótulo que ele não conhece."""
        assert rotulo_de_sigilo_reforcado("Direito de Família") == "familia"

    def test_respeita_a_ordem_dos_rotulos(self):
        assert rotulo_de_sigilo_reforcado("trabalhista", "familia") == "familia"

    def test_none_quando_nenhuma_area_e_sensivel(self):
        assert rotulo_de_sigilo_reforcado("trabalhista", "civel", None) is None

    def test_ignora_rotulos_vazios(self):
        assert rotulo_de_sigilo_reforcado("", None, "familia") == "familia"


class TestOverrideNaoRebaixa:
    @pytest.mark.parametrize("chave_override", ["familia", "família", "Família"])
    def test_override_nao_rebaixa_area_sensivel(self, monkeypatch, chave_override):
        """AI_SANITIZATION_MODE_MAP não pode mandar família para externo — nem
        escrevendo a chave com acento para escapar da normalização."""
        st = get_settings()
        monkeypatch.setattr(
            st, "AI_SANITIZATION_MODE_MAP",
            '{"%s": "externo_pseudonimizado"}' % chave_override,
        )
        assert modo_para_task("familia") == ModoSanitizacao.LOCAL_COMPLETO
        assert modo_para_task("família") == ModoSanitizacao.LOCAL_COMPLETO

    def test_override_pode_reforcar_area_comum(self, monkeypatch):
        st = get_settings()
        monkeypatch.setattr(
            st, "AI_SANITIZATION_MODE_MAP", '{"trabalhista": "local_completo"}',
        )
        assert modo_para_task("trabalhista") == ModoSanitizacao.LOCAL_COMPLETO


# ── 3. Ponta a ponta: o rótulo que CHEGA ao gateway ──────────────────────────

@pytest.fixture
def gateway_espiao(monkeypatch):
    """Roda o orquestrador com tudo mockado e captura o `task_type` recebido
    pelo gateway — o ponto exato onde o piso de sigilo precisa sobreviver."""
    from app.services import ai_gateway
    from app.services.ai.core import audit_logger, context_builder
    from app.services.ai.core.context_builder import ContextoMontado

    st = get_settings()
    monkeypatch.setattr(st, "OLLAMA_ENABLED", True)
    monkeypatch.setattr(st, "AI_EXTERNAL_PROVIDERS_ALLOWED", True)
    monkeypatch.setattr(st, "AI_SANITIZATION_MODE_MAP", "")

    capturado: dict = {}

    async def fake_montar_contexto(db, **kw):
        return ContextoMontado()

    async def fake_registrar(db, **kw):
        return "log-fake"

    async def fake_chat(messages, **kw):
        capturado["task_type"] = kw.get("task_type", "")
        return ai_gateway.GatewayResponse(
            texto="Resposta fictícia para teste.",
            modelo="modelo-fake", provedor="ollama",
            task_type=kw.get("task_type", ""), input_tokens=1, output_tokens=1,
        )

    monkeypatch.setattr(context_builder, "montar_contexto", fake_montar_contexto)
    monkeypatch.setattr(audit_logger, "registrar", fake_registrar)
    monkeypatch.setattr(ai_gateway, "chat", fake_chat)
    return capturado


def _advogado():
    return SimpleNamespace(id="usuario-ficticio-1", role="advogado")


async def _rodar(task_type: str, domain: str | None = None):
    from app.services.ai.core.orchestrator import orchestrator
    return await orchestrator.run(
        db=None, user=_advogado(), task_type=task_type, domain=domain,
        mensagem="Caso fictício de guarda compartilhada para teste.",
    )


class TestPisoChegaAoGateway:
    async def test_familia_nao_vira_estrategia_no_gateway(self, gateway_espiao):
        """Achado AI-019: TarefaIA.FAMILIA era convertida em "estrategia" e
        perdia o piso. O gateway precisa receber "familia"."""
        await _rodar("familia", "familia")
        assert gateway_espiao["task_type"] == "familia"
        assert modo_para_task(gateway_espiao["task_type"]) == (
            ModoSanitizacao.LOCAL_COMPLETO
        )

    async def test_dominio_acentuado_nao_escapa_do_piso(self, gateway_espiao):
        """Regressão do bypass por string livre: `domain` vem de campo aberto
        (Field(max_length=60)) e a UI em português manda "Família"."""
        await _rodar("chat", "Família")
        assert gateway_espiao["task_type"] == "familia"

    async def test_dominio_em_texto_livre_nao_escapa_do_piso(self, gateway_espiao):
        await _rodar("chat", "Direito de Família")
        assert gateway_espiao["task_type"] == "familia"

    async def test_task_type_do_endpoint_analyze_nao_escapa(self, gateway_espiao):
        """/api/ai-core/analyze monta task_type = f"{domain}_analysis"."""
        await _rodar("familia_analysis", "familia")
        assert gateway_espiao["task_type"] == "familia"

    async def test_area_comum_mantem_o_roteamento_original(self, gateway_espiao):
        """O piso não pode reescrever o rótulo de área não sensível — isso
        estragaria o roteamento de modelo do TASK_ROUTING."""
        await _rodar("chat", "trabalhista")
        assert gateway_espiao["task_type"] == "estrategia"
        assert modo_para_task(gateway_espiao["task_type"]) != (
            ModoSanitizacao.LOCAL_COMPLETO
        )


# ── 4. O piso realmente bloqueia a saída externa ─────────────────────────────

class TestGatewayBloqueiaExternoEmAreaSensivel:
    async def test_sem_provider_local_a_chamada_e_bloqueada(self, monkeypatch):
        """Fail-closed: em LOCAL_COMPLETO sem Ollama elegível o gateway levanta
        em vez de cair para Anthropic/Groq. Vale para o rótulo acentuado."""
        from app.services import ai_gateway

        st = get_settings()
        monkeypatch.setattr(st, "OLLAMA_ENABLED", False)
        monkeypatch.setattr(st, "ANTHROPIC_ENABLED", True)
        monkeypatch.setattr(st, "ANTHROPIC_API_KEY", "sk-ant-fake-para-testes")
        monkeypatch.setattr(st, "GROQ_API_KEY", "gsk-fake-para-testes")
        monkeypatch.setattr(st, "AI_EXTERNAL_PROVIDERS_ALLOWED", True)
        monkeypatch.setattr(st, "AI_SANITIZATION_MODE_MAP", "")

        async def explode(*a, **k):
            raise AssertionError("provider externo NÃO pode ser chamado")

        monkeypatch.setattr(ai_gateway, "_chamar_provedor", explode)

        for rotulo in ("familia", "família", "Direito de Família"):
            with pytest.raises(RuntimeError):
                await ai_gateway.chat(
                    [{"role": "user", "content": "Caso fictício de guarda."}],
                    task_type=rotulo,
                )
