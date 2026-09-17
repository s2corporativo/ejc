"""Modo Executivo + prompt caching + busca web (verificação ativa).

Cobre as três entregas do padrão de resposta executivo:
  1. system_prompts/modo_executivo.py contém os marcadores obrigatórios e é um
     MODO selecionável que COMPÕE com os prompts por área (não substitui);
  2. provider Anthropic condiciona o cache_control do bloco system à flag
     AI_PROMPT_CACHING_ENABLED (default True — comportamento atual);
  3. tool web_search só entra no payload com AI_WEB_SEARCH_ENABLED=true
     (default OFF), respeita AI_WEB_SEARCH_MAX_USES, degrada graciosamente se a
     API rejeitar o tool (400 → repete sem tools) e o nº de buscas é reportado
     no usage (metadado de auditoria para AILog/observabilidade).
"""
from __future__ import annotations

import anthropic
import httpx
import pytest

from app.core.config import get_settings
from app.services.providers import anthropic_provider as ap
from app.services import ai_gateway as g
from app.services.system_prompts.modo_executivo import (
    AVISO_RASCUNHO_EXECUTIVO,
    MARCADOR_PENDENTE_VERIFICACAO,
    PROMPT_MODO_EXECUTIVO,
)


# ── Fakes do SDK Anthropic (mesmo padrão de test_anthropic_gateway.py) ────────

class _Bloco:
    def __init__(self, tipo, text="", name=""):
        self.type = tipo
        self.text = text
        self.name = name


class _Usage:
    input_tokens = 100
    output_tokens = 800
    cache_read_input_tokens = 0
    cache_creation_input_tokens = 0


class _Resp:
    def __init__(self, blocos, stop_reason="end_turn"):
        self.content = blocos
        self.usage = _Usage()
        self.stop_reason = stop_reason


class _FakeMessages:
    """create() padrão: grava kwargs e devolve texto simples."""

    def __init__(self, sink, blocos=None):
        self._sink = sink
        self._blocos = blocos

    def create(self, **kwargs):
        self._sink.setdefault("chamadas", []).append(kwargs)
        self._sink["kwargs"] = kwargs
        return _Resp(self._blocos or [_Bloco("text", "resposta")])


def _erro_400() -> anthropic.BadRequestError:
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.BadRequestError(
        "web_search tool not supported",
        response=httpx.Response(400, request=req),
        body=None,
    )


class _FakeMessagesRejeitaTools(_FakeMessages):
    """Rejeita com 400 qualquer chamada COM tools; aceita sem tools."""

    def create(self, **kwargs):
        self._sink.setdefault("chamadas", []).append(kwargs)
        self._sink["kwargs"] = kwargs
        if "tools" in kwargs:
            raise _erro_400()
        return _Resp([_Bloco("text", "resposta degradada sem busca")])


class _FakeClient:
    def __init__(self, messages):
        self.messages = messages


@pytest.fixture()
def sink(monkeypatch):
    box: dict = {}
    monkeypatch.setattr(ap, "_get_client", lambda: _FakeClient(_FakeMessages(box)))
    monkeypatch.setattr(get_settings(), "ANTHROPIC_ENABLED", True)
    return box


# ── 1) Prompt-mestre: marcadores obrigatórios ────────────────────────────────

def test_prompt_modo_executivo_contem_marcadores_obrigatorios():
    p = PROMPT_MODO_EXECUTIVO
    # Rascunho/HITL
    assert AVISO_RASCUNHO_EXECUTIVO in p
    assert "RASCUNHO GERADO POR IA" in p
    # D5 (2026-09-05): "Provimento OAB 205/2021" removido — trata de
    # publicidade, não de vedação de promessa de resultado; "Código de
    # Ética OAB" é a citação que sobra e nunca mais deve reintroduzir 205/2021.
    assert "Código de Ética OAB" in p
    assert "205/2021" not in p
    # Honestidade epistêmica: marcador de verificação pendente
    assert MARCADOR_PENDENTE_VERIFICACAO in p
    assert "PENDENTE DE VERIFICAÇÃO" in p
    # Formato executivo: os 3 blocos
    assert "RESULTADO DIRETO" in p
    assert "OBSERVAÇÕES TÉCNICAS ESSENCIAIS" in p
    assert "PRÓXIMO PASSO" in p
    # Método A→E: lacunas (máx 3 perguntas) e preservação de prova (CPC 381/384)
    assert "3" in p and "pergunta" in p.lower()
    assert "381" in p and "384" in p
    # Limites éticos
    assert "NUNCA prometa" in p
    assert "NUNCA invente" in p


