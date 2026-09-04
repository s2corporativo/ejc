"""Claude no Núcleo Único — provider Anthropic + roteamento do gateway.

Contrato consolidado (Núcleo Único + API 2026):
  - provider: modelos modernos (Opus 4.7+/Sonnet 5) NÃO enviam temperature
    (a API rejeita com 400); raciocínio via extra_body.thinking adaptativo +
    output_config.effort; piso de max_tokens 8192 (thinking divide o budget);
  - provider: system prompt vira bloco com cache_control (prompt caching);
  - provider: Haiku/legado mantém temperature, sem extra_body, com teto
    ANTHROPIC_MAX_TOKENS;
  - gateway: cadeia respeita AI_PROVIDER_PRIORITY + elegibilidade; sem chave
    a Claude é pulada; provider_force inelegível degrada para cadeia automática;
  - tabela de preços corrigida (Opus 4.8 = 5/25, não 15/75).
"""
from __future__ import annotations

import pytest

from app.core.config import get_settings
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
    cache_read_input_tokens = 0
    cache_creation_input_tokens = 0


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


@pytest.fixture()
def sink(monkeypatch):
    box = {}
    monkeypatch.setattr(ap, "_get_client", lambda: _FakeClient(box))
    # ap.chat() aborta cedo se ANTHROPIC_ENABLED=false. Estes testes exercitam a
    # MONTAGEM do request (temperature/thinking/cache), não a política de
    # habilitação — então fixamos a flag para o provider ser hermético e imune a
    # um .env/env de dev com Anthropic OFF (mesma blindagem do conftest.py).
    monkeypatch.setattr(get_settings(), "ANTHROPIC_ENABLED", True)
    return box


# ── Provider: modelo moderno ──────────────────────────────────────────────────

async def test_provider_moderno_sem_temperature_com_thinking(sink):
    texto, usage = await ap.chat(
        messages=[{"role": "system", "content": "regras"},
                  {"role": "user", "content": "fatos"}],
        model="claude-sonnet-5",
        temperature=0.3,
        max_tokens=4000,
    )

    kw = sink["kwargs"]
    assert "temperature" not in kw            # Claude 4.7+/5 rejeita → 400
    assert kw["extra_body"]["thinking"] == {"type": "adaptive"}
    assert kw["extra_body"]["output_config"]["effort"] in ("low", "medium", "high")
    assert kw["max_tokens"] >= 8192           # folga para o thinking não truncar
    # system prompt vira bloco cacheável (prompt caching ≈ 10% do custo)
    assert kw["system"][0]["text"] == "regras"
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
    # texto concatena só os blocos 'text' (ignora thinking):
    assert texto == "I — SÍNTESE DOS FATOS\nConforme Doc. 03, houve pagamento."
    assert usage["model"] == "claude-sonnet-5"


async def test_provider_opus_tambem_e_moderno(sink):
    await ap.chat(messages=[{"role": "user", "content": "x"}],
                  model="claude-opus-4-8", temperature=0.2, max_tokens=2048)
    kw = sink["kwargs"]
    assert "temperature" not in kw
    assert kw["extra_body"]["thinking"] == {"type": "adaptive"}


# ── Provider: modelo legado (Haiku) ───────────────────────────────────────────

async def test_provider_haiku_mantem_temperature_sem_thinking(sink):
    await ap.chat(messages=[{"role": "user", "content": "x"}],
                  model="claude-haiku-4-5-20251001", temperature=0.2, max_tokens=512)
    kw = sink["kwargs"]
    assert kw["temperature"] == 0.2
    assert "extra_body" not in kw
    assert kw["max_tokens"] == 512            # sem piso para legado


async def test_provider_legado_respeita_teto_de_custo(sink, monkeypatch):
    monkeypatch.setattr(get_settings(), "ANTHROPIC_MAX_TOKENS", 1000)
    await ap.chat(messages=[{"role": "user", "content": "x"}],
                  model="claude-haiku-4-5-20251001", temperature=0.1, max_tokens=99999)
    assert sink["kwargs"]["max_tokens"] == 1000   # teto duro ANTHROPIC_MAX_TOKENS


# ── Gateway: cadeia por prioridade + elegibilidade ────────────────────────────

