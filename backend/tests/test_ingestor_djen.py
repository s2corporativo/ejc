"""Fase 3B — Ingestor DJEN (API Comunica/CNJ → RAG).

Cobre (SEM rede — a API não é alcançável neste ambiente; validação real só
na VPS):
1) parse_oabs: CSV de settings tolerante a lixo.
2) montar_documento: normalização de item real da API (camelCase e
   snake_case), limpeza de HTML, fallback de nº CNJ pelo texto.
3) chave_origem determinística/idempotente (com id e sem id → hash estável).
4) ingerir(): paginação sequencial mockada, upsert por item, tolerância a
   item malformado e a erro HTTP por OAB (não derruba as demais).
5) Gate do scheduler: job_ingestao_djen é no-op com DJEN_INGEST_ENABLED=False
   (default) e executa quando ligado.
"""
from __future__ import annotations

import copy

import httpx

import app.services.ingestors.djen as djen
from app.core.config import get_settings

# ── Fixture: formato real da API Comunica (GET /api/v1/comunicacao) ─────────
ITEM_COMPLETO = {
    "id": 987654,
    "numeroProcesso": "0001234-56.2025.8.13.0027",
    "siglaTribunal": "TJMG",
    "tipoComunicacao": "Intimação",
    "nomeOrgao": "2ª Vara Cível da Comarca de Betim",
    "texto": "<p>Fica o advogado <b>intimado</b> da sentença proferida nos "
             "autos do processo 0001234-56.2025.8.13.0027, para os devidos "
             "fins de direito e apresentação de eventual recurso.</p>",
    "dataDisponibilizacao": "2026-07-03",
    "link": "https://comunica.pje.jus.br/consulta?id=987654",
}

ITEM_SEM_ID = {
    # variante snake_case, sem id/hash e sem nº de processo estruturado —
    # o nº deve vir do texto (padrão CNJ) e a chave, de hash determinístico
    "sigla_tribunal": "TRT3",
    "tipo_comunicacao": "Edital",
    "texto": "Edital de citação referente ao processo "
             "0007777-88.2024.5.03.0142, publicado para ciência de terceiros "
             "interessados nos termos da legislação vigente.",
    "data_disponibilizacao": "2026-07-02",
}

RESPOSTA_API = {"status": "success", "count": 2,
                "items": [ITEM_COMPLETO, ITEM_SEM_ID]}


# ── 1. parse_oabs ────────────────────────────────────────────────────────────

def test_parse_oabs_csv_valido_e_tolerante():
    assert djen.parse_oabs("12345/MG, 67.890/mg ,") == [
        ("12345", "MG"), ("67890", "MG"),
    ]
    assert djen.parse_oabs("") == []
    assert djen.parse_oabs(None) == []
    # entradas inválidas são ignoradas sem exceção
    assert djen.parse_oabs("semuf,123/XYZ,/MG,abc/12") == []


# ── 2. montar_documento ──────────────────────────────────────────────────────

def test_montar_documento_item_completo():
    doc = djen.montar_documento(ITEM_COMPLETO)
    assert doc is not None
    assert doc["categoria"] == "comunicacao_processual"
    assert doc["fonte"] == "djen"
    assert doc["tribunal"] == "TJMG"
    assert doc["confianca"] == "alta"
    assert doc["chave_origem"] == "djen:987654"
    # HTML removido, conteúdo citável presente
    assert "<p>" not in doc["conteudo"] and "<b>" not in doc["conteudo"]
    assert "intimado" in doc["conteudo"]
    assert "0001234-56.2025.8.13.0027" in doc["conteudo"]
    # metadados para auditoria/consulta
    extra = doc["extra"]
    assert extra["numero_processo"] == "00012345620258130027"  # normalizado
    assert extra["tipo_comunicacao"] == "Intimação"
    assert extra["orgao"].startswith("2ª Vara")
    assert extra["data_disponibilizacao"] == "2026-07-03"
    assert extra["link"] == ITEM_COMPLETO["link"]


def test_montar_documento_snake_case_e_cnj_do_texto():
    doc = djen.montar_documento(ITEM_SEM_ID)
    assert doc is not None
    assert doc["tribunal"] == "TRT3"
    # nº de processo extraído do texto (fallback CNJ)
    assert doc["extra"]["numero_processo"] == "00077778820245030142"
    assert doc["extra"]["data_disponibilizacao"] == "2026-07-02"


