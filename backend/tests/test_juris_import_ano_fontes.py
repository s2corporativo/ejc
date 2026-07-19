"""Testes: filtro de ANO + cobertura TJMG/TRT/Turma Recursal no juris_import.

ATENÇÃO — FIXTURES 100% SINTÉTICAS: todo XML/HTML/registro abaixo é INVENTADO
para exercitar parsers e filtros. NENHUM texto representa julgado, ementa ou
tese REAL, e nada daqui é ingerido como conteúdo real (regra da casa: nenhum
texto de julgado entra escrito de memória de modelo). As ementas trazem o
marcador "REGISTRO SINTÉTICO DE TESTE" no próprio corpo.

Sem rede: respostas injetadas por monkeypatch (mesmo padrão de
test_juris_import.py). Cobre: filtro de ano client-side (lexml/stj/tjmg e
garantia final em importar_julgados), mapeamento de siglas TJMG/TRT-n/JEC,
filtro client-side de tribunal sem refinamento de URN, fonte tjmg registrada
com keyspace de dedup compartilhado com o ingestor agendado, e contrato
aditivo `ano` no router.
"""
from __future__ import annotations

import pytest

from app.models.user import User, UserRole
from app.services.juris_import import FONTES
from app.services.juris_import import base as ji_base
from app.services.juris_import import ingest as ji_ingest
from app.services.juris_import import lexml as ji_lexml
from app.services.juris_import import stj as ji_stj
from app.services.juris_import import tjmg as ji_tjmg
from app.services.juris_import.base import JulgadoNormalizado


# ── Fixture SINTÉTICA: XML SRW/SRU com TJMG, TRT e Turma Recursal ────────────
# Estrutura segue o contrato SRW 1.1 + Dublin Core documentado em
# juris_import/lexml.py; URNs e conteúdos são FICTÍCIOS (dados de teste).

_EMENTA_BASE = ("REGISTRO SINTÉTICO DE TESTE — NÃO É JULGADO REAL. "
                "Conteúdo fictício com tamanho suficiente para o filtro "
                "mínimo de cinquenta caracteres do normalizador. ")


def _rec(urn: str, titulo: str, data: str, tipo: str = "Acórdão",
         facet: str = "Jurisprudência::Acórdão", autoridade: str = "") -> str:
    return f"""
    <srw:record>
      <srw:recordData>
        <srw_dc:dc xmlns:srw_dc="info:srw/schema/1/dc-schema"
                   xmlns:dc="http://purl.org/dc/elements/1.1/">
          <urn>{urn}</urn>
          <tipoDocumento>{tipo}</tipoDocumento>
          <facet-tipoDocumento>{facet}</facet-tipoDocumento>
          <dc:title>{titulo}</dc:title>
          <dc:description>{_EMENTA_BASE}DANO MORAL SINTETICO.</dc:description>
          <dc:date>{data}</dc:date>
          <dc:identifier>https://www.lexml.gov.br/urn/{urn}</dc:identifier>
          {f'<autoridade>{autoridade}</autoridade>' if autoridade else ''}
        </srw_dc:dc>
      </srw:recordData>
    </srw:record>"""


_LEXML_XML_SINTETICO = f"""<?xml version="1.0" encoding="UTF-8"?>
<srw:searchRetrieveResponse xmlns:srw="http://www.loc.gov/zing/srw/">
  <srw:version>1.1</srw:version>
  <srw:numberOfRecords>5</srw:numberOfRecords>
  <srw:records>
    {_rec("urn:lex:br;minas.gerais:tribunal.justica;5.camara.civel:acordao;"
          "2026-03-10;9990001", "Acórdão sintético TJMG 2026", "2026-03-10",
          autoridade="Tribunal de Justiça de Minas Gerais")}
    {_rec("urn:lex:br;minas.gerais:tribunal.justica;5.camara.civel:acordao;"
          "2025-08-01;9990002", "Acórdão sintético TJMG 2025", "2025-08-01",
          autoridade="Tribunal de Justiça de Minas Gerais")}
    {_rec("urn:lex:br;justica.trabalho;regiao.3:tribunal.regional.trabalho;"
          "1.turma:acordao;2026-02-05;9990003",
          "Acórdão sintético TRT 3ª Região 2026", "2026-02-05",
          autoridade="Tribunal Regional do Trabalho da 3ª Região")}
    {_rec("urn:lex:br;minas.gerais:turma.recursal;juizado.especial.civel:"
          "acordao;2026-04-01;9990004",
          "Acórdão sintético Turma Recursal JEC 2026", "2026-04-01",
          autoridade="Turma Recursal dos Juizados Especiais")}
    {_rec("urn:lex:br;federal:lei:2026-01-05;99999",
          "Lei sintética (não jurisprudência)", "2026-01-05",
          tipo="Lei", facet="Legislação::Lei")}
  </srw:records>
</srw:searchRetrieveResponse>
"""