def _prep(monkeypatch, *, tem_chave=True, ollama=True):
    monkeypatch.setattr(g.settings, "ANTHROPIC_API_KEY", "sk-x" if tem_chave else "")
    monkeypatch.setattr(g.settings, "ANTHROPIC_ENABLED", True)
    monkeypatch.setattr(g.settings, "AI_EXTERNAL_PROVIDERS_ALLOWED", True)
    monkeypatch.setattr(g.settings, "AI_PROVIDER_PRIORITY", "ollama,anthropic,groq")
    monkeypatch.setattr(g.settings, "OLLAMA_ENABLED", ollama)
    monkeypatch.setattr(g.settings, "GROQ_API_KEY", "gk")


def test_gateway_tarefa_complexa_inclui_claude(monkeypatch):
    _prep(monkeypatch, tem_chave=True, ollama=False)
    cadeia = g._resolver_cadeia("estrategia", provider_force=None, model_override=None)
    # Sem Ollama, Claude assume a frente com o modelo COMPLEXO configurado.
    assert cadeia[0] == ("anthropic", g.settings.ANTHROPIC_MODEL_COMPLEXO)
    assert any(p == "groq" for p, _ in cadeia)             # fallback preservado


def test_gateway_tarefa_de_merito_comeca_pelo_modelo_forte(monkeypatch):
    """Decisão do titular (18/08): trabalho jurídico de mérito começa pelo
    provedor de raciocínio profundo, mesmo com a IA local ligada.

    Antes, o gateway ordenava só por AI_PROVIDER_PRIORITY — e com o default
    antigo ("ollama,...") um modelo local de 8-14B redigia a peça e o Claude
    virava fallback. A AIProviderPolicy já decidia o contrário para tarefa
    complexa; quem valia era o gateway."""
    _prep(monkeypatch, tem_chave=True, ollama=True)
    cadeia = g._resolver_cadeia("elaboracao_peca", provider_force=None, model_override=None)
    assert cadeia[0] == ("anthropic", g.settings.ANTHROPIC_MODEL_COMPLEXO)
    # A IA local permanece na cadeia como rede de segurança.
    assert any(p == "ollama" for p, _ in cadeia)


def test_gateway_fora_do_merito_respeita_a_ordem_configurada(monkeypatch):
    """A promoção vale para MÉRITO. Fora dele, quem manda é AI_PROVIDER_PRIORITY
    — é assim que o operador escolhe local-first (soberania de dados)."""
    _prep(monkeypatch, tem_chave=True, ollama=True)
    monkeypatch.setattr(g.settings, "AI_PROVIDER_PRIORITY", "ollama,anthropic,groq")
    cadeia = g._resolver_cadeia("resumo", provider_force=None, model_override=None)
    assert cadeia[0][0] == "ollama"


def test_gateway_pula_claude_sem_chave(monkeypatch):
    _prep(monkeypatch, tem_chave=False)
    cadeia = g._resolver_cadeia("estrategia", provider_force=None, model_override=None)
    assert all(p != "anthropic" for p, _ in cadeia)        # sem chave → sem Claude
    assert any(p == "groq" for p, _ in cadeia)


def test_gateway_tarefa_simples_usa_claude_so_como_ultimo_recurso(monkeypatch):
    """I8/A1 (análise E2E 03/09): `resumo`/`chat_rapido` passam a ter Anthropic
    na cadeia — antes, no desenho de produção (Ollama off, Groq/Maritaca sem
    chave) a cadeia ficava VAZIA com Anthropic saudável. Mas ele não vira o
    primeiro: o local/grátis continua na frente, e o modelo é o RÁPIDO."""
    _prep(monkeypatch, tem_chave=True)
    monkeypatch.setattr(g.settings, "ANTHROPIC_MODEL_RAPIDO", "claude-haiku-4-5")
    monkeypatch.setattr(g.settings, "ANTHROPIC_MODEL_COMPLEXO", "claude-opus-4-8")
    for task in ("resumo", "chat_rapido"):
        cadeia = g._resolver_cadeia(task, provider_force=None, model_override=None)
        provs = [p for p, _ in cadeia]
        assert cadeia[0][0] == "ollama"                    # local primeiro
        assert "anthropic" in provs                        # cadeia completa
        assert dict(cadeia)["anthropic"] == "claude-haiku-4-5"  # modelo rápido


