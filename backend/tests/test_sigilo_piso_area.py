"""Piso de sigilo por área (AI-019) — regressão da consolidação 2026-07-29.

O orquestrador converte `TarefaIA.MENORES`/tarefas de mérito em rótulos como
"estrategia" ANTES de chamar o gateway (`_TAREFA_PARA_GATEWAY`), e é o gateway
que resolve o modo de sanitização pelo `task_type`. Sem o piso, o rótulo da
área sensível se perde no meio da cadeia e o conteúdo sai do VPS como
EXTERNO_PSEUDONIMIZADO.

Os testes de ponta a ponta abaixo CAPTURAM o `task_type` que efetivamente chega
ao gateway — provar a política só na função de policy não bastaria, porque o
achado original era justamente a transformação intermediária.

Regressão específica desta consolidação: a resolução era lookup de chave EXATA
sobre `.strip().lower()`, então "menores" (acentuado em variantes), "Vara da
Infância e Juventude" e "menores_analysis" — este último é o `task_type` que
`/api/ai-core/analyze` monta como f"{domain}_analysis" — NÃO batiam com a
chave "menores" e caíam no fallback externo. Dados todos fictícios; nenhum
teste toca rede.

ATUALIZAÇÃO (18/08, decisão do titular): o piso LOCAL_COMPLETO foi reduzido a
crimes sexuais e menores/infância e juventude — família, saúde, médico,
criminal/penal geral e violência (inclusive doméstica) voltaram a
EXTERNO_PSEUDONIMIZADO. Os exemplos "família" usados como área sensível de
referência na consolidação original foram trocados por "menores"/"crimes
sexuais" (o mecanismo testado — normalização, piso não-rebaixável, roteamento
preservado, autoridade da área do caso — é o mesmo; só a lista de áreas
restritas mudou). Ver `app/services/ai/sanitization_policy.py`.
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
    "menores", "Menores", "menores_analysis", "Menores_analysis",
    "infancia_juventude", "vara da infancia e juventude",
    "crimes_sexuais", "crime sexual", "crimes sexuais", "Crime Sexual",
    "abuso sexual", "estupro", "estupro de vulneravel", "pedofilia",
]

AREAS_NAO_SIGILOSAS = [
    "trabalhista", "civel", "cível", "estrategia", "analise_caso",
    "analise_juridica", "empresarial", "tributario", "ambiental",
    "consumidor", "imobiliario", "sucessoes", "chat", "resumo",
    # Voltaram ao tratamento normal por decisão do titular (18/08): só
    # crimes sexuais e menores continuam LOCAL_COMPLETO.
    "familia", "família", "Direito de Família", "familia_analysis",
    "penal", "criminal", "criminal_analysis", "saude", "saúde",
    "plano de saude", "medico", "violencia", "violência doméstica",
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
        """O gateway precisa da CHAVE do mapa; devolver "Vara da Infância e
        Juventude" cru faria o gateway reconsultar um rótulo que ele não
        conhece."""
        assert rotulo_de_sigilo_reforcado("Vara da Infância e Juventude") == \
            "infancia_juventude"

    def test_respeita_a_ordem_dos_rotulos(self):
        assert rotulo_de_sigilo_reforcado("trabalhista", "menores") == "menores"

    def test_none_quando_nenhuma_area_e_sensivel(self):
        assert rotulo_de_sigilo_reforcado("trabalhista", "civel", None) is None

    def test_area_normal_apos_reducao_do_piso_nao_e_sigilosa(self):
        """Família/saúde/violência voltaram a EXTERNO_PSEUDONIMIZADO (decisão
        do titular, 18/08) — não devem mais aparecer como sigilo reforçado."""
        assert rotulo_de_sigilo_reforcado("familia", "saude", "violencia") is None

    def test_ignora_rotulos_vazios(self):
        assert rotulo_de_sigilo_reforcado("", None, "menores") == "menores"


class TestOverrideNaoRebaixa:
    @pytest.mark.parametrize("chave_override", ["menores", "Menores"])
    def test_override_nao_rebaixa_area_sensivel(self, monkeypatch, chave_override):
        """AI_SANITIZATION_MODE_MAP não pode mandar menores para externo —
        nem escrevendo a chave com variação de caixa para tentar escapar da
        normalização."""
        st = get_settings()
        monkeypatch.setattr(
            st, "AI_SANITIZATION_MODE_MAP",
            '{"%s": "externo_pseudonimizado"}' % chave_override,
        )
        assert modo_para_task("menores") == ModoSanitizacao.LOCAL_COMPLETO
        assert modo_para_task("Menores") == ModoSanitizacao.LOCAL_COMPLETO

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
        # Registra TODAS as chamadas: a crítica adversarial do Modo Duas IAs
        # chama o gateway uma segunda vez, e o que interessa aferir é a chamada
        # de GERAÇÃO (a primeira).
        capturado.setdefault("chamadas", []).append({
            "task_type": kw.get("task_type", ""),
            "modo": kw.get("modo_sanitizacao"),
        })
        capturado["task_type"] = capturado["chamadas"][0]["task_type"]
        capturado["modo"] = capturado["chamadas"][0]["modo"]
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
    async def test_menores_nao_vira_estrategia_no_gateway(self, gateway_espiao):
        """Achado AI-019: TarefaIA.MENORES era convertida em "estrategia" e
        perdia o piso. O gateway precisa receber "menores"."""
        await _rodar("menores", "menores")
        assert gateway_espiao["modo"] == ModoSanitizacao.LOCAL_COMPLETO
        assert gateway_espiao["modo"] == ModoSanitizacao.LOCAL_COMPLETO

    async def test_dominio_com_caixa_variada_nao_escapa_do_piso(self, gateway_espiao):
        """Regressão do bypass por string livre: `domain` vem de campo aberto
        (Field(max_length=60)) e a UI em português manda "Menores"."""
        await _rodar("chat", "Menores")
        assert gateway_espiao["modo"] == ModoSanitizacao.LOCAL_COMPLETO

    async def test_dominio_em_texto_livre_nao_escapa_do_piso(self, gateway_espiao):
        await _rodar("chat", "Vara da Infância e Juventude")
        assert gateway_espiao["modo"] == ModoSanitizacao.LOCAL_COMPLETO

    async def test_task_type_do_endpoint_analyze_nao_escapa(self, gateway_espiao):
        """/api/ai-core/analyze monta task_type = f"{domain}_analysis"."""
        await _rodar("menores_analysis", "menores")
        assert gateway_espiao["modo"] == ModoSanitizacao.LOCAL_COMPLETO

    async def test_area_reduzida_do_piso_nao_e_mais_local(self, gateway_espiao):
        """Família voltou a EXTERNO_PSEUDONIMIZADO (decisão do titular,
        18/08) — não pode mais chegar como LOCAL_COMPLETO no gateway."""
        await _rodar("chat", "Direito de Família")
        assert gateway_espiao["modo"] != ModoSanitizacao.LOCAL_COMPLETO

    async def test_area_comum_mantem_o_roteamento_original(self, gateway_espiao):
        """O piso não pode reescrever o rótulo de área não sensível — isso
        estragaria o roteamento de modelo do TASK_ROUTING."""
        await _rodar("chat", "trabalhista")
        assert gateway_espiao["task_type"] == "estrategia"
        assert gateway_espiao["modo"] is None
        assert gateway_espiao["modo"] != ModoSanitizacao.LOCAL_COMPLETO


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

        for rotulo in ("menores", "Menores", "Vara da Infância e Juventude"):
            with pytest.raises(RuntimeError):
                await ai_gateway.chat(
                    [{"role": "user", "content": "Caso fictício de guarda."}],
                    task_type=rotulo,
                )


# ── 5. A ÁREA REAL DO CASO manda, não o rótulo enviado ───────────────────────

class TestAreaDoCasoEAutoritativa:
    """Achado da auditoria de segurança 2026-07-29: o piso consultava só
    `task_type`/`domain`/tarefa — todos derivados do CORPO da requisição. Um
    caso cuja `Case.area` é sensível, consultado sem `domain` (ou com "civel"),
    escapava do piso e levava dossiê, documentos e RAG ao provider externo. O
    caminho agêntico (ai/agent/loop.py) já lia `caso.area`; este não."""

    async def test_caso_de_menores_sem_domain_nao_escapa(self, gateway_espiao, monkeypatch):
        from types import SimpleNamespace as NS

        from app.core import ownership
        from app.services.ai.core.orchestrator import orchestrator

        async def fake_acesso(db, cu, case_id):
            return NS(id=case_id, area=NS(value="menores"))

        monkeypatch.setattr(ownership, "verificar_acesso_caso", fake_acesso)
        await orchestrator.run(
            db=object(), user=_advogado(), task_type="chat", domain=None,
            case_id="caso-ficticio-1",
            mensagem="Resumo do andamento deste caso fictício.",
        )
        assert gateway_espiao["modo"] == ModoSanitizacao.LOCAL_COMPLETO

    async def test_rotulo_generico_nao_rebaixa_caso_sensivel(self, gateway_espiao, monkeypatch):
        """Mesmo declarando `domain="civel"`, a área do caso prevalece."""
        from types import SimpleNamespace as NS

        from app.core import ownership
        from app.services.ai.core.orchestrator import orchestrator

        async def fake_acesso(db, cu, case_id):
            return NS(id=case_id, area=NS(value="crimes_sexuais"))

        monkeypatch.setattr(ownership, "verificar_acesso_caso", fake_acesso)
        await orchestrator.run(
            db=object(), user=_advogado(), task_type="chat", domain="civel",
            case_id="caso-ficticio-2", mensagem="Analise este caso fictício.",
        )
        assert gateway_espiao["modo"] == ModoSanitizacao.LOCAL_COMPLETO

    async def test_caso_de_area_sensivel_reduzida_agora_segue_externo(
            self, gateway_espiao, monkeypatch):
        """Criminal geral voltou a EXTERNO_PSEUDONIMIZADO (decisão do
        titular, 18/08) — a área do caso continua autoritativa, só que agora
        aponta para o modo normal."""
        from types import SimpleNamespace as NS

        from app.core import ownership
        from app.services.ai.core.orchestrator import orchestrator

        async def fake_acesso(db, cu, case_id):
            return NS(id=case_id, area=NS(value="criminal"))

        monkeypatch.setattr(ownership, "verificar_acesso_caso", fake_acesso)
        await orchestrator.run(
            db=object(), user=_advogado(), task_type="chat", domain=None,
            case_id="caso-ficticio-2b", mensagem="Analise este caso fictício.",
        )
        assert gateway_espiao["modo"] != ModoSanitizacao.LOCAL_COMPLETO

    async def test_caso_de_area_comum_segue_externo(self, gateway_espiao, monkeypatch):
        from types import SimpleNamespace as NS

        from app.core import ownership
        from app.services.ai.core.orchestrator import orchestrator

        async def fake_acesso(db, cu, case_id):
            return NS(id=case_id, area=NS(value="trabalhista"))

        monkeypatch.setattr(ownership, "verificar_acesso_caso", fake_acesso)
        await orchestrator.run(
            db=object(), user=_advogado(), task_type="chat", domain=None,
            case_id="caso-ficticio-3", mensagem="Analise este caso fictício.",
        )
        assert gateway_espiao["modo"] != ModoSanitizacao.LOCAL_COMPLETO


# ── 6. Variantes morfológicas e caracteres invisíveis ────────────────────────

class TestVariantesMorfologicas:
    @pytest.mark.parametrize("rotulo", [
        "guarda de menor", "infanto-juvenil", "juizado da infancia",
        "vara da infancia e juventude", "crime sexual", "abuso sexual",
        "estupro de vulneravel", "violencia sexual", "pedofilia",
        "exploracao sexual infantil", "importunacao sexual",
    ])
    def test_variante_de_area_sensivel_e_local(self, rotulo):
        assert modo_para_task(rotulo) == ModoSanitizacao.LOCAL_COMPLETO

    @pytest.mark.parametrize("rotulo", [
        "men​ores",      # zero-width space
        "men­ores",      # soft hyphen
        "‎menores",      # left-to-right mark
    ])
    def test_caractere_invisivel_nao_contorna_o_piso(self, rotulo):
        assert modo_para_task(rotulo) == ModoSanitizacao.LOCAL_COMPLETO

    @pytest.mark.parametrize("rotulo", [
        "trabalhista", "civel", "tributario", "empresarial", "ambiental",
        "consumidor", "imobiliario", "administrativo",
        # Voltaram ao tratamento normal por decisão do titular (18/08):
        # radicais que hoje resolvem para família/criminal/penal/médico
        # geral, sem token de menor/sexual.
        "pericia medica", "perícia médica", "direito familiar",
        "antecedentes criminais", "habeas corpus", "divorcio consensual",
        "acao de alimentos", "empregada domestica", "vara criminal",
    ])
    def test_area_comum_continua_externa(self, rotulo):
        assert modo_para_task(rotulo) != ModoSanitizacao.LOCAL_COMPLETO


# ── 7. Sigilo não pode sequestrar o ROTEAMENTO ───────────────────────────────

class TestSigiloNaoQuebraRoteamento:
    """Achado da revisão de código 2026-07-29: o piso sobrescrevia o
    `task_type`, que também governa a cadeia de modelos (TASK_ROUTING) e a
    crítica adversarial do Modo Duas IAs (DUAS_IAS_TASK_TYPES). Uma minuta num
    caso de família virava task_type "familia" e saía da crítica — a peça de
    maior risco jurídico ficava sem a segunda leitura."""

    async def test_minuta_em_caso_sensivel_mantem_elaboracao_peca(
            self, gateway_espiao, monkeypatch):
        from types import SimpleNamespace as NS

        from app.core import ownership
        from app.services.ai.core.orchestrator import orchestrator

        async def fake_acesso(db, cu, case_id):
            return NS(id=case_id, area=NS(value="menores"))

        monkeypatch.setattr(ownership, "verificar_acesso_caso", fake_acesso)
        await orchestrator.run(
            db=object(), user=_advogado(), task_type="minutas",
            case_id="caso-ficticio-4",
            mensagem="Minuta fictícia para o caso.",
        )
        # Roteamento preservado na chamada de geração…
        assert gateway_espiao["chamadas"][0]["task_type"] == "elaboracao_peca"
        # …o sigilo aplicado mesmo assim…
        assert gateway_espiao["chamadas"][0]["modo"] == ModoSanitizacao.LOCAL_COMPLETO
        # …e a crítica adversarial VOLTOU a rodar (era o efeito colateral).
        assert any(c["task_type"] == "critica_adversarial"
                   for c in gateway_espiao["chamadas"])

    async def test_rotulo_de_area_nao_existe_no_task_routing(self):
        """Prova a razão do achado: "familia" não é chave de roteamento, então
        sobrescrever o task_type jogava a chamada no fallback genérico."""
        from app.services.ai_gateway import TASK_ROUTING
        assert "elaboracao_peca" in TASK_ROUTING
        assert "familia" not in TASK_ROUTING

    async def test_critica_adversarial_continua_habilitada(self):
        from app.services.ai import adversarial
        assert adversarial.critica_automatica_habilitada("elaboracao_peca") is True
        assert adversarial.critica_automatica_habilitada("familia") is False


class TestModoSanitizacaoSoEleva:
    async def test_parametro_nao_rebaixa_o_piso_do_task_type(self, monkeypatch):
        """Um chamador não pode usar `modo_sanitizacao` para liberar uma tarefa
        que o próprio task_type já classifica como LOCAL_COMPLETO."""
        from app.services import ai_gateway

        st = get_settings()
        monkeypatch.setattr(st, "OLLAMA_ENABLED", False)
        monkeypatch.setattr(st, "ANTHROPIC_ENABLED", True)
        monkeypatch.setattr(st, "ANTHROPIC_API_KEY", "sk-ant-fake-para-testes")
        monkeypatch.setattr(st, "AI_EXTERNAL_PROVIDERS_ALLOWED", True)
        monkeypatch.setattr(st, "AI_SANITIZATION_MODE_MAP", "")

        async def explode(*a, **k):
            raise AssertionError("provider externo NÃO pode ser chamado")

        monkeypatch.setattr(ai_gateway, "_chamar_provedor", explode)

        with pytest.raises(RuntimeError):
            await ai_gateway.chat(
                [{"role": "user", "content": "Caso fictício."}],
                task_type="menores",
                modo_sanitizacao=ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
            )