def test_prompt_modo_executivo_exportado_no_pacote():
    from app.services.system_prompts import PROMPT_MODO_EXECUTIVO as exportado
    assert exportado == PROMPT_MODO_EXECUTIVO


def test_nivel_executivo_compoe_sem_substituir_prompt_area():
    """O modo executivo entra como system EXTRA (prepend) — o prompt por área
    original permanece intacto na lista (composição, não substituição)."""
    area = {"role": "system", "content": "PROMPT DA ÁREA TRABALHISTA"}
    user = {"role": "user", "content": "analisar reclamação"}
    out = g._aplicar_nivel([area, user], "executivo")
    assert len(out) == 3
    assert out[0]["role"] == "system"
    assert "MODO EXECUTIVO" in out[0]["content"]
    assert "RESULTADO DIRETO" in out[0]["content"]
    # prompt por área preservado byte a byte
    assert out[1] == area
    assert out[2] == user


def test_nivel_desconhecido_continua_no_op():
    msgs = [{"role": "user", "content": "oi"}]
    assert g._aplicar_nivel(msgs, "inexistente") == msgs


# ── 2) Prompt caching condicionado à flag ────────────────────────────────────

async def test_caching_ligado_envia_cache_control(sink, monkeypatch):
    monkeypatch.setattr(get_settings(), "AI_PROMPT_CACHING_ENABLED", True)
    await ap.chat(
        messages=[{"role": "system", "content": "regras"},
                  {"role": "user", "content": "fatos"}],
        model="claude-opus-4-8", temperature=0.1, max_tokens=1000,
    )
    system = sink["kwargs"]["system"]
    assert isinstance(system, list)
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert system[0]["text"] == "regras"


async def test_caching_desligado_envia_system_string(sink, monkeypatch):
    monkeypatch.setattr(get_settings(), "AI_PROMPT_CACHING_ENABLED", False)
    await ap.chat(
        messages=[{"role": "system", "content": "regras"},
                  {"role": "user", "content": "fatos"}],
        model="claude-opus-4-8", temperature=0.1, max_tokens=1000,
    )
    assert sink["kwargs"]["system"] == "regras"


# ── 3) Busca web (verificação ativa) — flag OFF por default ──────────────────

async def test_web_search_desligado_nao_envia_tools(sink, monkeypatch):
    # Default LIGADO desde 2026-09-05 (decisão do titular); o caminho OFF segue
    # coberto — quem desliga via .env não pode receber o tool.
    monkeypatch.setattr(get_settings(), "AI_WEB_SEARCH_ENABLED", False)
    await ap.chat(
        messages=[{"role": "user", "content": "fatos"}],
        model="claude-opus-4-8", temperature=0.1, max_tokens=1000,
    )
    assert "tools" not in sink["kwargs"]


async def test_web_search_ligado_envia_tool_com_max_uses(sink, monkeypatch):
    monkeypatch.setattr(get_settings(), "AI_WEB_SEARCH_ENABLED", True)
    monkeypatch.setattr(get_settings(), "AI_WEB_SEARCH_MAX_USES", 5)
    await ap.chat(
        messages=[{"role": "user", "content": "fatos"}],
        model="claude-opus-4-8", temperature=0.1, max_tokens=1000,
    )
    tools = sink["kwargs"]["tools"]
    assert tools == [{
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 5,
    }]


async def test_web_search_degrada_gracioso_se_api_rejeitar(monkeypatch):
    """API rejeita o tool (400) → a MESMA chamada repete sem tools e a resposta
    é entregue normalmente (integração externa nunca derruba o fluxo)."""
    box: dict = {}
    monkeypatch.setattr(
        ap, "_get_client", lambda: _FakeClient(_FakeMessagesRejeitaTools(box))
    )
    monkeypatch.setattr(get_settings(), "ANTHROPIC_ENABLED", True)
    monkeypatch.setattr(get_settings(), "AI_WEB_SEARCH_ENABLED", True)
    texto, usage = await ap.chat(
        messages=[{"role": "user", "content": "fatos"}],
        model="claude-opus-4-8", temperature=0.1, max_tokens=1000,
    )
    assert texto == "resposta degradada sem busca"
    assert len(box["chamadas"]) == 2
    assert "tools" in box["chamadas"][0]
    assert "tools" not in box["chamadas"][1]
    assert usage["web_search_requests"] == 0