def test_gateway_tarefa_simples_sem_locais_cai_no_claude_em_vez_de_vazio(monkeypatch):
    """Cenário de produção do compose: só Anthropic elegível → cadeia NÃO vazia."""
    _prep(monkeypatch, tem_chave=True, ollama=False)
    monkeypatch.setattr(g.settings, "GROQ_API_KEY", "")
    cadeia = g._resolver_cadeia("chat_rapido", provider_force=None, model_override=None)
    assert [p for p, _ in cadeia] == ["anthropic"]


def test_gateway_force_anthropic_com_chave(monkeypatch):
    _prep(monkeypatch, tem_chave=True)
    cadeia = g._resolver_cadeia("elaboracao_peca", provider_force="anthropic",
                                model_override=None)
    assert cadeia == [("anthropic", g.settings.ANTHROPIC_MODEL_COMPLEXO)]


def test_gateway_force_anthropic_sem_chave_degrada(monkeypatch):
    # EJC skills com engine=anthropic não podem falhar duro sem chave:
    # caem na cadeia automática (Ollama/Groq).
    _prep(monkeypatch, tem_chave=False)
    cadeia = g._resolver_cadeia("elaboracao_peca", provider_force="anthropic",
                                model_override=None)
    assert cadeia, "cadeia não pode ficar vazia"
    assert all(p != "anthropic" for p, _ in cadeia)


def test_gateway_model_override_tem_prioridade(monkeypatch):
    _prep(monkeypatch, tem_chave=True, ollama=False)
    cadeia = g._resolver_cadeia("elaboracao_peca", provider_force=None,
                                model_override="claude-sonnet-5")
    assert cadeia[0] == ("anthropic", "claude-sonnet-5")


# ── Preços corrigidos ─────────────────────────────────────────────────────────

def test_precos_oficiais_corrigidos():
    # Tabela de preços Anthropic unificada em ai_cost (fonte única de custo de IA).
    from app.services.ai_cost import _PRECOS_ANTHROPIC_USD_MM
    assert _PRECOS_ANTHROPIC_USD_MM["claude-opus-4-8"] == {"input": 5.00, "output": 25.00}
    # A4 (análise E2E 03/09): Sonnet 5 é 2/10 na tabela vigente (era 3/15 aqui).
    assert _PRECOS_ANTHROPIC_USD_MM["claude-sonnet-5"] == {"input": 2.00, "output": 10.00}
    assert _PRECOS_ANTHROPIC_USD_MM["claude-haiku-4-5"] == {"input": 1.00, "output": 5.00}
    assert _PRECOS_ANTHROPIC_USD_MM["claude-opus-5"] == {"input": 5.00, "output": 25.00}
    assert _PRECOS_ANTHROPIC_USD_MM["claude-fable-5"] == {"input": 10.00, "output": 50.00}
    assert _PRECOS_ANTHROPIC_USD_MM["claude-fable-5-1"] == {"input": 10.00, "output": 50.00}


# ── Revogação de credencial pelo Cofre (auditoria de segurança, 18/08) ───────
# O Cofre grava "" em Settings.ANTHROPIC_API_KEY ao revogar uma credencial já
# cadastrada (comportamento deliberado: revogar não deve deixar fallback ao
# .env). O provider tinha um fallback a os.getenv que ANULAVA essa revogação:
# como o docker-compose exporta o .env no ambiente do processo (env_file), a
# chave revogada continuava sendo usada até o próximo restart do container.

def test_chave_revogada_nao_cai_no_env_do_processo(monkeypatch):
    """Settings com "" (revogada) NUNCA deve resolver para o valor do processo,
    mesmo que ANTHROPIC_API_KEY esteja setada no ambiente (docker env_file)."""
    from app.services.providers import anthropic_provider as ap

    monkeypatch.setattr(get_settings(), "ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-vazada-do-ambiente-do-processo")
    assert ap._api_key() == ""


def test_chave_valida_na_settings_e_usada_normalmente(monkeypatch):
    """Uso legítimo (credencial válida na Settings, vinda do Cofre ou do .env
    carregado pelo pydantic) continua funcionando — o fix não quebra o caminho são."""
    from app.services.providers import anthropic_provider as ap

    monkeypatch.setattr(get_settings(), "ANTHROPIC_API_KEY", "sk-ant-valor-valido")
    assert ap._api_key() == "sk-ant-valor-valido"