def _resp(text: str | None = None, json_data=None):
    class _R:
        pass
    r = _R()
    r.text = text or ""
    r.json = lambda: json_data
    return r


def _patch_lexml(monkeypatch, xml: str):
    chamadas: list[dict] = []

    async def fake_fetch(url, *, params=None, **kw):
        chamadas.append({"url": url, "params": params})
        return _resp(text=xml)

    monkeypatch.setattr(ji_lexml, "fetch", fake_fetch)
    return chamadas


# ── LexML: mapeamento de siglas client-side (TJMG / TRT-n / JEC) ─────────────

async def test_lexml_mapeia_siglas_tjmg_trt_jec(monkeypatch):
    _patch_lexml(monkeypatch, _LEXML_XML_SINTETICO)
    julgados = await ji_lexml.buscar("dano moral sintetico", limite=10)
    siglas = sorted(j.tribunal for j in julgados)
    # Lei filtrada (não é jurisprudência); Turma Recursal → JEC (antes do TJ).
    assert siglas == ["JEC", "TJMG", "TJMG", "TRT-3"]


def test_sigla_composta_fragmentos():
    f = ji_lexml._sigla_composta
    assert f("minas gerais tribunal justica 5 camara") == "TJMG"
    assert f("justica trabalho regiao 3 tribunal regional trabalho") == "TRT-3"
    assert f("tribunal regional trabalho") == "TRT"          # sem região → TRT
    assert f("minas gerais turma recursal juizado") == "JEC"
    assert f("juizado especial civel") == "JEC"
    assert f("qualquer outra autoridade") is None


def test_casa_tribunal_familia_e_exato():
    f = ji_lexml._casa_tribunal
    assert f("TJMG", "TJMG") and f("TRT-3", "TRT") and f("TRT-3", "TRT-3")
    assert not f("TRT", "TRT-3")     # registro sem região ≠ pedido específico
    assert not f("TJSP", "TJMG") and not f("TST", "TRT")


# ── LexML: filtro client-side de tribunal SEM refinamento de URN ─────────────

async def test_lexml_filtra_tjmg_client_side_sem_refinar_urn(monkeypatch):
    chamadas = _patch_lexml(monkeypatch, _LEXML_XML_SINTETICO)
    julgados = await ji_lexml.buscar("dano moral sintetico", tribunal="TJMG",
                                     limite=10)
    assert {j.tribunal for j in julgados} == {"TJMG"}
    assert len(julgados) == 2
    # LIMITAÇÃO documentada: TJMG não tem autoridade estável em _URN_TRIBUNAL
    # → a CQL vai SEM refinamento server-side (filtro só no cliente).
    assert "urn any" not in chamadas[0]["params"]["query"]


async def test_lexml_filtra_familia_trt_client_side(monkeypatch):
    _patch_lexml(monkeypatch, _LEXML_XML_SINTETICO)
    julgados = await ji_lexml.buscar("dano moral", tribunal="TRT", limite=10)
    assert [j.tribunal for j in julgados] == ["TRT-3"]
    julgados = await ji_lexml.buscar("dano moral", tribunal="JEC", limite=10)
    assert [j.tribunal for j in julgados] == ["JEC"]


# ── LexML: filtro de ANO client-side ─────────────────────────────────────────

async def test_lexml_filtro_ano_2026(monkeypatch):
    _patch_lexml(monkeypatch, _LEXML_XML_SINTETICO)
    julgados = await ji_lexml.buscar("dano moral", tribunal="TJMG",
                                     limite=10, ano=2026)
    assert len(julgados) == 1
    assert julgados[0].data == "2026-03-10"       # o de 2025 fica de fora
    julgados = await ji_lexml.buscar("dano moral", tribunal="TJMG",
                                     limite=10, ano=2025)
    assert [j.data for j in julgados] == ["2025-08-01"]