async def test_web_search_conta_buscas_no_usage(monkeypatch):
    """Blocos server_tool_use/web_search da resposta → usage.web_search_requests
    (metadado que o gateway registra em AILog/observabilidade)."""
    box: dict = {}
    blocos = [
        _Bloco("server_tool_use", name="web_search"),
        _Bloco("web_search_tool_result"),
        _Bloco("text", "com base na busca..."),
    ]
    monkeypatch.setattr(
        ap, "_get_client", lambda: _FakeClient(_FakeMessages(box, blocos))
    )
    monkeypatch.setattr(get_settings(), "ANTHROPIC_ENABLED", True)
    monkeypatch.setattr(get_settings(), "AI_WEB_SEARCH_ENABLED", True)
    texto, usage = await ap.chat(
        messages=[{"role": "user", "content": "fatos"}],
        model="claude-opus-4-8", temperature=0.1, max_tokens=1000,
    )
    assert texto == "com base na busca..."
    assert usage["web_search_requests"] == 1


# ── Review PR #481 — item 1: custo da busca web (cobrado à parte) ────────────

def test_custo_busca_web_brl(monkeypatch):
    from decimal import Decimal
    from app.services.ai_cost import custo_busca_web_brl
    monkeypatch.setenv("USD_BRL_RATE", "5.00")
    assert custo_busca_web_brl(0) == Decimal("0")
    assert custo_busca_web_brl(None) == Decimal("0")
    # 3 buscas × US$10/1000 × R$5,00 = R$0,15
    assert float(custo_busca_web_brl(3)) == pytest.approx(0.15)


async def test_chat_soma_custo_da_busca_no_custo_estimado(monkeypatch):
    """Gateway chat(): custo_estimado_brl = tokens + busca web — é este valor
    que persiste no AILog e alimenta governança/alerta de budget."""
    monkeypatch.setenv("USD_BRL_RATE", "5.00")

    async def _fake_barreira(provider, model, messages, modo, entidades,
                             temperature, max_tokens):
        usage = {
            "model": "claude-opus-4-8", "input_tokens": 0, "output_tokens": 0,
            "web_search_requests": 2,
            "web_search_fontes": [{"titulo": "STJ", "url": "https://stj.jus.br/x"}],
        }
        return "texto", "texto", usage, messages, False

    monkeypatch.setattr(g, "_chamar_com_barreira", _fake_barreira)
    monkeypatch.setattr(
        g, "_resolver_cadeia", lambda *a, **k: [("anthropic", "claude-opus-4-8")]
    )
    resp = await g.chat([{"role": "user", "content": "pergunta"}],
                        task_type="analise_juridica")
    # 0 tokens → custo é só a busca: 2 × US$10/1000 × R$5,00 = R$0,10
    assert resp.custo_estimado_brl == pytest.approx(0.10)
    assert resp.web_search_requests == 2
    assert resp.web_search_fontes == [{"titulo": "STJ", "url": "https://stj.jus.br/x"}]


# ── Review PR #481 — item 2: citações estruturadas da busca ──────────────────

class _Citacao:
    def __init__(self, url, title):
        self.url = url
        self.title = title


async def test_fontes_da_busca_renderizadas_e_no_usage(monkeypatch):
    """Citations dos blocos text NÃO são descartadas: viram seção 'Fontes
    consultadas (busca web):' no texto e lista estruturada no usage (→ AILog)."""
    box: dict = {}
    bloco_texto = _Bloco("text", "Aplicável o CDC (Súmula 297/STJ).")
    bloco_texto.citations = [
        _Citacao("https://stj.jus.br/sumula-297", "Súmula 297 do STJ"),
        _Citacao("https://stj.jus.br/sumula-297", "Súmula 297 do STJ"),  # dup
    ]
    blocos = [_Bloco("server_tool_use", name="web_search"), bloco_texto]
    monkeypatch.setattr(
        ap, "_get_client", lambda: _FakeClient(_FakeMessages(box, blocos))
    )
    monkeypatch.setattr(get_settings(), "ANTHROPIC_ENABLED", True)
    monkeypatch.setattr(get_settings(), "AI_WEB_SEARCH_ENABLED", True)
    texto, usage = await ap.chat(
        messages=[{"role": "user", "content": "fatos"}],
        model="claude-opus-4-8", temperature=0.1, max_tokens=1000,
    )
    assert "Fontes consultadas (busca web):" in texto
    assert "- Súmula 297 do STJ — https://stj.jus.br/sumula-297" in texto
    # dedupe por URL: uma única fonte estruturada no usage
    assert usage["web_search_fontes"] == [
        {"titulo": "Súmula 297 do STJ", "url": "https://stj.jus.br/sumula-297"}
    ]


def test_fontes_rag_busca_web_para_ailog():
    linha = g._fontes_rag_busca_web(
        2, [{"titulo": "Planalto", "url": "https://planalto.gov.br/cdc"}], "anthropic"
    )
    assert "[busca_web] 2 consulta(s)" in linha
    assert "https://planalto.gov.br/cdc" in linha
    assert g._fontes_rag_busca_web(0, [], "anthropic") is None