# ── Revogação com CLIENT JÁ CONSTRUÍDO (achado da revisão de segurança sobre
# o fix acima, 18/08): _api_key() sozinha não bastava. O SDK grava a chave
# DENTRO do objeto client no momento da construção, e o client é cacheado por
# PROCESSO (`--workers 1`) — revogar pelo Cofre zerava Settings, mas o client
# já construído seguia mandando a chave ANTIGA em toda chamada até o restart.
# Comprovado por PoC na revisão: client reconstruído só no restart.

def _fake_anthropic_sdk(monkeypatch):
    """Fake do construtor `anthropic.Anthropic` que só grava a api_key
    recebida — sem tocar rede, sem validar formato."""
    import anthropic as _sdk
    from app.services.providers import anthropic_provider as ap

    class _FakeClient:
        def __init__(self, **kwargs):
            self.api_key = kwargs.get("api_key")

    monkeypatch.setattr(_sdk, "Anthropic", _FakeClient)
    monkeypatch.setattr(ap, "_client", None)
    monkeypatch.setattr(ap, "_client_api_key", None)
    monkeypatch.setattr(get_settings(), "ANTHROPIC_ENABLED", True)
    return ap


def test_client_ja_construido_e_revogado_nao_continua_servindo_a_chave_velha(monkeypatch):
    ap = _fake_anthropic_sdk(monkeypatch)

    monkeypatch.setattr(get_settings(), "ANTHROPIC_API_KEY", "sk-ant-VALIDA-inicial")
    client1 = ap._get_client()
    assert client1.api_key == "sk-ant-VALIDA-inicial"

    # Revogação pelo Cofre: Settings passa a "".
    monkeypatch.setattr(get_settings(), "ANTHROPIC_API_KEY", "")
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY não configurada"):
        ap._get_client()
    # Fail-closed: a chave revogada NUNCA mais deve ser servida por um client
    # cacheado, nem mesmo o mesmo objeto de antes.
    assert ap._client is None


def test_rotacao_de_credencial_reconstroi_o_client_com_a_chave_nova(monkeypatch):
    ap = _fake_anthropic_sdk(monkeypatch)

    monkeypatch.setattr(get_settings(), "ANTHROPIC_API_KEY", "sk-ant-chave-A")
    client1 = ap._get_client()
    assert client1.api_key == "sk-ant-chave-A"

    monkeypatch.setattr(get_settings(), "ANTHROPIC_API_KEY", "sk-ant-chave-B")
    client2 = ap._get_client()
    assert client2.api_key == "sk-ant-chave-B"
    assert client2 is not client1  # não é o mesmo objeto reaproveitado


def test_sem_mudanca_de_chave_o_client_e_reaproveitado(monkeypatch):
    """A correção não pode custar reconstruir o client em TODA chamada."""
    ap = _fake_anthropic_sdk(monkeypatch)

    monkeypatch.setattr(get_settings(), "ANTHROPIC_API_KEY", "sk-ant-estavel")
    client1 = ap._get_client()
    client2 = ap._get_client()
    assert client1 is client2


# ── Deadline: SDK sem retry próprio, o fallback é entre PROVIDERS (18/08) ────
# Sem asyncio.timeout global na cadeia do gateway, o retry INTERNO do SDK (até
# 2x por padrão em erro transitório) multiplicava o pior caso de latência POR
# PROVIDER antes mesmo do próximo da cadeia ser tentado. A resiliência real é
# o fallback entre providers DIFERENTES que o gateway já faz.

def test_client_anthropic_desliga_retry_proprio_do_sdk(monkeypatch):
    import anthropic as _anthropic_sdk

    from app.services.providers import anthropic_provider as ap

    capturado = {}
    classe_original = _anthropic_sdk.Anthropic

    def _fake_anthropic(**kwargs):
        capturado.update(kwargs)
        return classe_original(**kwargs)

    monkeypatch.setattr(_anthropic_sdk, "Anthropic", _fake_anthropic)
    monkeypatch.setattr(ap, "_client", None)
    monkeypatch.setattr(get_settings(), "ANTHROPIC_ENABLED", True)
    monkeypatch.setattr(get_settings(), "ANTHROPIC_API_KEY", "sk-ant-teste")

    ap._get_client()
    assert capturado.get("max_retries") == 0
