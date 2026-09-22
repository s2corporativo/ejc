"""Fase 2 IA/RAG — API pública de abastecimento da base de conhecimento.

Cobre:
  1. Auth por API key (X-API-Key): sem chave 401, chave desconhecida 401,
     chave revogada 401, escopo errado 403.
  2. Batch feliz: novo / atualizado / inalterado (idempotência por
     chave_origem + hash), item inválido NÃO derruba o lote.
  3. Status de indexação por chave_origem.
  4. Proteção SSRF da callback_url (https em produção, IPs privados/loopback
     bloqueados) e resiliência do POST de callback (falha só loga).
  5. Administração de chaves (JWT admin): criação retorna a chave UMA vez;
     revogação.

Sem Postgres: usa um fake de AsyncSession (mesmo espírito de
test_rag_confianca_chunker._FakeDBUpsert) injetado via dependency_overrides.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.api_key_auth import gerar_chave
from app.models.api_key import ApiKey
from app.models.rag import KnowledgeDoc, KnowledgeChunk


# ── Fake de AsyncSession ──────────────────────────────────────────────────────

class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeNested:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeDB:
    """Fake mínimo de AsyncSession para os fluxos da API pública.

    Filtra selects por igualdade de parâmetros bound (chave_hash da ApiKey,
    chave_origem do KnowledgeDoc) e simula os server_defaults relevantes
    (versao=1, vigente=True) no add().
    """

    def __init__(self):
        self.store: dict[type, list] = {ApiKey: [], KnowledgeDoc: [], KnowledgeChunk: []}
        self.commits = 0

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _param_values(stmt) -> list:
        vals = []
        for v in stmt.compile().params.values():
            if isinstance(v, (list, tuple, set)):
                vals.extend(v)
            else:
                vals.append(v)
        return vals

    # -- API do AsyncSession usada pelo código -------------------------------
    async def execute(self, stmt, params=None):
        entity = stmt.column_descriptions[0]["entity"]
        vals = self._param_values(stmt)
        rows = self.store.get(entity, [])
        if entity is ApiKey:
            if vals:   # busca por chave_hash (auth) ou por id (admin/revogar)
                rows = [a for a in rows if a.chave_hash in vals or a.id in vals]
        elif entity is KnowledgeDoc:
            rows = [
                d for d in rows
                if d.chave_origem in vals
                and (d.vigente is None or d.vigente is True)
                and d.deleted_at is None
            ]
            # Honra o filtro de isolamento por cliente (auditoria A-1): se o
            # statement contém `client_id = :client_id_N`, aplica-o.
            client_vals = [v for k, v in stmt.compile().params.items()
                           if k.startswith("client_id")]
            if client_vals:
                rows = [d for d in rows if d.client_id == client_vals[0]]
        return _FakeResult(rows)

    def add(self, obj):
        if isinstance(obj, KnowledgeDoc):
            if obj.versao is None:
                obj.versao = 1          # simula server_default
            if obj.vigente is None:
                obj.vigente = True      # simula server_default
        self.store.setdefault(type(obj), []).append(obj)

    def begin_nested(self):
        return _FakeNested()

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _nova_chave(escopo="knowledge:write", *, revogada=False, client_id=None):
    chave, h, prefixo = gerar_chave()
    ak = ApiKey(id=f"ak-{prefixo}", nome="teste", chave_hash=h, prefixo=prefixo,
                escopo=escopo, client_id=client_id, ativo=not revogada)
    if revogada:
        from datetime import datetime, timezone
        ak.revoked_at = datetime.now(timezone.utc)
    return chave, ak


@pytest.fixture()
def ctx(monkeypatch):
    """App + fake DB + chave válida. Embeddings desligados (determinístico)."""
    from app.main import app
    from app.core.database import get_db
    import app.routers.rag_public as rp
    from app.core.rate_limit import _limpar_janelas

    _limpar_janelas()
    monkeypatch.setattr(rp, "emb_disponivel", lambda: False)

    db = _FakeDB()
    chave, ak = _nova_chave()
    db.store[ApiKey].append(ak)

    async def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)
    try:
        yield {"client": client, "db": db, "chave": chave, "ak": ak, "app": app}
    finally:
        app.dependency_overrides.clear()


def _item(chave_origem="lexml:lei-x", conteudo=None, **extra):
    return {
        "titulo": "Lei X — teste",
        "categoria": "legislacao_geral",
        "conteudo": conteudo or ("Conteúdo jurídico de teste suficientemente longo "
                                 "para ingestão idempotente na base. " * 2),
        "chave_origem": chave_origem,
        **extra,
    }


BATCH = "/api/rag/knowledge-base/batch"
STATUS = "/api/rag/knowledge-base/status"


# ── 1. Autenticação por API key ───────────────────────────────────────────────

def test_batch_sem_chave_401(ctx):
    r = ctx["client"].post(BATCH, json={"itens": [_item()]})
    assert r.status_code == 401


def test_batch_chave_desconhecida_401(ctx):
    r = ctx["client"].post(BATCH, json={"itens": [_item()]},
                           headers={"X-API-Key": "ejc_chave-inexistente"})
    assert r.status_code == 401


def test_batch_chave_revogada_401(ctx):
    chave, ak = _nova_chave(revogada=True)
    ctx["db"].store[ApiKey].append(ak)
    r = ctx["client"].post(BATCH, json={"itens": [_item()]},
                           headers={"X-API-Key": chave})
    assert r.status_code == 401


def test_batch_escopo_errado_403(ctx):
    chave, ak = _nova_chave(escopo="outro:escopo")
    ctx["db"].store[ApiKey].append(ak)
    r = ctx["client"].post(BATCH, json={"itens": [_item()]},
                           headers={"X-API-Key": chave})
    assert r.status_code == 403
    assert "knowledge:write" in r.json()["detail"]


# ── 2. Batch: novo / atualizado / inalterado / falha por item ────────────────

def test_batch_feliz_novo(ctx):
    r = ctx["client"].post(BATCH, json={"itens": [_item()]},
                           headers={"X-API-Key": ctx["chave"]})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["novo"] == 1 and body["erro"] == 0
    item = body["itens"][0]
    assert item["resultado"] == "novo"
    assert item["chave_origem"] == "lexml:lei-x"
    assert item["doc_id"] and item["versao"] == 1
    # last_used_at da chave foi atualizado (auditoria de uso)
    assert ctx["ak"].last_used_at is not None


def test_batch_idempotente_mesmo_payload_duas_vezes(ctx):
    payload = {"itens": [_item()]}
    h = {"X-API-Key": ctx["chave"]}
    r1 = ctx["client"].post(BATCH, json=payload, headers=h)
    r2 = ctx["client"].post(BATCH, json=payload, headers=h)
    assert r1.json()["itens"][0]["resultado"] == "novo"
    assert r2.json()["itens"][0]["resultado"] == "inalterado"
    # não duplicou o documento
    docs = [d for d in ctx["db"].store[KnowledgeDoc] if d.chave_origem == "lexml:lei-x"]
    assert len(docs) == 1


def test_batch_conteudo_alterado_gera_nova_versao(ctx):
    h = {"X-API-Key": ctx["chave"]}
    ctx["client"].post(BATCH, json={"itens": [_item()]}, headers=h)
    novo_conteudo = ("Texto REVISADO da norma, suficientemente longo para chunking "
                     "e reingestão versionada na base de conhecimento. " * 2)
    r = ctx["client"].post(BATCH, json={"itens": [_item(conteudo=novo_conteudo)]},
                           headers=h)
    item = r.json()["itens"][0]
    assert item["resultado"] == "atualizado"
    assert item["versao"] == 2
    # versão antiga preservada como histórico (vigente=False)
    docs = [d for d in ctx["db"].store[KnowledgeDoc] if d.chave_origem == "lexml:lei-x"]
    assert len(docs) == 2
    assert sorted((d.versao, d.vigente) for d in docs) == [(1, False), (2, True)]


def test_batch_item_invalido_nao_derruba_lote(ctx):
    itens = [
        _item("lexml:ok-1"),
        {"titulo": "Sem chave_origem", "categoria": "doutrina",
         "conteudo": "x" * 60},                       # inválido: falta chave_origem
        _item("lexml:ok-2"),
        _item("lexml:curto", conteudo="curto demais"),  # inválido: < 50 chars
    ]
    r = ctx["client"].post(BATCH, json={"itens": itens},
                           headers={"X-API-Key": ctx["chave"]})
    assert r.status_code == 201
    body = r.json()
    assert body["novo"] == 2 and body["erro"] == 2
    resultados = [i["resultado"] for i in body["itens"]]
    assert resultados == ["novo", "erro", "novo", "erro"]
    assert "chave_origem" in body["itens"][1]["erro"]
    assert body["itens"][3]["chave_origem"] == "lexml:curto"


def test_batch_chave_com_client_id_recusa_payload_de_outro_cliente(ctx):
    """C6 (análise E2E de IA 2026-09-03): antes o payload era silenciosamente
    FORÇADO ao escopo da chave; agora client_id divergente é recusado com 422
    claro e NADA é gravado (ver tests/test_api_key_batch_escopo_c6.py)."""
    chave, ak = _nova_chave(client_id="cli-123")
    ctx["db"].store[ApiKey].append(ak)
    r = ctx["client"].post(
        BATCH, json={"itens": [_item("lexml:lgpd", client_id="outro-cliente")]},
        headers={"X-API-Key": chave})
    assert r.status_code == 422
    assert "difere do client_id fixado na chave" in r.json()["detail"]
    assert not [d for d in ctx["db"].store[KnowledgeDoc] if d.chave_origem == "lexml:lgpd"]


def test_batch_limite_de_100_itens(ctx):
    itens = [_item(f"k:{i}") for i in range(101)]
    r = ctx["client"].post(BATCH, json={"itens": itens},
                           headers={"X-API-Key": ctx["chave"]})
    assert r.status_code == 422


# ── 3. Status de indexação ────────────────────────────────────────────────────

def test_status_por_chaves(ctx):
    h = {"X-API-Key": ctx["chave"]}
    ctx["client"].post(BATCH, json={"itens": [_item("lexml:a"), _item("lexml:b")]},
                       headers=h)
    r = ctx["client"].get(STATUS, params={"chaves": "lexml:a,lexml:b,nao-existe"},
                          headers=h)
    assert r.status_code == 200
    docs = {d["chave_origem"]: d for d in r.json()["docs"]}
    assert docs["lexml:a"]["status_indexacao"] == "pendente"   # embeddings off
    assert docs["lexml:a"]["doc_id"] and docs["lexml:a"]["versao"] == 1
    assert docs["nao-existe"]["status_indexacao"] == "nao_encontrado"
    assert docs["nao-existe"]["doc_id"] is None


def test_status_exige_api_key(ctx):
    r = ctx["client"].get(STATUS, params={"chaves": "x"})
    assert r.status_code == 401


# ── 4. SSRF do callback_url + resiliência do POST ────────────────────────────

def test_validar_callback_url_bloqueia_ips_privados_e_loopback():
    from app.routers.rag_public import validar_callback_url
    for url in (
        "http://127.0.0.1/hook",
        "http://localhost/hook",
        "http://10.0.0.5/hook",
        "http://192.168.1.1/hook",
        "http://169.254.169.254/hook",   # metadata endpoint (cloud)
        "http://[::1]/hook",
        "http://0.0.0.0/hook",
    ):
        with pytest.raises(ValueError):
            validar_callback_url(url, exigir_https=False)


def test_validar_callback_url_esquema_e_https():
    from app.routers.rag_public import validar_callback_url
    with pytest.raises(ValueError):
        validar_callback_url("ftp://example.com/hook", exigir_https=False)
    # produção: https obrigatório
    with pytest.raises(ValueError):
        validar_callback_url("http://93.184.216.34/hook", exigir_https=True)
    # IP público + https → passa (sem depender de DNS)
    validar_callback_url("https://93.184.216.34/hook", exigir_https=True)


def test_batch_rejeita_callback_url_ssrf(ctx):
    r = ctx["client"].post(
        BATCH,
        json={"itens": [_item()], "callback_url": "http://127.0.0.1:8000/hook"},
        headers={"X-API-Key": ctx["chave"]})
    assert r.status_code == 422
    assert "callback_url" in r.json()["detail"]


async def test_postar_callback_falha_so_loga(monkeypatch):
    """2 tentativas, timeout curto; exceção NUNCA propaga."""
    import app.routers.rag_public as rp

    chamadas = []

    class _FalhaClient:
        def __init__(self, *a, **kw):
            assert kw.get("timeout") == 5.0
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def post(self, url, json=None):
            chamadas.append(url)
            raise rp.httpx.ConnectError("recusado")

    monkeypatch.setattr(rp.httpx, "AsyncClient", _FalhaClient)
    ok = await rp._postar_callback("https://93.184.216.34/hook", {"lote_id": "x"})
    assert ok is False
    assert len(chamadas) == 2   # exatamente 2 tentativas


# ── 5. Administração de chaves (JWT admin) ────────────────────────────────────

class _AdminFake:
    id = "admin-1"
    role = "admin"


@pytest.fixture()
def admin_ctx(ctx):
    """Sobrepõe o get_current_user (JWT) por um admin fake; o middleware global
    ainda exige um Bearer válido — geramos um com a SECRET_KEY efêmera de dev."""
    from app.core.security import get_current_user, create_access_token
    app = ctx["app"]
    app.dependency_overrides[get_current_user] = lambda: _AdminFake()
    token = create_access_token("admin-1", "admin")
    ctx["auth"] = {"Authorization": f"Bearer {token}"}
    return ctx


def test_admin_cria_chave_e_recebe_segredo_uma_vez(admin_ctx):
    r = admin_ctx["client"].post(
        "/api/api-keys", json={"nome": "n8n produção"},
        headers=admin_ctx["auth"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["chave"].startswith("ejc_")
    assert body["escopo"] == "knowledge:write"
    # a listagem NÃO expõe a chave nem o hash
    r2 = admin_ctx["client"].get("/api/api-keys", headers=admin_ctx["auth"])
    assert r2.status_code == 200
    listado = next(a for a in r2.json()["data"] if a["nome"] == "n8n produção")
    assert "chave" not in listado and "chave_hash" not in listado
    assert listado["prefixo"] == body["chave"][:12]


def test_admin_escopo_invalido_422(admin_ctx):
    r = admin_ctx["client"].post(
        "/api/api-keys", json={"nome": "chave ruim", "escopo": "root:tudo"},
        headers=admin_ctx["auth"])
    assert r.status_code == 422


def test_admin_revoga_chave_e_ela_para_de_funcionar(admin_ctx):
    r = admin_ctx["client"].post(
        "/api/api-keys", json={"nome": "temporária"}, headers=admin_ctx["auth"])
    chave, key_id = r.json()["chave"], r.json()["id"]
    # funciona antes da revogação
    ok = admin_ctx["client"].post(BATCH, json={"itens": [_item("k:rev")]},
                                  headers={"X-API-Key": chave})
    assert ok.status_code == 201
    # revoga
    rv = admin_ctx["client"].post(f"/api/api-keys/{key_id}/revogar",
                                  headers=admin_ctx["auth"])
    assert rv.status_code == 200 and rv.json()["revoked_at"] is not None
    # 401 depois
    neg = admin_ctx["client"].post(BATCH, json={"itens": [_item("k:rev2")]},
                                   headers={"X-API-Key": chave})
    assert neg.status_code == 401


# ── 6. Auditoria de segurança (A-1, M-1, M-2, M-3) ────────────────────────────

def _addrinfo(ip: str):
    fam = 10 if ":" in ip else 2
    return [(fam, 1, 6, "", (ip, 0))]


# A-1: isolamento cross-tenant no GET /status --------------------------------

def test_status_chave_restrita_nao_enxerga_doc_de_outro_cliente(ctx):
    """Chave do cliente A consultando chave_origem do cliente B recebe
    `nao_encontrado` — como se o documento não existisse (fail-closed)."""
    chave_b, ak_b = _nova_chave(client_id="cli-b")
    ctx["db"].store[ApiKey].append(ak_b)
    ctx["client"].post(BATCH, json={"itens": [_item("lexml:doc-b")]},
                       headers={"X-API-Key": chave_b})

    chave_a, ak_a = _nova_chave(client_id="cli-a")
    ctx["db"].store[ApiKey].append(ak_a)
    r = ctx["client"].get(STATUS, params={"chaves": "lexml:doc-b"},
                          headers={"X-API-Key": chave_a})
    assert r.status_code == 200
    doc = r.json()["docs"][0]
    assert doc["status_indexacao"] == "nao_encontrado"
    assert doc["doc_id"] is None

    # a própria chave do cliente B continua enxergando o documento
    r_b = ctx["client"].get(STATUS, params={"chaves": "lexml:doc-b"},
                            headers={"X-API-Key": chave_b})
    assert r_b.json()["docs"][0]["status_indexacao"] != "nao_encontrado"


def test_status_chave_global_continua_enxergando_tudo(ctx):
    chave_b, ak_b = _nova_chave(client_id="cli-b")
    ctx["db"].store[ApiKey].append(ak_b)
    ctx["client"].post(BATCH, json={"itens": [_item("lexml:doc-b2")]},
                       headers={"X-API-Key": chave_b})
    r = ctx["client"].get(STATUS, params={"chaves": "lexml:doc-b2"},
                          headers={"X-API-Key": ctx["chave"]})  # sem client_id
    assert r.json()["docs"][0]["status_indexacao"] != "nao_encontrado"


# M-1: rate limit PRÉ-auth por IP ---------------------------------------------

def test_chave_invalida_consome_cota_por_ip_e_leva_429(ctx):
    from app.core.api_key_auth import MAX_TENTATIVAS_IP_MIN
    h = {"X-API-Key": "ejc_forca-bruta"}
    for _ in range(MAX_TENTATIVAS_IP_MIN):
        r = ctx["client"].get(STATUS, params={"chaves": "x"}, headers=h)
        assert r.status_code == 401
    r = ctx["client"].get(STATUS, params={"chaves": "x"}, headers=h)
    assert r.status_code == 429
    assert "Retry-After" in r.headers
    # e SEM chave nenhuma também é limitado (pré-auth de verdade)
    r2 = ctx["client"].get(STATUS, params={"chaves": "x"})
    assert r2.status_code == 429


# M-2: DNS rebinding do callback_url ------------------------------------------

def test_validar_callback_url_retorna_ip_publico(monkeypatch):
    import app.core.safe_outbound_url as sou
    import app.routers.rag_public as rp
    monkeypatch.setattr(sou.socket, "getaddrinfo",
                        lambda host, port: _addrinfo("93.184.216.34"))
    ip = rp.validar_callback_url("https://exemplo.com/hook", exigir_https=False)
    assert ip == "93.184.216.34"


async def test_postar_callback_fixa_ip_com_host_e_sni(monkeypatch):
    import app.routers.rag_public as rp
    capturas = []

    class _CapClient:
        def __init__(self, *a, **kw):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def post(self, url, json=None, headers=None, extensions=None):
            capturas.append((url, headers, extensions))
            class _R:
                def raise_for_status(self):
                    pass
            return _R()

    monkeypatch.setattr(rp.httpx, "AsyncClient", _CapClient)
    ok = await rp._postar_callback("https://exemplo.com:8443/hook?x=1",
                                   {"lote_id": "l1"}, ip="93.184.216.34")
    assert ok is True
    url, headers, extensions = capturas[0]
    assert url == "https://93.184.216.34:8443/hook?x=1"   # conecta no IP fixado
    assert headers["Host"] == "exemplo.com"              # host original preservado
    assert extensions["sni_hostname"] == "exemplo.com"   # SNI/verificação TLS


def test_dns_rebinding_entre_validacao_e_post_nao_tem_efeito(ctx, monkeypatch):
    """DNS devolve IP público na validação e IP privado depois: o callback em
    background usa o IP FIXADO na validação — o IP privado nunca é alcançado."""
    import app.core.safe_outbound_url as sou
    import app.routers.rag_public as rp

    resolucoes = {"n": 0}

    def _dns_rebind(host, port):
        resolucoes["n"] += 1
        # 1ª resolução (validação) → público; depois → privado (rebinding)
        return _addrinfo("93.184.216.34" if resolucoes["n"] == 1 else "10.0.0.5")

    monkeypatch.setattr(sou.socket, "getaddrinfo", _dns_rebind)

    capturas = []

    class _CapClient:
        def __init__(self, *a, **kw):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def post(self, url, json=None, headers=None, extensions=None):
            capturas.append((url, headers))
            class _R:
                def raise_for_status(self):
                    pass
            return _R()

    monkeypatch.setattr(rp.httpx, "AsyncClient", _CapClient)

    class _FakeSessionCtx:
        async def __aenter__(self):
            return ctx["db"]
        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(rp, "AsyncSessionLocal", lambda: _FakeSessionCtx())

    r = ctx["client"].post(
        BATCH,
        json={"itens": [_item("lexml:rebind")],
              "callback_url": "http://rebind.example/hook"},
        headers={"X-API-Key": ctx["chave"]})
    assert r.status_code == 201
    assert r.json()["callback_agendado"] is True
    # o POST do callback (background) foi para o IP público FIXADO
    assert capturas, "callback não foi disparado"
    url, headers = capturas[0]
    assert url.startswith("http://93.184.216.34/")
    assert headers["Host"] == "rebind.example"
    assert "10.0.0.5" not in url


# M-3: DoS de memória (tetos de conteúdo) --------------------------------------

def test_item_conteudo_acima_do_teto_vira_erro_sem_derrubar_lote(ctx):
    from app.routers.rag_public import MAX_CHARS_ITEM
    itens = [_item("lexml:ok"),
             _item("lexml:gigante", conteudo="x" * (MAX_CHARS_ITEM + 1))]
    r = ctx["client"].post(BATCH, json={"itens": itens},
                           headers={"X-API-Key": ctx["chave"]})
    assert r.status_code == 201
    body = r.json()
    assert body["novo"] == 1 and body["erro"] == 1
    assert "conteudo" in body["itens"][1]["erro"]


def test_lote_acima_do_teto_agregado_422(ctx):
    from app.routers.rag_public import MAX_CHARS_ITEM, MAX_CHARS_LOTE
    por_item = MAX_CHARS_ITEM - 10_000
    n = MAX_CHARS_LOTE // por_item + 2   # garante estourar o agregado
    itens = [_item(f"k:big-{i}", conteudo="x" * por_item) for i in range(n)]
    r = ctx["client"].post(BATCH, json={"itens": itens},
                           headers={"X-API-Key": ctx["chave"]})
    assert r.status_code == 422
    assert "agregado" in r.json()["detail"]