def test_no_ano_regras():
    assert ji_base.no_ano("2026-03-10", 2026) is True
    assert ji_base.no_ano("2025-12-31", 2026) is False
    assert ji_base.no_ano(None, 2026) is False     # sem data comprovada → fora
    assert ji_base.no_ano("data-invalida", 2026) is False
    assert ji_base.no_ano(None, None) is True      # sem filtro → tudo passa


# ── STJ: filtro de ano no lote CKAN ──────────────────────────────────────────

_STJ_PACKAGE = {"result": {"resources": [
    {"format": "JSON", "name": "20260601.json",
     "url": "https://dadosabertos.web.stj.jus.br/dataset/x/20260601.json"},
]}}
# Registros SINTÉTICOS (dados de teste — não são acórdãos reais).
_STJ_RECORDS = [
    {"numeroRegistro": "202600000001", "numeroProcesso": "9000001",
     "siglaClasse": "REsp", "ministroRelator": "SINTETICA UM",
     "nomeOrgaoJulgador": "Turma Sintética", "dataDecisao": "2026-05-12",
     "ementa": _EMENTA_BASE + "DANO MORAL SINTETICO EM 2026."},
    {"numeroRegistro": "202500000002", "numeroProcesso": "9000002",
     "siglaClasse": "REsp", "ministroRelator": "SINTETICA DOIS",
     "nomeOrgaoJulgador": "Turma Sintética", "dataDecisao": "2025-11-20",
     "ementa": _EMENTA_BASE + "DANO MORAL SINTETICO EM 2025."},
]


async def test_stj_filtro_ano_2026(monkeypatch):
    async def fake_fetch(url, *, params=None, **kw):
        if url.endswith("/package_show"):
            return _resp(json_data=_STJ_PACKAGE)
        return _resp(json_data=_STJ_RECORDS)

    monkeypatch.setattr(ji_stj, "fetch", fake_fetch)
    julgados = await ji_stj.buscar("dano moral sintetico", limite=10, ano=2026)
    assert [j.numero for j in julgados] == ["9000001"]
    assert julgados[0].data == "2026-05-12"


# ── Fonte TJMG (juris_import/tjmg.py) ────────────────────────────────────────

def _item_tjmg(numero: str, data: str | None, **kw) -> dict:
    """Item no formato do parser de jurisprudencia_externa (SINTÉTICO)."""
    return {
        "titulo": f"Acórdão TJMG {numero}",
        "ementa": _EMENTA_BASE + "NEGATIVACAO INDEVIDA SINTETICA.",
        "tribunal": "TJMG",
        "relator": kw.get("relator", "DES. SINTETICO"),
        "numero_acordao": numero,
        "data_julgamento": data,
        "fonte": "TJMG",
        "link_original": (f"https://www5.tjmg.jus.br/jurisprudencia/"
                          f"formEspelhoAcordao.do?numeroRegistro={numero}"),
        "area_juridica": "Consumidor",
        "orgao_julgador": kw.get("orgao", "5ª Câmara Cível"),
        "classe": kw.get("classe", "Apelação Cível"),
        **{k: v for k, v in kw.items() if k in ()},
    }


async def test_tjmg_fonte_normaliza_e_filtra_ano(monkeypatch):
    chamadas: list[dict] = []

    async def fake_buscar_tjmg(palavras, pagina=1, por_pagina=10, *,
                               data_inicial="", data_final="", **kw):
        chamadas.append({"palavras": palavras, "pagina": pagina,
                         "data_inicial": data_inicial,
                         "data_final": data_final})
        return [
            _item_tjmg("1.0000.26.000001-1", "2026-03-10"),
            _item_tjmg("1.0000.25.000002-2", "2025-07-01"),   # fora do ano
            _item_tjmg("1.0000.26.000003-3", None),           # sem data → fora
            dict(_item_tjmg("", "2026-01-01"),                # sem número
                 link_original=""),
        ]

    monkeypatch.setattr(ji_tjmg, "buscar_tjmg", fake_buscar_tjmg)
    julgados = await ji_tjmg.buscar("negativação indevida", limite=10, ano=2026)

    assert len(julgados) == 1
    j = julgados[0]
    assert j.tribunal == "TJMG" and j.data == "2026-03-10"
    assert j.relator == "DES. SINTETICO"
    assert j.orgao_julgador == "5ª Câmara Cível"
    assert j.url_fonte.startswith("https://www5.tjmg.jus.br/")
    # Keyspace COMPARTILHADO com o ingestor agendado (ingestors/tjmg.py):
    assert j.chave_dedup() == "tjmg:1.0000.26.000001-1"
    # …e a canônica por tribunal+dígitos segue no dedup como chave extra.
    assert "julgado:TJMG:10000260000011" in j.chaves_dedup()
    # Janela de datas do ano vai SERVER-SIDE ao formulário do TJMG…
    assert chamadas[0]["data_inicial"] == "01/01/2026"
    assert chamadas[0]["data_final"] == "31/12/2026"
    # …e o client-side (no_ano) segue como garantia (2025 e sem-data barrados).


