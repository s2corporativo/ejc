"""Módulo AGÊNTICO de IA (loop de tool-use atrás de AI_AGENT_ENABLED).

Tudo mockado (provider Anthropic / gateway / tools / DB) — nenhum teste toca
rede ou banco real. Espelha o estilo de test_duas_ias.py e test_pseudonymizer.py:
settings via monkeypatch na instância cacheada de get_settings(); dados FICTÍCIOS
(CPF sintético 123.456.789-09, nomes inventados).

Cobre (atualizado para os achados S1/H1/S2/S3/M3/M5/L6/L7/L9 + Sugestões 2 e 3):
  1. Barreira LGPD AGÊNTICA: nome próprio + CPF no histórico (inclusive dentro de
     tool_result e tool_use.input ANINHADO, S2) NUNCA vazam em claro; marcadores
     consistentes; resposta reidratada (recursiva); text_para_log pseudonimizado.
  2. anthropic_provider.chat_tools: parse text+tool_use, ignora thinking; modelo
     moderno sem temperature e SEM piso 8192 no caminho de tool-use (M3).
  3. Registry/permissions: 13 tools (4 originais + 9 dos motores, FASE 6);
     leitura sem confirmação, escrita com HITL; roles nas escritas (L9);
     schemas(role) filtra por papel.
  4. Loop rodar_agente: HITL vinculado aos ARGS com retomada por token (H1) e
     fallback por hash; teto de passos/custo (L6/Sug.2); stop_reason max_tokens/
     pause_turn (L7); área sigilosa fail-closed (S1); degradação de PII residual
     (M5); erros seguros.
  5. ler_dossie leitor PURO (S3): nenhuma escrita/gerar_dossie.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config import get_settings

# ── Dados fictícios (nenhum dado real) ────────────────────────────────────────
NOME = "João da Silva"
CPF = "123.456.789-09"


@pytest.fixture
def s(monkeypatch):
    """Baseline: Anthropic elegível, sanitização externa exigida, Ollama OFF."""
    st = get_settings()
    monkeypatch.setattr(st, "ANTHROPIC_ENABLED", True)
    monkeypatch.setattr(st, "ANTHROPIC_API_KEY", "sk-ant-fake-para-testes")
    monkeypatch.setattr(st, "AI_EXTERNAL_PROVIDERS_ALLOWED", True)
    monkeypatch.setattr(st, "AI_REQUIRE_SANITIZATION_FOR_EXTERNAL", True)
    monkeypatch.setattr(st, "OLLAMA_ENABLED", False)
    monkeypatch.setattr(st, "AI_PROVIDER", "auto")
    monkeypatch.setattr(st, "GROQ_API_KEY", "")
    monkeypatch.setattr(st, "AI_SANITIZATION_MODE_MAP", "")
    return st


# ══════════════════════════════════════════════════════════════════════════════
# 1. Barreira LGPD AGÊNTICA — content str / bloco text / tool_use.input /
#    tool_result. PII real nunca vai ao provider; marcadores reversíveis.
# ══════════════════════════════════════════════════════════════════════════════

def _historico_com_pii() -> list[dict]:
    """Histórico agêntico (ESPAÇO REAL) com nome+CPF em content, tool_use.input
    e tool_result — cobrindo TODOS os slots que a barreira deve pseudonimizar."""
    return [
        {"role": "system", "content": "Você é o agente jurídico."},
        {"role": "user", "content": f"Analise o caso de {NOME}, CPF {CPF}."},
        {"role": "assistant", "content": [
            {"type": "text", "text": f"Vou buscar precedentes de {NOME}."},
            {"type": "tool_use", "id": "t1", "name": "buscar_precedentes",
             "input": {"consulta": f"dano moral {NOME} CPF {CPF}", "n": 3}},
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1",
             "content": f"Precedente citando {NOME} e o CPF {CPF}."},
        ]},
    ]


class TestBarreiraAgenticaPseudonimiza:
    """_pseudonimizar_agentico: extrai texto de todos os slots, reescreve
    pseudonimizado numa DEEP COPY (original intacto), com mapa reversível."""

    def test_extrai_todos_os_slots_e_nao_vaza_pii(self):
        from app.services import ai_gateway
        from app.services.ai.sanitization_policy import ModoSanitizacao
        from app.services.ai.pseudonymizer import reidratar

        msgs = _historico_com_pii()
        envio, residual, mapa = ai_gateway._pseudonimizar_agentico(
            msgs, ModoSanitizacao.EXTERNO_PSEUDONIMIZADO, {"cliente": [NOME]},
        )
        dump = str(envio)
        assert residual == []
        # (a) nenhuma PII real no que iria ao provider (inclui tool_result e input).
        assert NOME not in dump, "nome vazou para o envio"
        assert CPF not in dump, "CPF vazou para o envio"
        # (b) marcadores CONSISTENTES: mesma entidade → mesmo índice.
        assert "[CLIENTE_1]" in dump and "[CLIENTE_2]" not in dump
        assert "[CPF_1]" in dump and "[CPF_2]" not in dump
        # (c) original NÃO mutado (espaço real preservado por deep copy).
        assert NOME in str(msgs) and CPF in str(msgs)
        # (d) mapa reverte 1:1.
        assert reidratar("sobre [CLIENTE_1] e [CPF_1]", mapa) == f"sobre {NOME} e {CPF}"

    def test_tool_use_input_aninhado_nao_vaza_pii(self):
        """S2: PII em object/array ANINHADO de tool_use.input também é
        pseudonimizada (extração recursiva) e reidratada recursivamente."""
        from app.services import ai_gateway
        from app.services.ai.sanitization_policy import ModoSanitizacao

        msgs = [{"role": "assistant", "content": [
            {"type": "tool_use", "id": "x", "name": "t", "input": {
                "obj": {"cpf": f"CPF {CPF}"},
                "arr": [f"{NOME} citado", {"nome": NOME}],
            }},
        ]}]
        envio, residual, mapa = ai_gateway._pseudonimizar_agentico(
            msgs, ModoSanitizacao.EXTERNO_PSEUDONIMIZADO, {"cliente": [NOME]},
        )
        dump = str(envio)
        assert residual == []
        assert NOME not in dump and CPF not in dump
        # Reidratação RECURSIVA reverte o input aninhado.
        inp = {"obj": {"cpf": "[CPF_1]"}, "arr": ["[CLIENTE_1] citado", {"nome": "[CLIENTE_1]"}]}
        ai_gateway._reidratar_recursivo(inp, mapa)
        assert inp["obj"]["cpf"] == CPF
        assert inp["arr"][0] == f"{NOME} citado" and inp["arr"][1]["nome"] == NOME

    async def test_chat_agentico_nao_vaza_pii_e_reidrata(self, s, monkeypatch):
        """Round-trip do turno: mocka só o provider de baixo nível (chat_tools).
        A PII do histórico NÃO chega ao provider; text e tool_use.input voltam
        reidratados; text_para_log fica PSEUDONIMIZADO (vai ao AILog)."""
        from app.services import ai_gateway
        from app.services.providers import anthropic_provider

        capturado: dict = {}

        async def fake_chat_tools(messages_envio, model, max_tokens, tools):
            capturado["dump"] = str(messages_envio)
            capturado["tools"] = tools
            # O modelo raciocina SÓ sobre os marcadores e devolve marcadores.
            return {
                "text": "Minuta para [CLIENTE_1] (CPF [CPF_1]).",
                "tool_calls": [{
                    "id": "z", "name": "gerar_minuta_peca",
                    "input": {"tipo": "peça", "instrucoes": "defesa de [CLIENTE_1]"},
                }],
                "stop_reason": "tool_use",
                "usage": {"model": model, "input_tokens": 5, "output_tokens": 7},
            }

        monkeypatch.setattr(anthropic_provider, "chat_tools", fake_chat_tools)

        tools = [{"name": "gerar_minuta_peca", "description": "x",
                  "input_schema": {"type": "object"}}]
        r = await ai_gateway.chat_agentico(
            _historico_com_pii(), tools, task_type="estrategia",
            entidades={"cliente": [NOME]},
        )
        # (a) provider externo recebeu SÓ marcadores — nenhuma PII real vazou.
        assert NOME not in capturado["dump"], "nome vazou ao provider"
        assert CPF not in capturado["dump"], "CPF vazou ao provider"
        assert "[CLIENTE_1]" in capturado["dump"] and "[CPF_1]" in capturado["dump"]
        assert capturado["tools"] == tools  # tools repassadas intactas
        # (b) resposta ao chamador REIDRATADA (text + tool_use.input).
        assert r["text"] == f"Minuta para {NOME} (CPF {CPF})."
        assert r["tool_calls"][0]["input"]["instrucoes"] == f"defesa de {NOME}"
        # (c) text_para_log PSEUDONIMIZADO — nunca PII real no log.
        assert r["text_para_log"] == "Minuta para [CLIENTE_1] (CPF [CPF_1])."
        assert NOME not in r["text_para_log"] and CPF not in r["text_para_log"]
        assert r["provider"] == "anthropic"
        assert r["stop_reason"] == "tool_use"

    async def test_chat_agentico_modo_local_completo_bloqueia(self, s, monkeypatch):
        """S1: quando o chamador passa modo LOCAL_COMPLETO (sigilo da ÁREA), o
        turno agêntico bloqueia (sem provider local com tool-use) — nunca externo."""
        from app.services import ai_gateway
        from app.services.ai.sanitization_policy import ModoSanitizacao

        with pytest.raises(RuntimeError):
            await ai_gateway.chat_agentico(
                [{"role": "user", "content": "x"}], [], task_type="estrategia",
                modo_sanitizacao=ModoSanitizacao.LOCAL_COMPLETO,
            )


# ══════════════════════════════════════════════════════════════════════════════
# 2. anthropic_provider.chat_tools — tool-use nativo (parse de blocos).
# ══════════════════════════════════════════════════════════════════════════════

def _bloco(**kw):
    return SimpleNamespace(**kw)


class _FakeMessages:
    def __init__(self, captured, resp):
        self._captured, self._resp = captured, resp

    def create(self, **kwargs):
        self._captured.update(kwargs)
        return self._resp


class _FakeClient:
    def __init__(self, captured, resp):
        self.messages = _FakeMessages(captured, resp)


def _resp_fake(content, stop_reason="tool_use", inp=10, out=20):
    return SimpleNamespace(
        content=content, stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=inp, output_tokens=out,
                              cache_read_input_tokens=0, cache_creation_input_tokens=0),
    )


class TestChatTools:
    async def test_parse_text_tooluse_ignora_thinking(self, s, monkeypatch):
        from app.services.providers import anthropic_provider
        captured: dict = {}
        resp = _resp_fake([
            _bloco(type="thinking", thinking="raciocínio interno oculto"),
            _bloco(type="text", text="Deixe-me buscar. "),
            _bloco(type="text", text="Segundo trecho."),
            _bloco(type="tool_use", id="tu1", name="buscar_precedentes",
                   input={"consulta": "dano moral"}),
        ], stop_reason="tool_use")
        monkeypatch.setattr(anthropic_provider, "_get_client",
                            lambda: _FakeClient(captured, resp))

        tools = [{"name": "buscar_precedentes", "description": "x",
                  "input_schema": {"type": "object"}}]
        out = await anthropic_provider.chat_tools(
            [{"role": "system", "content": "sys"}, {"role": "user", "content": "oi"}],
            "claude-opus-4-8", 4096, tools,
        )
        # text junta blocos text; thinking é IGNORADO.
        assert out["text"] == "Deixe-me buscar. Segundo trecho."
        assert "oculto" not in out["text"]
        # tool_use parseado (id/name/input); thinking não vira tool_call.
        assert out["tool_calls"] == [{"id": "tu1", "name": "buscar_precedentes",
                                      "input": {"consulta": "dano moral"}}]
        assert out["stop_reason"] == "tool_use"
        assert out["usage"]["input_tokens"] == 10 and out["usage"]["output_tokens"] == 20
        # tools repassadas ao provider; system vai como bloco cacheável.
        assert captured["tools"] == tools
        assert captured["system"][0]["text"] == "sys"
        # Modelo MODERNO: sem temperature; thinking adaptativo. M3: no caminho de
        # tool-use NÃO se força o piso 8192 (turnos curtos) — respeita o teto duro
        # do chamador (mt = min(4096, ANTHROPIC_MAX_TOKENS)).
        assert "temperature" not in captured
        assert captured["extra_body"]["thinking"]["type"] == "adaptive"
        assert captured["max_tokens"] == min(4096, int(s.ANTHROPIC_MAX_TOKENS))

    async def test_modelo_legado_sem_extrabody_respeita_teto(self, s, monkeypatch):
        from app.services.providers import anthropic_provider
        captured: dict = {}
        resp = _resp_fake([_bloco(type="text", text="ok")], stop_reason="end_turn")
        monkeypatch.setattr(anthropic_provider, "_get_client",
                            lambda: _FakeClient(captured, resp))
        out = await anthropic_provider.chat_tools(
            [{"role": "user", "content": "oi"}], "claude-3-5-sonnet-20240620", 100, [],
        )
        assert out["text"] == "ok" and out["tool_calls"] == []
        assert out["stop_reason"] == "end_turn"
        assert "extra_body" not in captured
        assert "temperature" not in captured
        assert captured["max_tokens"] == min(100, int(s.ANTHROPIC_MAX_TOKENS))

    async def test_provider_desabilitado_erro(self, s, monkeypatch):
        from app.services.providers import anthropic_provider
        monkeypatch.setattr(s, "ANTHROPIC_ENABLED", False)
        with pytest.raises(RuntimeError):
            await anthropic_provider.chat_tools(
                [{"role": "user", "content": "oi"}], "claude-opus-4-8", 4096, [],
            )


# ══════════════════════════════════════════════════════════════════════════════
# 3. Registry / permissions — 13 tools (4 originais + 9 dos motores, FASE 6);
#    HITL nas escritas; filtro por papel + L9.
# ══════════════════════════════════════════════════════════════════════════════

_TOOLS_LEITURA = {
    "buscar_precedentes", "ler_dossie",
    # FASE 6 — motores determinísticos (leitura, sem HITL).
    "montar_cronologia", "identificar_rito_e_fase", "detectar_providencias",
    "calcular_prazo", "consultar_tabela_oab", "ler_checklist_peca",
    "classificar_area",
}
_TOOLS_ESCRITA = {
    "gerar_minuta_peca", "registrar_nota_caso",
    # FASE 6 — escritas dos motores (HITL obrigatório).
    "criar_prazo_confirmado", "gerar_kit_documental",
}
_TOOLS_ESPERADAS = _TOOLS_LEITURA | _TOOLS_ESCRITA


class TestRegistryGlobal:
    def test_tools_registradas_e_visiveis(self):
        # Import REGISTRA as tools via decoradores (idempotente).
        from app.services.ai.agent.tools import leitura, escrita, motores  # noqa: F401
        from app.services.ai.agent.tools.registry import REGISTRY
        assert REGISTRY.nomes_visiveis("advogado") == _TOOLS_ESPERADAS
        schemas = REGISTRY.schemas("advogado")
        assert len(schemas) == len(_TOOLS_ESPERADAS)
        for sch in schemas:
            assert set(sch) == {"name", "description", "input_schema"}

    def test_l9_escrita_restrita_a_papeis_senior(self):
        """L9: as tools de ESCRITA só são visíveis a papéis sênior; papéis
        operacionais (ex.: auxiliar) veem SÓ as de leitura."""
        from app.services.ai.agent.tools import leitura, escrita, motores  # noqa: F401
        from app.services.ai.agent.tools.registry import REGISTRY
        for papel in ("superadmin", "admin", "socio", "advogado"):
            assert REGISTRY.nomes_visiveis(papel) == _TOOLS_ESPERADAS
        # Papel não-sênior → só leitura (escrita filtrada).
        assert REGISTRY.nomes_visiveis("auxiliar") == _TOOLS_LEITURA
        assert REGISTRY.nomes_visiveis("estagiario") == _TOOLS_LEITURA

    def test_leitura_sem_confirmacao_escrita_com_hitl(self):
        from app.services.ai.agent.tools import leitura, escrita, motores  # noqa: F401
        from app.services.ai.agent.permissions import requer_confirmacao, pode_ver_tool
        # LEITURA → automática.
        for nome in _TOOLS_LEITURA:
            assert requer_confirmacao(nome) is False, nome
        # ESCRITA → HITL (confirmação humana).
        for nome in _TOOLS_ESCRITA:
            assert requer_confirmacao(nome) is True, nome
        # Facade de visibilidade.
        assert pode_ver_tool("buscar_precedentes", "advogado") is True
        # Tool inexistente nunca requer confirmação (fail-safe).
        assert requer_confirmacao("inexistente") is False


class TestRegistryFiltroPorPapel:
    """Lógica do _Registry em ISOLAMENTO (instância fresca, sem tocar o singleton
    global): schemas(role) filtra por papel e executar barra papel/tool inválidos."""

    def _reg(self):
        from app.services.ai.agent.tools.registry import _Registry, ToolSpec

        async def h_all(args, ctx):
            return {"ok": "all"}

        async def h_admin(args, ctx):
            return {"ok": "admin", "args": args}

        reg = _Registry()
        reg.registrar(ToolSpec("t_all", "d", {"type": "object"}, h_all, False, None))
        reg.registrar(ToolSpec("t_admin", "d", {"type": "object"}, h_admin, True, ("admin",)))
        return reg

    def test_schemas_e_nomes_filtram_por_papel(self):
        reg = self._reg()
        # roles=None → visível a qualquer papel; roles=("admin",) → só admin.
        assert reg.nomes_visiveis("advogado") == {"t_all"}
        assert reg.nomes_visiveis("admin") == {"t_all", "t_admin"}
        assert {sch["name"] for sch in reg.schemas("advogado")} == {"t_all"}
        assert reg.requer_confirmacao("t_admin") is True
        assert reg.requer_confirmacao("t_all") is False

    async def test_executar_barra_papel_e_tool_desconhecida(self):
        from app.services.ai.agent.tools.context import AgentContext
        reg = self._reg()
        ctx_adv = AgentContext(db=None, user=None, case_id="c1", client_id=None, role="advogado")
        ctx_admin = AgentContext(db=None, user=None, case_id="c1", client_id=None, role="admin")
        # Defense-in-depth: papel sem visibilidade é BARRADO na execução.
        with pytest.raises(PermissionError):
            await reg.executar("t_admin", {}, ctx_adv)
        # Papel correto executa o handler.
        assert (await reg.executar("t_admin", {"x": 1}, ctx_admin)) == {
            "ok": "admin", "args": {"x": 1}}
        # Ferramenta desconhecida → ValueError.
        with pytest.raises(ValueError):
            await reg.executar("inexistente", {}, ctx_adv)

    def test_registro_idempotente_mantem_primeira_definicao(self):
        from app.services.ai.agent.tools.registry import ToolSpec
        reg = self._reg()

        async def h2(args, ctx):
            return {"ok": "outro"}

        # Re-registrar o MESMO nome é ignorado (mantém a 1ª definição).
        reg.registrar(ToolSpec("t_all", "d2", {"type": "object"}, h2, True, None))
        assert reg.get("t_all").requer_confirmacao is False
        assert reg.get("t_all").description == "d"


# ══════════════════════════════════════════════════════════════════════════════
# 4. Loop rodar_agente — HITL (H1), conclusão, tetos (L6/Sug.2), stop_reason
#    (L7), área sigilosa (S1), degradação (M5), erros seguros.
# ══════════════════════════════════════════════════════════════════════════════

def _user():
    return SimpleNamespace(id="u1", role=SimpleNamespace(value="advogado"))


def _turno(text, tool_calls, stop_reason, *, text_log=None):
    return {
        "text": text,
        "text_para_log": text_log if text_log is not None else text,
        "tool_calls": tool_calls,
        "stop_reason": stop_reason,
        "usage": {"model": "claude-opus-4-8", "input_tokens": 3, "output_tokens": 4},
        "provider": "anthropic", "model": "claude-opus-4-8",
    }


@pytest.fixture
def loop_env(s, monkeypatch):
    """Mocka TODA borda externa do loop (DB/rede/Redis): ownership, entidades,
    AILog, gate de citações e o store HITL (hitl_state) em memória. chat_agentico
    e REGISTRY.executar são mockados por teste."""
    import app.services.ai.agent.loop as loop
    import app.services.ai_gateway as gw
    import app.services.ai_guard as guard
    import app.services.ai.entidades_caso as ent
    import app.services.ai.core.response_validator as rv
    import app.services.ai.agent.hitl_state as hitl
    from app.services.ai.agent.tools.registry import REGISTRY

    ailog_calls: list[dict] = []
    hitl_store: dict[str, dict] = {}

    async def fake_acesso(db, user, case_id):
        return SimpleNamespace(client_id="c1", area=SimpleNamespace(value="civil"))

    async def fake_entidades(db, case_id):
        return {"cliente": [NOME]}

    async def fake_ailog(db, **kw):
        ailog_calls.append(kw)
        return "log-id"

    async def fake_validar(db, conteudo, **kw):
        return {"conteudo": conteudo, "alertas": [], "revisao_obrigatoria": False}

    async def fake_salvar(estado, ttl=None):
        tok = f"tok-{len(hitl_store) + 1}"
        hitl_store[tok] = estado
        return tok

    async def fake_carregar(token):
        return hitl_store.pop(token, None)

    monkeypatch.setattr(loop, "verificar_acesso_caso", fake_acesso)
    monkeypatch.setattr(ent, "entidades_do_caso", fake_entidades)
    monkeypatch.setattr(guard, "registrar_ai_log", fake_ailog)
    monkeypatch.setattr(rv, "validar", fake_validar)
    monkeypatch.setattr(hitl, "salvar", fake_salvar)
    monkeypatch.setattr(hitl, "carregar", fake_carregar)

    return SimpleNamespace(
        loop=loop, gw=gw, registry=REGISTRY, ailog_calls=ailog_calls,
        hitl=hitl, hitl_store=hitl_store, monkeypatch=monkeypatch,
    )


def _coletor():
    eventos: list[tuple] = []

    def on_event(tipo, dados):
        eventos.append((tipo, dados))

    return eventos, on_event


def _hash(nome, args):
    from app.services.ai.agent.hitl_state import hash_tool_call
    return hash_tool_call(nome, args)


class TestLoopHITL:
    async def test_write_tool_nao_aprovada_pausa_com_token_e_hash(self, loop_env):
        """HITL (H1): write-tool sem aprovação PAUSA (pendente_confirmacao) com
        `token` (Redis) e `args_hash` vinculado aos ARGS; NUNCA executa."""
        args = {"tipo": "contestação", "instrucoes": "defesa"}
        loop_env.monkeypatch.setattr(
            loop_env.gw, "chat_agentico",
            lambda *a, **k: _async(_turno(
                "Vou gerar a minuta.",
                [{"id": "w1", "name": "gerar_minuta_peca", "input": args}],
                "tool_use")),
        )
        executadas: list[str] = []

        async def spy_exec(name, a, ctx):
            executadas.append(name)
            return {"ok": True}

        loop_env.monkeypatch.setattr(loop_env.registry, "executar", spy_exec)

        eventos, on_event = _coletor()
        r = await loop_env.loop.rodar_agente(
            db=None, user=_user(), case_id="c1", mensagem="Faça a defesa",
            on_event=on_event,
        )
        assert r["status"] == "pendente_confirmacao"
        assert r["ferramenta"] == "gerar_minuta_peca"
        assert r["args"] == args
        assert r["args_hash"] == _hash("gerar_minuta_peca", args)
        assert r["token"] == "tok-1"                 # estado persistido no Redis
        assert r["transcricao_parcial"]              # traz os passos parciais
        assert executadas == []                      # NUNCA executou a write-tool
        assert any(t == "confirmacao_requerida" for t, _ in eventos)
        assert len(loop_env.ailog_calls) == 1
        # Estado retomável guardado com o tool_call EXATO pendente.
        assert loop_env.hitl_store["tok-1"]["pending"]["input"] == args

    async def test_retomar_aprovar_executa_exatamente_e_conclui(self, loop_env):
        """H1: ao retomar com token+aprovar, executa EXATAMENTE o tool_call
        persistido (mesmos args) e CONTINUA — sem re-rodar os passos anteriores."""
        args = {"tipo": "peça", "instrucoes": "defesa original"}
        turnos = iter([
            _turno("Gerando.", [{"id": "w1", "name": "gerar_minuta_peca", "input": args}], "tool_use"),
            _turno("Minuta pronta (rascunho).", [], "end_turn"),
        ])
        chamadas = {"n": 0}

        def _chat(*a, **k):
            chamadas["n"] += 1
            return _async(next(turnos))

        loop_env.monkeypatch.setattr(loop_env.gw, "chat_agentico", _chat)
        executadas: list[tuple] = []

        async def spy_exec(name, a, ctx):
            executadas.append((name, a))
            return {"conteudo": "minuta", "is_rascunho": True}

        loop_env.monkeypatch.setattr(loop_env.registry, "executar", spy_exec)

        # 1) primeiro turno → pausa com token.
        r1 = await loop_env.loop.rodar_agente(
            db=None, user=_user(), case_id="c1", mensagem="Gere a peça")
        assert r1["status"] == "pendente_confirmacao" and r1["token"] == "tok-1"
        assert executadas == []          # nada executado ainda
        assert chamadas["n"] == 1

        # 2) retoma aprovando → executa EXATAMENTE os args aprovados e conclui.
        r2 = await loop_env.loop.rodar_agente(
            db=None, user=_user(), case_id="c1",
            retomar_token="tok-1", decisao="aprovar")
        assert r2["status"] == "ok" and r2["is_rascunho"] is True
        assert executadas == [("gerar_minuta_peca", args)]   # args EXATOS
        assert chamadas["n"] == 2         # só +1 chamada (continuação) → SEM re-run

    async def test_retomar_recusar_nao_executa(self, loop_env):
        """H1: retomar com 'recusar' NÃO executa a write-tool; segue e conclui."""
        args = {"tipo": "peça", "instrucoes": "x"}
        turnos = iter([
            _turno("Gerando.", [{"id": "w1", "name": "gerar_minuta_peca", "input": args}], "tool_use"),
            _turno("Sem a minuta, segue a análise.", [], "end_turn"),
        ])
        loop_env.monkeypatch.setattr(
            loop_env.gw, "chat_agentico", lambda *a, **k: _async(next(turnos)))
        executadas: list[str] = []

        async def spy_exec(name, a, ctx):
            executadas.append(name)
            return {"ok": True}

        loop_env.monkeypatch.setattr(loop_env.registry, "executar", spy_exec)

        r1 = await loop_env.loop.rodar_agente(
            db=None, user=_user(), case_id="c1", mensagem="Gere a peça")
        assert r1["status"] == "pendente_confirmacao"
        eventos, on_event = _coletor()
        r2 = await loop_env.loop.rodar_agente(
            db=None, user=_user(), case_id="c1",
            retomar_token="tok-1", decisao="recusar", on_event=on_event)
        assert r2["status"] == "ok"
        assert executadas == []                    # recusada → nunca executou
        assert any(t == "recusado" for t, _ in eventos)

    async def test_retomar_token_expirado_erro_seguro(self, loop_env):
        """Token inexistente/expirado (Redis) → erro seguro, sem executar nada."""
        r = await loop_env.loop.rodar_agente(
            db=None, user=_user(), case_id="c1",
            retomar_token="inexistente", decisao="aprovar")
        assert r == {"status": "erro", "detalhe": "sessao_expirada"}

    async def test_fallback_hash_casa_executa(self, loop_env):
        """Sem Redis (salvar→None), a aprovação por HASH (nome+args) permite a
        re-execução: o loop re-roda e só executa se o tool_call casar o hash."""
        async def salvar_none(estado, ttl=None):
            return None

        loop_env.monkeypatch.setattr(loop_env.hitl, "salvar", salvar_none)
        args = {"descricao": "nota aprovada"}
        # write → write → conclusão (1ª chamada pausa; no re-run executa e conclui).
        turnos = iter([
            _turno("Nota?", [{"id": "n1", "name": "registrar_nota_caso", "input": args}], "tool_use"),
            _turno("Nota?", [{"id": "n1", "name": "registrar_nota_caso", "input": args}], "tool_use"),
            _turno("Nota registrada (rascunho).", [], "end_turn"),
        ])
        loop_env.monkeypatch.setattr(
            loop_env.gw, "chat_agentico", lambda *a, **k: _async(next(turnos)))
        executadas: list[tuple] = []

        async def spy_exec(name, a, ctx):
            executadas.append((name, a))
            return {"registrado": True}

        loop_env.monkeypatch.setattr(loop_env.registry, "executar", spy_exec)

        # 1) pausa (Redis down → token None, mas devolve args_hash).
        r1 = await loop_env.loop.rodar_agente(
            db=None, user=_user(), case_id="c1", mensagem="Registre a nota")
        assert r1["status"] == "pendente_confirmacao" and r1["token"] is None
        h = r1["args_hash"]
        assert h == _hash("registrar_nota_caso", args)
        assert executadas == []
        # 2) re-roda enviando o hash aprovado → executa (casou) e conclui.
        r2 = await loop_env.loop.rodar_agente(
            db=None, user=_user(), case_id="c1", mensagem="Registre a nota",
            aprovacoes_hash={h})
        assert r2["status"] == "ok"
        assert executadas == [("registrar_nota_caso", args)]

    async def test_aprovacao_hash_e_one_shot_repeticao_pausa_de_novo(self, loop_env):
        """Item 7 (auditoria): a aprovação por hash vale para UMA execução — o
        hash é CONSUMIDO na primeira write executada; chamada repetida IDÊNTICA
        pausa DE NOVO (nova aprovação humana), nunca executa em série."""
        args = {"descricao": "nota aprovada"}
        h = _hash("registrar_nota_caso", args)
        turnos = iter([
            _turno("Nota 1", [{"id": "n1", "name": "registrar_nota_caso",
                               "input": args}], "tool_use"),
            _turno("Nota 2 (idêntica)", [{"id": "n2", "name": "registrar_nota_caso",
                                          "input": args}], "tool_use"),
        ])
        loop_env.monkeypatch.setattr(
            loop_env.gw, "chat_agentico", lambda *a, **k: _async(next(turnos)))
        executadas: list[tuple] = []

        async def spy_exec(name, a, ctx):
            executadas.append((name, a))
            return {"registrado": True}

        loop_env.monkeypatch.setattr(loop_env.registry, "executar", spy_exec)

        r = await loop_env.loop.rodar_agente(
            db=None, user=_user(), case_id="c1", mensagem="Registre duas vezes",
            aprovacoes_hash={h})
        # 1ª execução consumiu o hash; a repetição idêntica PAUSOU de novo.
        assert executadas == [("registrar_nota_caso", args)]
        assert r["status"] == "pendente_confirmacao"
        assert r["args_hash"] == h

    async def test_fallback_hash_diverge_recusa(self, loop_env):
        """H1: se o modelo gerar ARGS diferentes dos aprovados, o hash não casa →
        NÃO executa (recusa segura), mesmo com um hash aprovado presente."""
        loop_env.monkeypatch.setattr(
            loop_env.gw, "chat_agentico",
            lambda *a, **k: _async(_turno(
                "Nota?",
                [{"id": "n1", "name": "registrar_nota_caso",
                  "input": {"descricao": "OUTRA nota não aprovada"}}],
                "tool_use")),
        )
        executadas: list[str] = []

        async def spy_exec(name, a, ctx):
            executadas.append(name)
            return {"registrado": True}

        loop_env.monkeypatch.setattr(loop_env.registry, "executar", spy_exec)

        # Hash aprovado é de OUTROS args → não casa com o que o modelo gerou.
        h_aprovado = _hash("registrar_nota_caso", {"descricao": "nota aprovada"})
        r = await loop_env.loop.rodar_agente(
            db=None, user=_user(), case_id="c1", mensagem="Registre",
            aprovacoes_hash={h_aprovado})
        assert r["status"] == "pendente_confirmacao"   # pausou de novo
        assert executadas == []                        # args divergentes → não executou


class TestLoopConclusao:
    async def test_sem_tooluse_conclui_ok_rascunho(self, loop_env):
        loop_env.monkeypatch.setattr(
            loop_env.gw, "chat_agentico",
            lambda *a, **k: _async(_turno(
                f"Resposta sobre {NOME}.", [], "end_turn",
                text_log="Resposta sobre [CLIENTE_1].")),
        )
        eventos, on_event = _coletor()
        r = await loop_env.loop.rodar_agente(
            db=None, user=_user(), case_id="c1", mensagem="Resuma", on_event=on_event,
        )
        assert r["status"] == "ok"
        assert r["is_rascunho"] is True
        assert r["resposta"] == f"Resposta sobre {NOME}."   # reidratado ao chamador
        assert r["revisao_obrigatoria"] is False and r["alertas"] == []
        assert any(t == "final" for t, _ in eventos)
        # LGPD: o AILog recebeu a versão PSEUDONIMIZADA (nunca o nome real).
        assert len(loop_env.ailog_calls) == 1
        assert loop_env.ailog_calls[0]["resposta"] == "Resposta sobre [CLIENTE_1]."
        assert NOME not in loop_env.ailog_calls[0]["resposta"]

    async def test_read_tool_executa_sem_pausar_e_conclui(self, loop_env):
        """Tool de LEITURA roda automaticamente (sem HITL); o loop continua e
        conclui — comprova que só ESCRITA pausa."""
        turnos = iter([
            _turno("Buscando.", [{"id": "r1", "name": "buscar_precedentes",
                                  "input": {"consulta": "dano moral"}}], "tool_use"),
            _turno("Conclusão fundamentada.", [], "end_turn"),
        ])
        loop_env.monkeypatch.setattr(
            loop_env.gw, "chat_agentico", lambda *a, **k: _async(next(turnos)))
        executadas: list[str] = []

        async def spy_exec(name, args, ctx):
            executadas.append(name)
            return {"total": 0, "trechos": []}

        loop_env.monkeypatch.setattr(loop_env.registry, "executar", spy_exec)

        r = await loop_env.loop.rodar_agente(
            db=None, user=_user(), case_id="c1", mensagem="Fundamente",
        )
        assert r["status"] == "ok"
        assert executadas == ["buscar_precedentes"]  # leitura auto-executada
        assert len(r["passos"]) == 2                 # 1 turno com tool + 1 conclusão


class TestLoopStopReason:
    async def test_max_tokens_conclui_com_aviso_sem_executar_tool(self, loop_env):
        """L7: stop_reason=max_tokens NÃO conclui vazio nem executa tool
        possivelmente truncada; conclui com aviso de truncação."""
        loop_env.monkeypatch.setattr(
            loop_env.gw, "chat_agentico",
            lambda *a, **k: _async(_turno(
                "Análise parcial",
                [{"id": "t", "name": "buscar_precedentes", "input": {"consulta": "x"}}],
                "max_tokens")),
        )
        executadas: list[str] = []

        async def spy_exec(name, args, ctx):
            executadas.append(name)
            return {"total": 0}

        loop_env.monkeypatch.setattr(loop_env.registry, "executar", spy_exec)

        r = await loop_env.loop.rodar_agente(
            db=None, user=_user(), case_id="c1", mensagem="x")
        assert r["status"] == "ok"
        assert executadas == []                       # tool truncada NÃO executada
        assert any("max_tokens" in a for a in r["alertas"])
        assert "parcial" in r["resposta"]

    async def test_pause_turn_continua_e_conclui(self, loop_env):
        """L7: stop_reason=pause_turn → reanexa o parcial e CONTINUA (não conclui)."""
        turnos = iter([
            _turno("pensando…", [], "pause_turn"),
            _turno("Conclusão final.", [], "end_turn"),
        ])
        loop_env.monkeypatch.setattr(
            loop_env.gw, "chat_agentico", lambda *a, **k: _async(next(turnos)))
        r = await loop_env.loop.rodar_agente(
            db=None, user=_user(), case_id="c1", mensagem="x")
        assert r["status"] == "ok"
        assert r["resposta"] == "Conclusão final."
        assert len(r["passos"]) == 2      # pausou 1x e continuou


class TestLoopTetos:
    async def test_teto_de_passos_encerra_com_aviso(self, loop_env):
        """L6/L7: modelo que SEMPRE pede tool (de leitura) → encerra no teto
        de passos com aviso, sem loop infinito. (Tool de LEITURA: aprovação de
        escrita agora é one-shot e pausaria na repetição — HITL, item 7.)"""
        loop_env.monkeypatch.setattr(get_settings(), "AI_AGENT_MAX_STEPS", 3)
        args = {"consulta": "dano moral"}
        contador = {"n": 0}

        def _chat(*a, **k):
            contador["n"] += 1
            return _async(_turno(
                f"passo {contador['n']}",
                [{"id": f"t{contador['n']}", "name": "buscar_precedentes", "input": args}],
                "tool_use"))

        loop_env.monkeypatch.setattr(loop_env.gw, "chat_agentico", _chat)

        async def spy_exec(name, a, ctx):
            return {"total": 0}

        loop_env.monkeypatch.setattr(loop_env.registry, "executar", spy_exec)

        r = await loop_env.loop.rodar_agente(
            db=None, user=_user(), case_id="c1", mensagem="loop")
        assert r["status"] == "ok"
        assert len(r["passos"]) == 3            # respeitou o teto (não infinito)
        assert contador["n"] == 3               # chat_agentico chamado exatamente 3x
        assert any("teto de passos" in a for a in r["alertas"])
        assert "orçamento" in r["resposta"]     # fallback de parada por orçamento

    async def test_teto_de_custo_encerra_com_aviso(self, loop_env):
        """Sugestão 2: acumula custo por turno; ao exceder AI_AGENT_MAX_CUSTO_BRL,
        o loop encerra com aviso de custo (igual ao teto de tokens)."""
        loop_env.monkeypatch.setattr(get_settings(), "AI_AGENT_MAX_CUSTO_BRL", 0.01)
        # Custo alto por turno (independente da tabela de preços real).
        loop_env.monkeypatch.setattr(loop_env.loop, "_custo_turno", lambda resp: 0.05)
        loop_env.monkeypatch.setattr(
            loop_env.gw, "chat_agentico",
            lambda *a, **k: _async(_turno(
                "Buscando.", [{"id": "r", "name": "buscar_precedentes",
                               "input": {"consulta": "x"}}], "tool_use")),
        )

        async def spy_exec(name, a, ctx):
            return {"total": 0}

        loop_env.monkeypatch.setattr(loop_env.registry, "executar", spy_exec)

        r = await loop_env.loop.rodar_agente(
            db=None, user=_user(), case_id="c1", mensagem="loop")
        assert r["status"] == "ok"
        assert len(r["passos"]) == 1                    # parou logo após estourar custo
        assert any("teto de custo" in a for a in r["alertas"])
        assert r["custo_estimado_brl"] == pytest.approx(0.05)


class TestLoopSigiloArea:
    async def test_area_sigilosa_fail_closed(self, loop_env):
        """S1: caso cuja ÁREA é reforçada a LOCAL_COMPLETO → fail-closed. O agente
        aborta ANTES de chamar o provider (nunca envia ao externo) e não loga."""
        st = get_settings()
        loop_env.monkeypatch.setattr(st, "AI_SANITIZATION_MODE_MAP",
                                     '{"criminal":"local_completo"}')

        async def fake_acesso(db, user, case_id):
            return SimpleNamespace(client_id="c1", area=SimpleNamespace(value="criminal"))

        loop_env.monkeypatch.setattr(loop_env.loop, "verificar_acesso_caso", fake_acesso)
        chamou = {"n": 0}

        def _chat(*a, **k):
            chamou["n"] += 1
            return _async(_turno("x", [], "end_turn"))

        loop_env.monkeypatch.setattr(loop_env.gw, "chat_agentico", _chat)
        eventos, on_event = _coletor()
        r = await loop_env.loop.rodar_agente(
            db=None, user=_user(), case_id="c1", mensagem="x", on_event=on_event)
        assert r == {"status": "erro", "detalhe": "caso_sigiloso_exige_ia_local"}
        assert chamou["n"] == 0                  # NUNCA enviou ao provider externo
        assert loop_env.ailog_calls == []        # nada logado
        assert any(t == "erro" for t, _ in eventos)


class TestLoopDegradacaoPII:
    async def test_pii_residual_em_tool_result_degrada_e_continua(self, loop_env):
        """M5: PII residual vinda de tool_result NÃO mata o loop — o trecho é
        redigido e o agente CONTINUA (não aborta com bloqueado_por_pii_lgpd)."""
        from app.services.ai_gateway import _ProviderPulado

        # 1º turno: leitura (executa e anexa tool_result). 2º: _ProviderPulado
        # (residual do tool_result) → degrada e RETENTA → conclui.
        estados = {"passo": 0}

        def _chat(*a, **k):
            estados["passo"] += 1
            if estados["passo"] == 1:
                return _async(_turno("Lendo.", [{"id": "r1", "name": "buscar_precedentes",
                                                  "input": {"consulta": "x"}}], "tool_use"))
            if estados["passo"] == 2:
                raise _ProviderPulado(["PESSOA"])      # residual do tool_result
            return _async(_turno("Conclusão após redigir trecho.", [], "end_turn"))

        loop_env.monkeypatch.setattr(loop_env.gw, "chat_agentico", _chat)

        async def spy_exec(name, a, ctx):
            return {"trechos": [{"trecho": "precedente com nome residual"}]}

        loop_env.monkeypatch.setattr(loop_env.registry, "executar", spy_exec)

        eventos, on_event = _coletor()
        r = await loop_env.loop.rodar_agente(
            db=None, user=_user(), case_id="c1", mensagem="Fundamente", on_event=on_event)
        assert r["status"] == "ok"                       # NÃO abortou
        assert "Conclusão após redigir" in r["resposta"]
        assert any(t == "degradacao" for t, _ in eventos)
        assert any("redigido" in a for a in r["alertas"])


class TestLoopErrosSeguros:
    async def test_barreira_lgpd_pulou_provider_erro_seguro(self, loop_env):
        """chat_agentico levantando _ProviderPulado no PRIMEIRO turno (sem
        tool_result para redigir) → erro SEGURO (bloqueado_por_pii_lgpd), sem
        AILog e sem vazar detalhe cru."""
        from app.services.ai_gateway import _ProviderPulado

        def _chat(*a, **k):
            raise _ProviderPulado(["[CPF_RESIDUAL]"])

        loop_env.monkeypatch.setattr(loop_env.gw, "chat_agentico", _chat)
        eventos, on_event = _coletor()
        r = await loop_env.loop.rodar_agente(
            db=None, user=_user(), case_id="c1", mensagem="x", on_event=on_event,
        )
        assert r == {"status": "erro", "detalhe": "bloqueado_por_pii_lgpd"}
        assert any(t == "erro" for t, _ in eventos)
        assert loop_env.ailog_calls == []  # nada logado quando o provider é pulado

    async def test_excecao_do_provider_vira_erro_com_tipo(self, loop_env):
        def _chat(*a, **k):
            raise RuntimeError("provedor fora do ar")

        loop_env.monkeypatch.setattr(loop_env.gw, "chat_agentico", _chat)
        r = await loop_env.loop.rodar_agente(
            db=None, user=_user(), case_id="c1", mensagem="x",
        )
        # Detalhe é só o TIPO da exceção (sem stack/PII).
        assert r == {"status": "erro", "detalhe": "RuntimeError"}
        assert loop_env.ailog_calls == []


# ══════════════════════════════════════════════════════════════════════════════
# 5. ler_dossie — LEITOR PURO (S3): nenhuma escrita / gerar_dossie.
# ══════════════════════════════════════════════════════════════════════════════

class TestLerDossiePuro:
    def _ctx(self):
        from app.services.ai.agent.tools.context import AgentContext
        return AgentContext(db=None, user=SimpleNamespace(id="u1"), case_id="c1",
                            client_id=None, role="advogado", area="civil")

    async def test_le_ultima_versao_sem_efeito_colateral(self, monkeypatch):
        from app.services.ai.agent.tools import leitura
        from app.services import dossie_service

        async def fake_acesso(db, user, case_id):
            return SimpleNamespace(client_id="c1")

        async def fake_ultimo(db, case_id):
            return SimpleNamespace(versao=3, titulo="Dossiê v3",
                                   conteudo_texto="conteúdo real", conteudo_html=None)

        def _boom(*a, **k):
            raise AssertionError("gerar_dossie NÃO pode ser chamado numa tool de leitura")

        monkeypatch.setattr(leitura, "verificar_acesso_caso", fake_acesso)
        monkeypatch.setattr(dossie_service, "ler_ultimo_dossie", fake_ultimo)
        monkeypatch.setattr(dossie_service, "gerar_dossie", _boom)

        out = await leitura.ler_dossie({}, self._ctx())
        assert out["existe"] is True
        assert out["versao"] == 3 and out["conteudo"] == "conteúdo real"

    async def test_sem_dossie_informa_sem_gerar(self, monkeypatch):
        from app.services.ai.agent.tools import leitura
        from app.services import dossie_service

        async def fake_acesso(db, user, case_id):
            return SimpleNamespace(client_id="c1")

        async def fake_ultimo(db, case_id):
            return None

        def _boom(*a, **k):
            raise AssertionError("gerar_dossie NÃO pode ser chamado numa tool de leitura")

        monkeypatch.setattr(leitura, "verificar_acesso_caso", fake_acesso)
        monkeypatch.setattr(dossie_service, "ler_ultimo_dossie", fake_ultimo)
        monkeypatch.setattr(dossie_service, "gerar_dossie", _boom)

        out = await leitura.ler_dossie({}, self._ctx())
        assert out["existe"] is False and out["conteudo"] == ""
        assert "Nenhum dossiê" in out["nota"]


# ── util: embrulha um valor pronto num awaitable (chat_agentico é async) ───────
async def _async(valor):
    return valor