def test_montar_documento_malformado_retorna_none():
    assert djen.montar_documento({}) is None                 # sem texto
    assert djen.montar_documento({"texto": "<p></p>"}) is None
    assert djen.montar_documento("não é dict") is None
    assert djen.montar_documento(None) is None


# ── 3. chave_origem determinística ───────────────────────────────────────────

def test_chave_origem_deterministica_e_idempotente():
    assert djen.chave_origem(ITEM_COMPLETO) == "djen:987654"
    assert djen.chave_origem({"hash": "abc123"}) == "djen:abc123"
    # sem id/hash → hash SHA-1 estável dos campos identificadores
    k1 = djen.chave_origem(ITEM_SEM_ID)
    k2 = djen.chave_origem(copy.deepcopy(ITEM_SEM_ID))
    assert k1 == k2 and k1.startswith("djen:") and len(k1) == 5 + 40
    # item diferente → chave diferente
    outro = {**ITEM_SEM_ID, "texto": "outro conteúdo qualquer de edital"}
    assert djen.chave_origem(outro) != k1


# ── Infra de mock (sem rede, sem banco) ──────────────────────────────────────

class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _FakeDB:
    async def commit(self):
        pass

    async def rollback(self):
        pass


class _FakeCaso:
    """Caso ativo devolvido pelo resolvedor por nº de processo (id + client_id)."""
    def __init__(self, id="case-1", client_id="cli-1"):
        self.id = id
        self.client_id = client_id


_SEM_CASO = object()  # sentinela: distingue "default (resolve)" de "None (não resolve)"


def _prepara(monkeypatch, *, oabs="12345/MG", respostas=None, upserts=None, caso=_SEM_CASO):
    """Configura settings + mocks de fetch/upsert/resolvedor no namespace do módulo."""
    s = get_settings()
    monkeypatch.setattr(s, "DJEN_OABS_MONITORADAS", oabs)
    monkeypatch.setattr(s, "DJEN_INGEST_JANELA_DIAS", 2)
    monkeypatch.setattr(djen, "PAUSA_ENTRE_PAGINAS", 0)

    # Auditoria RAG/LGPD: a ingestão DJEN resolve o caso ATIVO pelo nº do
    # processo e só indexa vinculada ao escopo tenant/caso. Por padrão o mock
    # resolve um caso; passe caso=None para exercitar o skip (PII de terceiros).
    caso_ret = _FakeCaso() if caso is _SEM_CASO else caso

    async def fake_buscar_caso(db, numero):
        return caso_ret

    monkeypatch.setattr(djen, "buscar_caso_ativo_por_processo", fake_buscar_caso)

    chamadas = []

    async def fake_fetch(url, *, params=None, **kw):
        chamadas.append(params)
        resp = respostas.pop(0) if respostas else {"items": []}
        if isinstance(resp, Exception):
            raise resp
        return _FakeResp(resp)

    monkeypatch.setattr(djen, "fetch", fake_fetch)

    async def fake_upsert(db, **kwargs):
        upserts.append(kwargs)
        return "novo"

    if upserts is not None:
        monkeypatch.setattr(djen, "upsert_documento", fake_upsert)
    return chamadas


# ── 4. ingerir() ─────────────────────────────────────────────────────────────

async def test_ingerir_upserta_cada_comunicacao(monkeypatch):
    ups: list[dict] = []
    chamadas = _prepara(monkeypatch, respostas=[dict(RESPOSTA_API)], upserts=ups)

    novos, total = await djen.ingerir(_FakeDB())
    assert (novos, total) == (2, 2)
    assert [u["chave_origem"] for u in ups][0] == "djen:987654"
    assert all(u["fonte"] == "djen" and u["confianca"] == "alta" for u in ups)
    assert all(u["extra"]["oab_monitorada"] == "12345/MG" for u in ups)
    # Auditoria RAG/LGPD: comunicação vinculada ao escopo tenant/caso resolvido
    # (nunca conhecimento global recuperável por qualquer cliente).
    assert all(u["case_id"] == "case-1" and u["client_id"] == "cli-1" for u in ups)
    # parâmetros da API: OAB + janela incremental + paginação conservadora
    p = chamadas[0]
    assert p["numeroOab"] == "12345" and p["ufOab"] == "MG"
    assert p["itensPorPagina"] == 100 and p["pagina"] == 1
    assert p["dataDisponibilizacaoInicio"] <= p["dataDisponibilizacaoFim"]
    # <100 itens na página → parou na primeira (sequencial, sem excesso)
    assert len(chamadas) == 1


