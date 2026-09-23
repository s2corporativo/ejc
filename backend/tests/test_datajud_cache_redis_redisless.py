"""Cache L2 Redis do DataJud (compartilhado entre workers uvicorn).

OPS-04 (Auditoria 2026-09-20): o L1 em memória do ``_CACHE_CONSULTA`` é por
processo — 3 workers do uvicorn = 3 fetches do mesmo nº CNJ no mesmo ciclo.
O L2 memoiza resposta CNJ em Redis por (dominio, alias, payload) e só entra
em ação quando DATAJUD_CACHE_REDIS_ENABLED=true. Aqui validamos:
  • off por default e no-op sem Redis;
  • hit reusa JSON cacheado sem nova chamada HTTP;
  • TTL configurável;
  • chave SHA-256 estável;
  • deserialização corrompida → refetch transparente.

Nota: conftest bloqueia ``cache_clear()`` em get_settings (Issue #620), então
os monkeypatches operam em ``datajud_service.get_settings`` (referência
importada) sem invalidar o singleton global.
"""

from types import SimpleNamespace

import pytest

from app.services import datajud_service


def test_redis_habilitado_default_off():
    """Opt-in: persistir JSON processual em Redis exige homologação do Titular."""
    assert datajud_service._redis_habilitado() is False


def test_redis_habilitado_quando_flag_liga(monkeypatch):
    s = SimpleNamespace(DATAJUD_CACHE_REDIS_ENABLED=True, DATAJUD_CACHE_REDIS_TTL=60)
    # Monkeypatch em datajud_service — referencia importada, não o módulo.
    monkeypatch.setattr(datajud_service, "get_settings", lambda: s)
    assert datajud_service._redis_habilitado() is True


def test_redis_ttl_negativo_vira_zero(monkeypatch):
    """TTL ≤ 0 desativa o cache mesmo com a flag ligada."""
    s = SimpleNamespace(DATAJUD_CACHE_REDIS_ENABLED=True, DATAJUD_CACHE_REDIS_TTL=-5)
    monkeypatch.setattr(datajud_service, "get_settings", lambda: s)
    assert datajud_service._redis_ttl() == 0
    s2 = SimpleNamespace(DATAJUD_CACHE_REDIS_ENABLED=True, DATAJUD_CACHE_REDIS_TTL=0)
    monkeypatch.setattr(datajud_service, "get_settings", lambda: s2)
    assert datajud_service._redis_ttl() == 0


def test_chave_sha256_estavel():
    """Mesma (dominio, alias, payload) → mesma chave. SHA-256 não vaza payload."""
    a = datajud_service._cache_redis_chave("mov:1", "api_publica_tjmg", {"x": 1})
    b = datajud_service._cache_redis_chave("mov:1", "api_publica_tjmg", {"x": 1})
    assert a == b
    assert a.startswith("dj:")
    assert len(a) == 3 + 64  # "dj:" + 64 hex chars (SHA-256)
    # O número CNJ (20 dígitos) nunca aparece na chave — chave = SHA-256 (bytes),
    # não é reversível. Payload pode aparecer no input mas o SHA-256 não
    # "vaza" sem a função inversa. Tamanho fixo é a garantia.


def test_chave_muda_com_dominio_alias_payload():
    k_base = datajud_service._cache_redis_chave("mov:1", "tjmg", {"x": 1})
    assert datajud_service._cache_redis_chave("proc:1", "tjmg", {"x": 1}) != k_base
    assert datajud_service._cache_redis_chave("mov:1", "tjsp", {"x": 1}) != k_base
    assert datajud_service._cache_redis_chave("mov:1", "tjmg", {"x": 2}) != k_base


async def test_consultar_ou_cachear_off_cai_na_http(monkeypatch):
    """Sem flag ligada: chama _datajud_search direto, sem tocar em Redis."""
    s = SimpleNamespace(
        DATAJUD_CACHE_REDIS_ENABLED=False,
        DATAJUD_CACHE_REDIS_TTL=0,
    )
    monkeypatch.setattr(datajud_service, "get_settings", lambda: s)

    chamadas = []

    async def fake_search(alias, payload, headers):
        chamadas.append(alias)
        return {"hits": {"hits": [{"_source": {}}]}}

    monkeypatch.setattr(datajud_service, "_datajud_search", fake_search)
    out = await datajud_service._consultar_ou_cachear(
        "tjmg", {}, {}, chave_dominio="mov:1",
    )
    assert chamadas == ["tjmg"]
    assert "hits" in out