# ── Review PR #481 — item 3: executivo ignorado em tarefas JSON ──────────────

def test_executivo_ignorado_em_tarefa_de_saida_estruturada():
    """Tarefas com 'SAÍDA OBRIGATÓRIA — JSON' (triagem/prazos/honorarios) são
    mutuamente exclusivas com o formato de prosa do modo executivo: o modo é
    IGNORADO (com aviso em log) e o parse downstream nunca quebra."""
    msgs = [{"role": "system", "content": "PROMPT_TRIAGEM (JSON)"},
            {"role": "user", "content": "relato"}]
    for tarefa_json in ("triagem", "prazos", "honorarios"):
        assert g._aplicar_nivel(msgs, "executivo", task_label=tarefa_json) == msgs
    # Tarefa de prosa → modo aplicado normalmente
    out = g._aplicar_nivel(msgs, "executivo", task_label="analise_juridica")
    assert "MODO EXECUTIVO" in out[0]["content"]
    # Níveis de raciocínio (alto/maximo) NÃO são afetados pela restrição
    out_alto = g._aplicar_nivel(msgs, "alto", task_label="triagem")
    assert len(out_alto) == 3


# ── Review PR #481 — item 4: pause_turn com teto de continuações ─────────────

class _FakeMessagesPause(_FakeMessages):
    """Devolve stop_reason=pause_turn nas N primeiras chamadas; depois termina."""

    def __init__(self, sink, pausas):
        super().__init__(sink)
        self._pausas = pausas

    def create(self, **kwargs):
        self._sink.setdefault("chamadas", []).append(kwargs)
        if self._pausas > 0:
            self._pausas -= 1
            return _Resp([_Bloco("text", "parte ")], stop_reason="pause_turn")
        return _Resp([_Bloco("text", "final")])


async def test_pause_turn_continua_ate_stop_terminal(monkeypatch):
    box: dict = {}
    monkeypatch.setattr(
        ap, "_get_client", lambda: _FakeClient(_FakeMessagesPause(box, pausas=2))
    )
    monkeypatch.setattr(get_settings(), "ANTHROPIC_ENABLED", True)
    texto, usage = await ap.chat(
        messages=[{"role": "user", "content": "fatos"}],
        model="claude-opus-4-8", temperature=0.1, max_tokens=1000,
    )
    # 1 chamada inicial + 2 continuações; texto das partes concatenado
    assert len(box["chamadas"]) == 3
    assert texto == "parte parte final"
    assert "interrompida" not in texto
    # continuação reenvia o turno pausado como assistant
    assert box["chamadas"][1]["messages"][-1]["role"] == "assistant"
    # tokens somados entre as continuações (3 × 100 / 3 × 800)
    assert usage["input_tokens"] == 300
    assert usage["output_tokens"] == 2400


async def test_pause_turn_degrada_gracioso_no_teto(monkeypatch):
    """Sempre pause_turn → 1 inicial + 3 continuações (teto) e degradação
    graciosa: usa o parcial acumulado + aviso, sem levantar erro."""
    box: dict = {}
    monkeypatch.setattr(
        ap, "_get_client", lambda: _FakeClient(_FakeMessagesPause(box, pausas=99))
    )
    monkeypatch.setattr(get_settings(), "ANTHROPIC_ENABLED", True)
    texto, _ = await ap.chat(
        messages=[{"role": "user", "content": "fatos"}],
        model="claude-opus-4-8", temperature=0.1, max_tokens=1000,
    )
    assert len(box["chamadas"]) == 1 + ap._MAX_CONTINUACOES_PAUSE_TURN
    assert texto.startswith("parte parte parte parte")
    assert "Busca web interrompida no limite de continuações" in texto


async def test_web_search_nao_entra_no_caminho_agentico(sink, monkeypatch):
    """chat_tools (loop agêntico) gerencia a própria lista de tools — a busca
    web opt-in NÃO pode ser intercalada nela mesmo com a flag ligada."""
    monkeypatch.setattr(get_settings(), "AI_WEB_SEARCH_ENABLED", True)
    tools_do_loop = [{"name": "ler_dossie", "description": "x",
                      "input_schema": {"type": "object", "properties": {}}}]
    await ap.chat_tools(
        messages=[{"role": "user", "content": "fatos"}],
        model="claude-opus-4-8", max_tokens=1000, tools=tools_do_loop,
    )
    assert sink["kwargs"]["tools"] == tools_do_loop
