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
    def __init__(self, blocos):
        self.content = blocos
        self.usage = _Usage()


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
    # Rascunho/HITL (OAB Provimento 205/2021)
    assert AVISO_RASCUNHO_EXECUTIVO in p
    assert "RASCUNHO GERADO POR IA" in p
    assert "205/2021" in p
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

async def test_web_search_default_off_nao_envia_tools(sink):
    assert get_settings().AI_WEB_SEARCH_ENABLED is False  # default do repo
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
