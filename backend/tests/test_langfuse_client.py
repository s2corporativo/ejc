"""Fase 6 — wrapper de observabilidade Langfuse (self-hosted).

Contrato:
  - NO-OP quando desabilitado: não importa/instancia SDK, funções não levantam;
  - metadata montado só com campos operacionais (sem PII);
  - conteúdo (input/output) só quando LANGFUSE_CAPTURE_CONTENT e SEMPRE sanitizado;
  - qualquer erro do SDK é engolido — nunca quebra o fluxo de IA.
"""
from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.services.observability import langfuse_client as lf


@pytest.fixture(autouse=True)
def _reset():
    lf._reset_para_testes()
    yield
    lf._reset_para_testes()


def _cfg(monkeypatch, **kw):
    s = get_settings()
    for k, v in kw.items():
        monkeypatch.setattr(s, k, v)


# ── NO-OP quando desabilitado ─────────────────────────────────────────────────

def test_desabilitado_e_noop(monkeypatch):
    _cfg(monkeypatch, LANGFUSE_ENABLED=False)
    assert lf.habilitado() is False
    # nenhuma dessas chamadas pode levantar nem retornar cliente
    assert lf.novo_trace("resumo") is None
    lf.registrar_generation(None, name="resumo", model="x", metadata={})
    lf.registrar_evento(None, name="fallback", metadata={})
    lf.flush()  # não levanta


def test_habilitado_exige_as_duas_chaves(monkeypatch):
    _cfg(monkeypatch, LANGFUSE_ENABLED=True, LANGFUSE_PUBLIC_KEY="pk", LANGFUSE_SECRET_KEY="")
    assert lf.habilitado() is False
    _cfg(monkeypatch, LANGFUSE_SECRET_KEY="sk")
    assert lf.habilitado() is True


def test_get_client_falha_vira_none_sem_levantar(monkeypatch):
    # Habilitado com chaves, mas o SDK falha ao instanciar → wrapper degrada p/ None.
    _cfg(monkeypatch, LANGFUSE_ENABLED=True, LANGFUSE_PUBLIC_KEY="pk", LANGFUSE_SECRET_KEY="sk")

    import sys, types
    fake_mod = types.ModuleType("langfuse")

    class _Boom:
        def __init__(self, **kw):
            raise RuntimeError("host indisponível")

    fake_mod.Langfuse = _Boom
    monkeypatch.setitem(sys.modules, "langfuse", fake_mod)
    assert lf.novo_trace("resumo") is None  # não levanta


# ── Guarda de soberania: host externo x CAPTURE_CONTENT (LGPD) ────────────────

def _fake_sdk(monkeypatch):
    """Injeta um SDK Langfuse falso que instancia sem erro."""
    import sys, types
    fake_mod = types.ModuleType("langfuse")

    class _OK:
        def __init__(self, **kw):
            self.kw = kw

        def trace(self, **kw):
            return object()

    fake_mod.Langfuse = _OK
    monkeypatch.setitem(sys.modules, "langfuse", fake_mod)


def test_host_interno_helper():
    # compose service name (sem ponto), localhost e IP privado = interno
    assert lf._host_langfuse_interno("http://langfuse:3000") is True
    assert lf._host_langfuse_interno("http://localhost:3000") is True
    assert lf._host_langfuse_interno("http://127.0.0.1:3000") is True
    assert lf._host_langfuse_interno("http://10.0.0.5:3000") is True
    # cloud / IP público = externo
    assert lf._host_langfuse_interno("https://cloud.langfuse.com") is False
    assert lf._host_langfuse_interno("https://us.cloud.langfuse.com") is False
    assert lf._host_langfuse_interno("http://8.8.8.8:3000") is False
    assert lf._host_langfuse_interno("") is False


def test_capture_content_rejeita_host_externo(monkeypatch):
    # captura ligada + host cloud → cliente NÃO inicializa (conteúdo não vaza)
    _cfg(monkeypatch, LANGFUSE_ENABLED=True, LANGFUSE_PUBLIC_KEY="pk",
         LANGFUSE_SECRET_KEY="sk", LANGFUSE_CAPTURE_CONTENT=True,
         LANGFUSE_HOST="https://cloud.langfuse.com")
    _fake_sdk(monkeypatch)  # mesmo com SDK OK, a guarda barra antes
    assert lf._get_client() is None
    assert lf.novo_trace("resumo") is None