async def test_tjmg_fonte_tribunal_diferente_sem_rede(monkeypatch):
    async def fake_buscar_tjmg(*a, **kw):
        raise AssertionError("não deveria consultar a fonte")

    monkeypatch.setattr(ji_tjmg, "buscar_tjmg", fake_buscar_tjmg)
    assert await ji_tjmg.buscar("dano moral", tribunal="STJ", limite=5) == []


async def test_tjmg_fonte_fail_safe_fonte_vazia(monkeypatch):
    """HTML mudou/rede caiu → buscar_tjmg degrada p/ [] e a fonte não quebra."""
    async def fake_buscar_tjmg(*a, **kw):
        return []

    monkeypatch.setattr(ji_tjmg, "buscar_tjmg", fake_buscar_tjmg)
    assert await ji_tjmg.buscar("dano moral", limite=5, ano=2026) == []


def test_tjmg_fonte_registrada_no_registry():
    assert "tjmg" in FONTES
    assert FONTES["tjmg"]["enabled"] is True
    assert FONTES["tjmg"]["buscar"] is ji_tjmg.buscar


# ── Ingestão: garantia final de ano + dedup cross-keyspace + metadados ───────

class _Res:
    def __init__(self, valor):
        self._v = valor

    def scalar_one_or_none(self):
        return self._v


class _FakeDB:
    def __init__(self, existentes: set[str]):
        self.existentes = existentes
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, q):
        chaves: list[str] = []
        for v in q.compile().params.values():
            if isinstance(v, (list, tuple)):
                chaves.extend(x for x in v if isinstance(x, str))
            elif isinstance(v, str):
                chaves.append(v)
        return _Res("doc-existente"
                    if any(c in self.existentes for c in chaves) else None)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _julgado(numero: str, data: str | None, tribunal="TJMG", **kw):
    return JulgadoNormalizado(
        tribunal=tribunal, numero=numero, data=data,
        ementa=_EMENTA_BASE + "CONTEUDO CITAVEL SINTETICO.",
        url_fonte=f"https://www5.tjmg.jus.br/x?numeroRegistro={numero}", **kw)


async def test_importar_julgados_garantia_final_de_ano(monkeypatch):
    gravados: list[dict] = []

    async def fake_upsert(db, **kw):
        gravados.append(kw)
        return "novo"

    monkeypatch.setattr(ji_ingest, "upsert_documento", fake_upsert)
    db = _FakeDB(existentes=set())
    julgados = [
        _julgado("100", "2026-02-01"),
        _julgado("200", "2025-02-01"),   # conector deixou passar → barra aqui
        _julgado("300", None),           # sem data → barra
    ]
    resumo = await ji_ingest.importar_julgados(
        db, julgados, fonte_slug="t", ano=2026)
    assert resumo == {"importados": 1, "duplicados": 0, "erros": 0,
                      "fora_do_ano": 2}
    # Metadados de CITAÇÃO gravados no extra (tribunal/número/data/url):
    doc = gravados[0]
    assert doc["tribunal"] == "TJMG"
    assert doc["extra"]["data_julgamento"] == "2026-02-01"
    assert doc["extra"]["url_fonte"].startswith("https://www5.tjmg.jus.br/")
    assert doc["extra"]["fonte_validada"] is True
    assert doc["categoria"] == "jurisprudencia"