async def test_ingerir_pagina_ate_lote_incompleto(monkeypatch):
    ups: list[dict] = []
    pagina_cheia = {"items": [
        {**ITEM_COMPLETO, "id": i} for i in range(djen.ITENS_POR_PAGINA)
    ]}
    chamadas = _prepara(
        monkeypatch,
        respostas=[pagina_cheia, {"items": [ITEM_SEM_ID]}],
        upserts=ups,
    )
    novos, total = await djen.ingerir(_FakeDB())
    assert len(chamadas) == 2                      # parou na página incompleta
    assert [c["pagina"] for c in chamadas] == [1, 2]
    assert total == djen.ITENS_POR_PAGINA + 1
    # chaves determinísticas distintas por item
    assert len({u["chave_origem"] for u in ups}) == total


async def test_ingerir_pula_comunicacao_sem_caso_ativo(monkeypatch):
    """Auditoria RAG/LGPD: comunicação de processo SEM caso ativo cadastrado
    NÃO entra no RAG global (contém PII de terceiros — partes, teor da
    intimação). É pulada: nenhum upsert, contadores zerados."""
    ups: list[dict] = []
    _prepara(monkeypatch, respostas=[dict(RESPOSTA_API)], upserts=ups, caso=None)
    novos, total = await djen.ingerir(_FakeDB())
    assert (novos, total) == (0, 0)
    assert ups == []


async def test_ingerir_sem_oabs_configuradas_e_noop(monkeypatch):
    ups: list[dict] = []
    chamadas = _prepara(monkeypatch, oabs="", respostas=[], upserts=ups)
    assert await djen.ingerir(_FakeDB()) == (0, 0)
    assert chamadas == [] and ups == []


async def test_ingerir_tolerante_a_erro_http_por_oab(monkeypatch):
    """Erro na 1ª OAB não impede a coleta da 2ª."""
    ups: list[dict] = []
    req = httpx.Request("GET", djen.BASE)
    erro = httpx.HTTPStatusError(
        "HTTP 500", request=req, response=httpx.Response(500, request=req),
    )
    _prepara(
        monkeypatch, oabs="12345/MG,67890/MG",
        respostas=[erro, {"items": [ITEM_COMPLETO]}], upserts=ups,
    )
    novos, total = await djen.ingerir(_FakeDB())
    assert (novos, total) == (1, 1)
    assert ups[0]["extra"]["oab_monitorada"] == "67890/MG"


async def test_ingerir_tolerante_a_resposta_malformada(monkeypatch):
    """Envelope inesperado / itens-lixo não derrubam a ingestão."""
    ups: list[dict] = []
    _prepara(
        monkeypatch,
        respostas=[{"items": ["string-lixo", {}, {"texto": None},
                              ITEM_COMPLETO, 42]}],
        upserts=ups,
    )
    novos, total = await djen.ingerir(_FakeDB())
    assert (novos, total) == (1, 1)                # só o item válido
    # payload sem "items" e não-lista → zero itens, sem exceção
    ups2: list[dict] = []
    _prepara(monkeypatch, respostas=[{"status": "error"}], upserts=ups2)
    assert await djen.ingerir(_FakeDB()) == (0, 0)


# ── 5. Gate no scheduler ─────────────────────────────────────────────────────

async def test_job_djen_gate_desligado_por_padrao(monkeypatch):
    from app.services import scheduler as sch
    import app.services.ingestion_service as ing

    assert get_settings().DJEN_INGEST_ENABLED is False   # default seguro

    execucoes = []

    async def fake_exec(slug, *a, **k):
        execucoes.append(slug)
        return (0, 0)

    monkeypatch.setattr(ing, "executar_ingestao", fake_exec)
    await sch.job_ingestao_djen()
    assert execucoes == []                               # no-op com gate off

    monkeypatch.setattr(get_settings(), "DJEN_INGEST_ENABLED", True)
    await sch.job_ingestao_djen()
    assert execucoes == ["djen"]


def test_job_djen_registrado_no_scheduler():
    """O add_job do ingestor DJEN está no start_scheduler (1x/dia)."""
    import inspect
    from app.services import scheduler as sch
    src = inspect.getsource(sch.start_scheduler)
    assert "job_ingestao_djen" in src and "ing_djen" in src
