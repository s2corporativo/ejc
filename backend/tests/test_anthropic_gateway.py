"""Claude como provedor de raciocínio jurídico — provider + roteamento do gateway.

Cobre:
  - provider: modelos modernos não enviam temperature (400 na API) e usam
    adaptive thinking com piso de max_tokens; texto extraído dos blocos certos;
  - provider: Haiku/legado mantém temperature e não envia thinking;
  - gateway: estrategia/elaboracao_peca roteiam para a Claude quando há chave,
    e a pulam (Ollama/Groq) quando não há;
  - tabela de preços corrigida (Opus 4.8 = 5/25, não 15/75).
"""
from __future__ import annotations

from app.services.providers import anthropic_provider as ap
from app.services import ai_gateway as g


# ── Fakes do SDK Anthropic ────────────────────────────────────────────────────

class _Bloco:
    def __init__(self, tipo, text=""):
        self.type = tipo
        self.text = text


class _Usage:
    input_tokens = 100
    output_tokens = 800


class _Resp:
    def __init__(self, blocos):
        self.content = blocos
        self.usage = _Usage()


class _FakeMessages:
    def __init__(self, sink):
        self._sink = sink

    def create(self, **kwargs):
        self._sink["kwargs"] = kwargs
        # simula thinking (texto vazio) + dois blocos de texto
        return _Resp([
            _Bloco("thinking", ""),
            _Bloco("text", "I — SÍNTESE DOS FATOS\n"),
            _Bloco("text", "Conforme Doc. 03, houve pagamento."),
        ])


class _FakeClient:
    def __init__(self, sink):
        self.messages = _FakeMessages(sink)


# ── Provider: modelo moderno ──────────────────────────────────────────────────

async def test_provider_modelo_moderno_sem_temperature_com_thinking(monkeypatch):
    sink = {}
    monkeypatch.setattr(ap, "_get_client", lambda: _FakeClient(sink))

    texto, usage = await ap.chat(
        messages=[{"role": "system", "content": "regras"},
                  {"role": "user", "content": "fatos"}],
        model="claude-sonnet-5",
        temperature=0.3,
        max_tokens=4000,
    )

    kw = sink["kwargs"]
    assert "temperature" not in kw            # Claude 4.6+/5 rejeita → 400
    assert kw["thinking"] == {"type": "adaptive"}
    assert kw["max_tokens"] >= ap._THINKING_FLOOR   # folga para não truncar
    assert kw["system"] == "regras"
    # texto concatena só os blocos 'text' (ignora thinking):
    assert texto == "I — SÍNTESE DOS FATOS\nConforme Doc. 03, houve pagamento."
    assert usage["model"] == "claude-sonnet-5"


async def test_provider_opus_tambem_e_moderno(monkeypatch):
    sink = {}
    monkeypatch.setattr(ap, "_get_client", lambda: _FakeClient(sink))
    await ap.chat(messages=[{"role": "user", "content": "x"}],
                  model="claude-opus-4-8", temperature=0.2, max_tokens=2048)
    assert "temperature" not in sink["kwargs"]
    assert sink["kwargs"]["thinking"] == {"type": "adaptive"}


# ── Provider: modelo legado (Haiku) ───────────────────────────────────────────

async def test_provider_haiku_mantem_temperature_sem_thinking(monkeypatch):
    sink = {}
    monkeypatch.setattr(ap, "_get_client", lambda: _FakeClient(sink))
    await ap.chat(messages=[{"role": "user", "content": "x"}],
                  model="claude-haiku-4-5-20251001", temperature=0.2, max_tokens=512)
    kw = sink["kwargs"]
    assert kw["temperature"] == 0.2
    assert "thinking" not in kw
    assert kw["max_tokens"] == 512            # sem piso para legado


# ── Gateway: Claude só para raciocínio complexo ───────────────────────────────

def _cadeia(monkeypatch, *, tem_chave=True, nivel=None):
    monkeypatch.setattr(g.settings, "ANTHROPIC_API_KEY", "sk-x" if tem_chave else "")
    monkeypatch.setattr(g.settings, "OLLAMA_ENABLED", True)
    monkeypatch.setattr(g.settings, "GROQ_API_KEY", "gk")
    return g._resolver_cadeia("estrategia", provider_force=None,
                              model_override=None, nivel_inteligencia=nivel)


def test_gateway_padrao_nao_usa_claude(monkeypatch):
    # Sem nível elevado (padrão), o raciocínio NÃO vai para a Claude —
    # mesmo com chave — e segue em Ollama/Groq.
    for nivel in (None, "padrao"):
        cadeia = _cadeia(monkeypatch, tem_chave=True, nivel=nivel)
        assert all(p != "anthropic" for p, _ in cadeia), nivel
        assert any(p == "ollama" for p, _ in cadeia)
        assert any(p == "groq" for p, _ in cadeia)


def test_gateway_maximo_usa_opus(monkeypatch):
    cadeia = _cadeia(monkeypatch, tem_chave=True, nivel="maximo")
    assert cadeia[0] == ("anthropic", "claude-opus-4-8")   # complexo → modelo mais capaz
    assert any(p == "groq" for p, _ in cadeia)             # fallback preservado


def test_gateway_alto_usa_sonnet(monkeypatch):
    cadeia = _cadeia(monkeypatch, tem_chave=True, nivel="alto")
    assert cadeia[0] == ("anthropic", "claude-sonnet-5")


def test_gateway_pula_claude_sem_chave(monkeypatch):
    cadeia = _cadeia(monkeypatch, tem_chave=False, nivel="maximo")
    assert all(p != "anthropic" for p, _ in cadeia)        # sem chave → sem Claude
    assert any(p == "ollama" for p, _ in cadeia)
    assert any(p == "groq" for p, _ in cadeia)


def test_gateway_model_override_tem_prioridade(monkeypatch):
    monkeypatch.setattr(g.settings, "ANTHROPIC_API_KEY", "sk-x")
    monkeypatch.setattr(g.settings, "OLLAMA_ENABLED", False)
    monkeypatch.setattr(g.settings, "GROQ_API_KEY", "gk")
    cadeia = g._resolver_cadeia("elaboracao_peca", provider_force=None,
                                model_override="claude-sonnet-5",
                                nivel_inteligencia="maximo")
    assert cadeia[0] == ("anthropic", "claude-sonnet-5")   # override vence a escalada p/ Opus


# ── Preços corrigidos ─────────────────────────────────────────────────────────

def test_precos_oficiais_corrigidos():
    assert g._PRICING_USD_MM["claude-opus-4-8"] == {"input": 5.00, "output": 25.00}
    assert g._PRICING_USD_MM["claude-sonnet-5"] == {"input": 3.00, "output": 15.00}
    assert g._PRICING_USD_MM["claude-haiku-4-5"] == {"input": 1.00, "output": 5.00}