async def test_consultar_ou_cachear_redis_indisponivel_faz_http(monkeypatch):
    """Redis offline → HTTP normal, no-op silencioso (graceful degradation)."""
    s = SimpleNamespace(
        DATAJUD_CACHE_REDIS_ENABLED=True,
        DATAJUD_CACHE_REDIS_TTL=60,
        REDIS_URL="redis://invalid",
    )
    monkeypatch.setattr(datajud_service, "get_settings", lambda: s)
    monkeypatch.setattr(datajud_service, "_redis_cliente", lambda: None)

    chamadas = []

    async def fake_search(alias, payload, headers):
        chamadas.append("http")
        return {"hits": {"hits": [{"_source": {}}]}}

    monkeypatch.setattr(datajud_service, "_datajud_search", fake_search)
    out = await datajud_service._consultar_ou_cachear(
        "tjmg", {"x": 1}, {}, chave_dominio="mov:1",
    )
    assert chamadas == ["http"]
    assert "hits" in out


async def test_consultar_ou_cachear_hit_evita_http(monkeypatch):
    """Hit em Redis: retorna o JSON cacheado, sem chamar _datajud_search."""
    s = SimpleNamespace(
        DATAJUD_CACHE_REDIS_ENABLED=True,
        DATAJUD_CACHE_REDIS_TTL=60,
    )
    monkeypatch.setattr(datajud_service, "get_settings", lambda: s)

    payload_json = '{"hits": {"hits": [{"_source": {"movimentos": []}}]}}'

    class FakeCli:
        async def get(self, key): return payload_json
        async def set(self, key, val, ex=None): self.gravado = (key, val, ex)
        async def aclose(self): pass

    fake = FakeCli()
    monkeypatch.setattr(datajud_service, "_redis_cliente", lambda: fake)

    chamadas = []

    async def should_not_call(*a, **kw):
        chamadas.append("http")
        return {}

    monkeypatch.setattr(datajud_service, "_datajud_search", should_not_call)

    out = await datajud_service._consultar_ou_cachear(
        "tjmg", {"x": 1}, {}, chave_dominio="mov:1",
    )
    assert chamadas == []  # ZERO chamadas HTTP — hit total
    assert "hits" in out
    assert out["hits"]["hits"][0]["_source"]["movimentos"] == []


async def test_consultar_ou_cachear_payload_corrompido_refaz_http(monkeypatch):
    """JSON em cache corrompido → refetch silencioso."""
    s = SimpleNamespace(
        DATAJUD_CACHE_REDIS_ENABLED=True,
        DATAJUD_CACHE_REDIS_TTL=60,
    )
    monkeypatch.setattr(datajud_service, "get_settings", lambda: s)

    class FakeCli:
        async def get(self, key): return "{json quebrado"
        async def set(self, key, val, ex=None): pass
        async def aclose(self): pass

    monkeypatch.setattr(datajud_service, "_redis_cliente", lambda: FakeCli())

    chamadas = []

    async def fake_search(alias, payload, headers):
        chamadas.append("http")
        return {"hits": {"hits": [{"_source": {"ok": True}}]}}

    monkeypatch.setattr(datajud_service, "_datajud_search", fake_search)

    out = await datajud_service._consultar_ou_cachear(
        "tjmg", {"x": 1}, {}, chave_dominio="mov:1",
    )
    assert chamadas == ["http"]
    assert out["hits"]["hits"][0]["_source"]["ok"] is True


async def test_consultar_ou_cachear_grava_apos_sucesso(monkeypatch):
    """Em sucesso, persiste no Redis com TTL configurado para reuso."""
    s = SimpleNamespace(
        DATAJUD_CACHE_REDIS_ENABLED=True,
        DATAJUD_CACHE_REDIS_TTL=123,
    )
    monkeypatch.setattr(datajud_service, "get_settings", lambda: s)

    gravados = []

    class FakeCli:
        async def get(self, key): return None
        async def set(self, key, val, ex=None):
            gravados.append((key, ex))
        async def aclose(self): pass

    inst = FakeCli()
    monkeypatch.setattr(datajud_service, "_redis_cliente", lambda: inst)

    async def fake_search(alias, payload, headers):
        return {"hits": {"hits": [{"_source": {"x": 1}}]}}

    monkeypatch.setattr(datajud_service, "_datajud_search", fake_search)
    await datajud_service._consultar_ou_cachear(
        "tjmg", {"x": 1}, {}, chave_dominio="mov:1",
    )
    assert len(gravados) == 1
    _, ttl = gravados[0]
    assert ttl == 123