def test_capture_content_aceita_host_interno(monkeypatch):
    # captura ligada + host self-hosted (compose) → inicializa normalmente
    _cfg(monkeypatch, LANGFUSE_ENABLED=True, LANGFUSE_PUBLIC_KEY="pk",
         LANGFUSE_SECRET_KEY="sk", LANGFUSE_CAPTURE_CONTENT=True,
         LANGFUSE_HOST="http://langfuse:3000")
    _fake_sdk(monkeypatch)
    assert lf._get_client() is not None


def test_host_externo_permissivo_sem_captura(monkeypatch):
    # captura DESLIGADA + host externo → permitido (só metadados), inicializa
    _cfg(monkeypatch, LANGFUSE_ENABLED=True, LANGFUSE_PUBLIC_KEY="pk",
         LANGFUSE_SECRET_KEY="sk", LANGFUSE_CAPTURE_CONTENT=False,
         LANGFUSE_HOST="https://cloud.langfuse.com")
    _fake_sdk(monkeypatch)
    assert lf._get_client() is not None


# ── metadata puro (sem PII) ───────────────────────────────────────────────────

def test_montar_metadata_so_operacional():
    meta = lf.montar_metadata(
        provider="anthropic", model="claude-opus-4-8", task_type="estrategia",
        input_tokens=100, output_tokens=200, duracao_ms=1234,
        fallback_ativado=True, fallback_motivo="ollama: timeout",
        custo_estimado_brl=0.5, sucesso=True, tier="pesado", roteamento_score=7,
    )
    assert meta["provider"] == "anthropic"
    assert meta["task_type"] == "estrategia"
    assert meta["custo_estimado_brl"] == 0.5
    assert meta["tier"] == "pesado"
    # campos None são omitidos
    meta2 = lf.montar_metadata(provider="groq", model=None, task_type="resumo")
    assert "model" not in meta2
    assert "erro" not in meta2


# ── captura de conteúdo condicional + sanitização ─────────────────────────────

def test_conteudo_omitido_quando_captura_desligada(monkeypatch):
    _cfg(monkeypatch, LANGFUSE_CAPTURE_CONTENT=False)
    assert lf._sanitizar_conteudo("CPF 123.456.789-09") is None
    assert lf._sanitizar_conteudo([{"role": "user", "content": "x"}]) is None


def test_conteudo_sanitizado_quando_captura_ligada(monkeypatch):
    _cfg(monkeypatch, LANGFUSE_CAPTURE_CONTENT=True)
    out = lf._sanitizar_conteudo("meu CPF é 529.982.247-25 ok")
    assert "529.982.247-25" not in out  # PII sanitizada
    msgs = lf._sanitizar_conteudo([{"role": "user", "content": "CPF 529.982.247-25"}])
    assert "529.982.247-25" not in msgs[0]["content"]


# ── generation/evento usam o handle do SDK e engolem erro ─────────────────────

class _FakeTrace:
    def __init__(self):
        self.generations = []
        self.events = []

    def generation(self, **kw):
        self.generations.append(kw)

    def event(self, **kw):
        self.events.append(kw)


def test_registrar_generation_repassa_para_o_trace(monkeypatch):
    _cfg(monkeypatch, LANGFUSE_CAPTURE_CONTENT=False)
    tr = _FakeTrace()
    lf.registrar_generation(
        tr, name="resumo", model="groq/llama", metadata={"provider": "groq"},
        input_messages=[{"role": "user", "content": "x"}], output_text="y",
        input_tokens=10, output_tokens=20,
    )
    assert len(tr.generations) == 1
    g = tr.generations[0]
    assert g["model"] == "groq/llama"
    assert g["usage"] == {"input": 10, "output": 20, "unit": "TOKENS"}
    assert g["input"] is None and g["output"] is None  # captura desligada


def test_registrar_generation_engole_erro():
    class _Boom:
        def generation(self, **kw):
            raise RuntimeError("falha SDK")

    lf.registrar_generation(_Boom(), name="x", model="m", metadata={})  # não levanta