async def test_importar_sem_ano_mantem_contrato_antigo(monkeypatch):
    async def fake_upsert(db, **kw):
        return "novo"

    monkeypatch.setattr(ji_ingest, "upsert_documento", fake_upsert)
    resumo = await ji_ingest.importar_julgados(
        _FakeDB(set()), [_julgado("100", "2025-02-01")], fonte_slug="t")
    # SEM ano: nada é filtrado e a chave "fora_do_ano" NÃO aparece (aditivo).
    assert resumo == {"importados": 1, "duplicados": 0, "erros": 0}


async def test_importar_dedup_com_keyspace_do_ingestor_agendado(monkeypatch):
    async def fake_upsert(db, **kw):
        raise AssertionError("já existe pelo crawler agendado — não regrava")

    monkeypatch.setattr(ji_ingest, "upsert_documento", fake_upsert)
    # Doc já ingerido pelo crawler agendado do TJMG (chave tjmg:<registro>).
    db = _FakeDB(existentes={"tjmg:1.0000.26.000001-1"})
    j = _julgado("1.0000.26.000001-1", "2026-03-10",
                 chave_principal="tjmg:1.0000.26.000001-1")
    resumo = await ji_ingest.importar_julgados(db, [j], fonte_slug="tjmg",
                                               ano=2026)
    assert resumo["duplicados"] == 1 and resumo["importados"] == 0


# ── Router: contrato aditivo `ano` ───────────────────────────────────────────

async def test_router_aceita_e_propaga_ano():
    from fastapi import BackgroundTasks
    from app.routers.juris_import import (
        ImportarJurisRequest, importar_jurisprudencia,
    )

    agendados: list[tuple] = []

    class _BT(BackgroundTasks):
        def add_task(self, fn, *a, **kw):
            agendados.append((fn, a, kw))

    req = ImportarJurisRequest(fonte="tjmg", consulta="negativação indevida",
                               tribunal="TJMG", limite=50, ano=2026)
    out = await importar_jurisprudencia(
        req, _BT(), cu=User(id="u1", role=UserRole.advogado))
    assert out["status"] == "executando" and out["fonte"] == "tjmg"
    fn, args, kw = agendados[0]
    assert fn is ji_ingest.executar_importacao
    assert kw.get("ano") == 2026


def test_router_ano_opcional_e_validado():
    from pydantic import ValidationError
    from app.routers.juris_import import ImportarJurisRequest

    # Sem `ano` — contrato antigo intacto.
    r = ImportarJurisRequest(fonte="lexml", consulta="dano moral")
    assert r.ano is None
    with pytest.raises(ValidationError):
        ImportarJurisRequest(fonte="lexml", consulta="dano moral", ano=99)


# ── executar_importacao: ano propagado à fonte e ao resumo ───────────────────

async def test_executar_importacao_propaga_ano(monkeypatch):
    recebidos: dict = {}

    async def fake_buscar(consulta, tribunal=None, limite=20, ano=None):
        recebidos.update(consulta=consulta, tribunal=tribunal,
                         limite=limite, ano=ano)
        return [_julgado("100", "2026-02-01"), _julgado("200", "2025-01-01")]

    async def fake_importar(db, julgados, *, fonte_slug, ano=None):
        aceitos = [j for j in julgados if ji_base.no_ano(j.data, ano)]
        return {"importados": len(aceitos), "duplicados": 0, "erros": 0,
                "fora_do_ano": len(julgados) - len(aceitos)}

    class _DB:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def commit(self):
            pass

    async def _noop(*a, **kw):
        return None

    monkeypatch.setitem(FONTES, "fake", {"slug": "fake", "descricao": "t",
                                         "enabled": True,
                                         "buscar": fake_buscar})
    monkeypatch.setattr(ji_ingest, "importar_julgados", fake_importar)
    monkeypatch.setattr(ji_ingest, "registrar_fonte", _noop)
    monkeypatch.setattr(ji_ingest, "marcar_execucao", _noop)
    monkeypatch.setattr(ji_ingest, "criar_audit_log", _noop)
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", _DB)

    await ji_ingest.executar_importacao(
        "job-ano", "fake", "dano moral", "TJMG", 50, "u1", "advogado",
        ano=2026)
    assert recebidos["ano"] == 2026
    st = ji_ingest.status_job("job-ano")
    assert st["status"] == "concluido" and st["ano"] == 2026
    assert st["resumo"] == {"importados": 1, "duplicados": 0, "erros": 0,
                            "fora_do_ano": 1}
