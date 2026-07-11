"""Testes da importação de jurisprudência via APIs oficiais (juris_import).

Sem rede: as respostas das fontes são fixtures baseadas nos contratos
DOCUMENTADOS (LexML SRU — XML SRW/Dublin Core; STJ Dados Abertos CKAN —
espelhos de acórdãos JSON), injetadas por monkeypatch de `fetch`.
Cobre: normalização por fonte, filtro de tipo/termos, dedup por
tribunal+número e gate de papel (advogado+) do router.
"""
from __future__ import annotations

import pytest

from app.core.security import require_roles
from app.models.user import User, UserRole
from app.services.juris_import import base as ji_base
from app.services.juris_import import ingest as ji_ingest
from app.services.juris_import import lexml as ji_lexml
from app.services.juris_import import stj as ji_stj
from app.services.juris_import.base import JulgadoNormalizado


# ── Fixtures de resposta (contratos documentados) ────────────────────────────

# XML SRW 1.1 + Dublin Core, formato do serviço https://www.lexml.gov.br/busca/SRU
# (operation=searchRetrieve — ver cabeçalho de juris_import/lexml.py).
_LEXML_XML = """<?xml version="1.0" encoding="UTF-8"?>
<srw:searchRetrieveResponse xmlns:srw="http://www.loc.gov/zing/srw/">
  <srw:version>1.1</srw:version>
  <srw:numberOfRecords>2</srw:numberOfRecords>
  <srw:records>
    <srw:record>
      <srw:recordSchema>info:srw/schema/1/dc-v1.1</srw:recordSchema>
      <srw:recordData>
        <srw_dc:dc xmlns:srw_dc="info:srw/schema/1/dc-schema"
                   xmlns:dc="http://purl.org/dc/elements/1.1/">
          <urn>urn:lex:br:superior.tribunal.justica;turma.3:acordao;resp:2010-11-23;1186789</urn>
          <tipoDocumento>Acórdão</tipoDocumento>
          <facet-tipoDocumento>Jurisprudência::Acórdão</facet-tipoDocumento>
          <dc:title>REsp 1186789/SP</dc:title>
          <dc:description>DIREITO DO CONSUMIDOR. DANO MORAL. INSCRIÇÃO INDEVIDA
            EM CADASTRO DE INADIMPLENTES. Responsabilidade objetiva do fornecedor
            reconhecida pela Terceira Turma.</dc:description>
          <dc:date>2010-11-23</dc:date>
          <dc:identifier>https://www.lexml.gov.br/urn/urn:lex:br:superior.tribunal.justica;turma.3:acordao;resp:2010-11-23;1186789</dc:identifier>
          <autoridade>Superior Tribunal de Justiça</autoridade>
        </srw_dc:dc>
      </srw:recordData>
    </srw:record>
    <srw:record>
      <srw:recordData>
        <srw_dc:dc xmlns:srw_dc="info:srw/schema/1/dc-schema"
                   xmlns:dc="http://purl.org/dc/elements/1.1/">
          <urn>urn:lex:br:federal:lei:2002-01-10;10406</urn>
          <tipoDocumento>Lei</tipoDocumento>
          <facet-tipoDocumento>Legislação::Lei</facet-tipoDocumento>
          <dc:title>Lei nº 10.406, de 10 de Janeiro de 2002</dc:title>
          <dc:description>Institui o Código Civil. Texto integral da norma com
            mais de cinquenta caracteres de descrição.</dc:description>
          <dc:date>2002-01-10</dc:date>
          <dc:identifier>https://www.lexml.gov.br/urn/urn:lex:br:federal:lei:2002-01-10;10406</dc:identifier>
        </srw_dc:dc>
      </srw:recordData>
    </srw:record>
  </srw:records>
</srw:searchRetrieveResponse>
"""

# Espelho de acórdão do STJ Dados Abertos (CKAN) — campos reais do dataset
# (mesmos consumidos por app/services/ingestors/stj.py).
_STJ_PACKAGE = {
    "result": {"resources": [
        {"format": "JSON", "name": "20260501.json",
         "url": "https://dadosabertos.web.stj.jus.br/dataset/x/20260501.json"},
        {"format": "CSV", "name": "20260501.csv", "url": "https://x/csv"},
    ]}
}
_STJ_RECORDS = [
    {
        "numeroRegistro": "202001234567",
        "numeroProcesso": "1888888",
        "siglaClasse": "REsp",
        "descricaoClasse": "Recurso Especial",
        "ministroRelator": "FULANA DE TAL",
        "nomeOrgaoJulgador": "Terceira Turma",
        "dataDecisao": "2026-05-12",
        "ementa": "PLANO DE SAÚDE. NEGATIVA DE COBERTURA INDEVIDA. DANO MORAL "
                  "CONFIGURADO. Recurso provido para restabelecer a condenação.",
        "teseJuridica": "A negativa indevida de cobertura gera dano moral.",
    },
    {   # não casa com a consulta "dano moral"
        "numeroRegistro": "202009999999",
        "numeroProcesso": "1777777",
        "siglaClasse": "AREsp",
        "ministroRelator": "BELTRANO",
        "nomeOrgaoJulgador": "Quarta Turma",
        "dataDecisao": "2026-05-10",
        "ementa": "EXECUÇÃO FISCAL. PRESCRIÇÃO INTERCORRENTE RECONHECIDA NA "
                  "ORIGEM. Ausência de impulso útil do exequente por prazo legal.",
    },
    {   # sem ementa → descartado
        "numeroRegistro": "202000000001",
        "numeroProcesso": "1666666",
        "ementa": "",
    },
]


def _resp(text: str | None = None, json_data=None):
    class _R:
        pass
    r = _R()
    r.text = text or ""
    r.json = lambda: json_data
    return r


# ── LexML: normalização/parse ────────────────────────────────────────────────

async def test_lexml_normaliza_e_filtra_jurisprudencia(monkeypatch):
    chamadas: list[dict] = []

    async def fake_fetch(url, *, params=None, **kw):
        chamadas.append({"url": url, "params": params})
        return _resp(text=_LEXML_XML)

    monkeypatch.setattr(ji_lexml, "fetch", fake_fetch)
    julgados = await ji_lexml.buscar("dano moral", tribunal="STJ", limite=10)

    # Só o Acórdão passa (a Lei é Legislação::Lei — filtrada).
    assert len(julgados) == 1
    j = julgados[0]
    assert j.tribunal == "STJ"
    assert j.numero == "1186789"
    assert j.data == "2010-11-23"
    assert "DANO MORAL" in j.ementa and "REsp 1186789/SP" in j.ementa
    assert j.url_fonte.startswith("https://www.lexml.gov.br/urn/")
    assert j.chave_dedup() == "julgado:STJ:1186789"

    # Contrato da requisição SRU + refinamento por URN do tribunal.
    # Termos do usuário ENTRE ASPAS: consulta multi-palavra sem quoting vira
    # CQL inválida ("dano moral and urn any ..." → 0 resultados silencioso).
    p = chamadas[0]["params"]
    assert chamadas[0]["url"] == ji_lexml.SRU_URL
    assert p["operation"] == "searchRetrieve" and p["version"] == "1.1"
    assert '"dano moral"' in p["query"]
    assert 'urn any "superior.tribunal.justica"' in p["query"]


def test_lexml_cql_quota_termos_e_remove_aspas_internas():
    assert ji_lexml._cql("dano moral", None) == '"dano moral"'
    # Aspas do usuário são removidas antes do quoting (não quebram a CQL).
    assert ji_lexml._cql('dano "moral"', None) == '"dano  moral"'
    assert ji_lexml._cql("dano moral", "STJ") == (
        '"dano moral" and urn any "superior.tribunal.justica"')


async def test_lexml_resposta_com_diagnostics_degrada_para_vazio(monkeypatch):
    xml = ('<srw:searchRetrieveResponse xmlns:srw="http://www.loc.gov/zing/srw/">'
           "<srw:diagnostics>erro CQL</srw:diagnostics>"
           "</srw:searchRetrieveResponse>")

    async def fake_fetch(url, **kw):
        return _resp(text=xml)

    monkeypatch.setattr(ji_lexml, "fetch", fake_fetch)
    assert await ji_lexml.buscar("dano moral", limite=5) == []


async def test_lexml_paginacao_respeita_limite(monkeypatch):
    n_chamadas = 0

    async def fake_fetch(url, *, params=None, **kw):
        nonlocal n_chamadas
        n_chamadas += 1
        return _resp(text=_LEXML_XML)   # 2 registros (< página) → para na 1ª

    monkeypatch.setattr(ji_lexml, "fetch", fake_fetch)
    julgados = await ji_lexml.buscar("dano moral", limite=100)
    assert n_chamadas == 1              # página incompleta encerra a paginação
    assert len(julgados) == 1           # dedup interno + filtro de tipo


# ── STJ: filtro temático e normalização ──────────────────────────────────────

async def test_stj_filtra_por_termos_e_normaliza(monkeypatch):
    async def fake_fetch(url, *, params=None, **kw):
        if url.endswith("/package_show"):
            return _resp(json_data=_STJ_PACKAGE)
        return _resp(json_data=_STJ_RECORDS)

    monkeypatch.setattr(ji_stj, "fetch", fake_fetch)
    julgados = await ji_stj.buscar("dano moral cobertura", limite=10)

    assert len(julgados) == 1
    j = julgados[0]
    assert j.tribunal == "STJ"
    assert j.numero == "1888888"
    assert j.data == "2026-05-12"
    assert j.orgao_julgador == "Terceira Turma"
    assert j.relator == "FULANA DE TAL"
    assert "NEGATIVA DE COBERTURA" in j.ementa
    assert j.url_fonte == _STJ_PACKAGE["result"]["resources"][0]["url"]
    # Chave PRINCIPAL = a MESMA do ingestor agendado (keyspace compartilhado:
    # o job diário não reimporta o que o advogado importou hoje)...
    assert j.chave_dedup() == "stj:202001234567"
    # ...e a canônica por tribunal+número segue no dedup como chave extra.
    assert "julgado:STJ:1888888" in j.chaves_dedup()


async def test_stj_tribunal_diferente_retorna_vazio(monkeypatch):
    async def fake_fetch(url, **kw):   # nunca deve ser chamado
        raise AssertionError("não deveria consultar a rede")

    monkeypatch.setattr(ji_stj, "fetch", fake_fetch)
    assert await ji_stj.buscar("dano moral", tribunal="TJMG", limite=5) == []


async def test_stj_respeita_limite(monkeypatch):
    muitos = [dict(_STJ_RECORDS[0], numeroRegistro=f"2020{i:08d}",
                   numeroProcesso=str(1000000 + i)) for i in range(30)]

    async def fake_fetch(url, *, params=None, **kw):
        if url.endswith("/package_show"):
            return _resp(json_data=_STJ_PACKAGE)
        return _resp(json_data=muitos)

    monkeypatch.setattr(ji_stj, "fetch", fake_fetch)
    julgados = await ji_stj.buscar("dano moral", limite=7)
    assert len(julgados) == 7


# ── Ingestão: dedup por tribunal+número e resumo ─────────────────────────────

class _Res:
    def __init__(self, valor):
        self._v = valor

    def scalar_one_or_none(self):
        return self._v


class _FakeDB:
    """DB fake: controla o retorno do lookup de dedup; upsert é stub."""

    def __init__(self, existentes: set[str]):
        self.existentes = existentes
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, q):
        # extrai as chaves do IN() da query compilada (bindparam expanding
        # carrega a LISTA inteira como valor único)
        chaves: list[str] = []
        for v in q.compile().params.values():
            if isinstance(v, (list, tuple)):
                chaves.extend(x for x in v if isinstance(x, str))
            elif isinstance(v, str):
                chaves.append(v)
        achou = any(c in self.existentes for c in chaves)
        return _Res("doc-existente" if achou else None)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _julgado(numero="1234567", tribunal="STJ", **kw):
    return JulgadoNormalizado(
        tribunal=tribunal, numero=numero, data="2026-01-01",
        ementa="EMENTA de teste com tamanho suficiente para o pipeline de "
               "ingestão considerar o conteúdo relevante e citável.",
        url_fonte="https://dadosabertos.web.stj.jus.br/x.json", **kw,
    )


async def test_importar_deduplica_por_tribunal_numero(monkeypatch):
    gravados: list[dict] = []

    async def fake_upsert(db, **kw):
        gravados.append(kw)
        return "novo"

    monkeypatch.setattr(ji_ingest, "upsert_documento", fake_upsert)
    db = _FakeDB(existentes={"julgado:STJ:7777777"})

    julgados = [
        _julgado(numero="7777777"),                 # já existe → duplicado
        _julgado(numero="8888888"),                 # novo
        _julgado(numero="9999999",                  # novo com chave legada
                 chaves_extras=["stj:202001234567"]),
    ]
    resumo = await ji_ingest.importar_julgados(db, julgados, fonte_slug="t")
    assert resumo == {"importados": 2, "duplicados": 1, "erros": 0}
    assert len(gravados) == 2
    # Commit POR JULGADO gravado: item contado = item durável (o rollback de
    # um erro posterior nunca descarta importados já contados).
    assert db.commits == 2

    # Campos exigidos pelos DOIS consumidores (RAG + gate de citações):
    doc = gravados[0]
    assert doc["categoria"] == "jurisprudencia"
    assert doc["chave_origem"] == "julgado:STJ:8888888"
    assert doc["fonte"].startswith("https://")           # URL oficial
    assert doc["extra"]["fonte_validada"] is True
    assert doc["extra"]["rag_status"] == "disponivel"
    assert doc["extra"]["numero_processo"] == "8888888"
    assert doc["extra"]["data_julgamento"] == "2026-01-01"
    assert doc["confianca"] == "alta"


async def test_importar_dedup_por_chave_legada(monkeypatch):
    async def fake_upsert(db, **kw):
        raise AssertionError("não deveria gravar julgado já existente")

    monkeypatch.setattr(ji_ingest, "upsert_documento", fake_upsert)
    db = _FakeDB(existentes={"stj:202001234567"})
    resumo = await ji_ingest.importar_julgados(
        db, [_julgado(chaves_extras=["stj:202001234567"])], fonte_slug="t")
    assert resumo == {"importados": 0, "duplicados": 1, "erros": 0}


async def test_importar_erro_em_um_nao_aborta_os_demais(monkeypatch):
    vez = {"n": 0}

    async def fake_upsert(db, **kw):
        vez["n"] += 1
        if vez["n"] == 1:
            raise RuntimeError("falha simulada")
        return "novo"

    monkeypatch.setattr(ji_ingest, "upsert_documento", fake_upsert)
    db = _FakeDB(existentes=set())
    resumo = await ji_ingest.importar_julgados(
        db, [_julgado(numero="1"), _julgado(numero="2")], fonte_slug="t")
    assert resumo == {"importados": 1, "duplicados": 0, "erros": 1}
    # Rollback só do item com erro; o item bem-sucedido tem commit próprio.
    assert db.commits == 1 and db.rollbacks == 1


def test_numero_canonico_aplica_mascara_cnj():
    j = _julgado(numero="00008323520184013202")
    assert ji_ingest._numero_canonico(j) == "0000832-35.2018.4.01.3202"
    assert ji_ingest._numero_canonico(_julgado(numero="REsp 123")) == "REsp 123"


# ── Router: gate de papel (advogado+) e validação de fonte ───────────────────

from app.routers.juris_import import _GATE_ADVOGADO  # noqa: E402


async def _passa(role: UserRole) -> bool:
    checker = require_roles(_GATE_ADVOGADO)
    try:
        await checker(current_user=User(id="u1", role=role))
        return True
    except Exception as e:
        assert getattr(e, "status_code", None) == 403
        return False


@pytest.mark.parametrize("role", [
    UserRole.superadmin, UserRole.admin, UserRole.socio, UserRole.advogado,
])
async def test_gate_importacao_passa_advogado_e_acima(role):
    assert await _passa(role) is True


@pytest.mark.parametrize("role", [
    UserRole.advogado_auxiliar, UserRole.financeiro, UserRole.estagiario,
    UserRole.secretaria, UserRole.cliente_externo,
])
async def test_gate_importacao_barra_abaixo_de_advogado(role):
    assert await _passa(role) is False


async def test_post_rejeita_fonte_desconhecida():
    from fastapi import BackgroundTasks, HTTPException
    from app.routers.juris_import import ImportarJurisRequest, importar_jurisprudencia

    req = ImportarJurisRequest(fonte="inexistente", consulta="dano moral")
    with pytest.raises(HTTPException) as exc:
        await importar_jurisprudencia(
            req, BackgroundTasks(), cu=User(id="u1", role=UserRole.advogado))
    assert exc.value.status_code == 422


async def test_post_agenda_job_e_status_consultavel(monkeypatch):
    from fastapi import BackgroundTasks
    from app.routers import juris_import as router_mod
    from app.routers.juris_import import ImportarJurisRequest, importar_jurisprudencia

    agendados = []

    class _BT(BackgroundTasks):
        def add_task(self, fn, *a, **kw):
            agendados.append((fn, a))

    req = ImportarJurisRequest(fonte="lexml", consulta="dano moral",
                               tribunal="STJ", limite=10)
    out = await importar_jurisprudencia(
        req, _BT(), cu=User(id="u1", role=UserRole.socio))
    assert out["status"] == "executando" and out["fonte"] == "lexml"
    assert len(agendados) == 1
    assert agendados[0][0] is ji_ingest.executar_importacao

    # status consultável (registro em memória do job) — pelo DONO do job
    ji_ingest.registrar_job(out["job_id"], {"job_id": out["job_id"],
                                            "status": "concluido",
                                            "user_id": "u1",
                                            "resumo": {"importados": 3,
                                                       "duplicados": 1,
                                                       "erros": 0}})
    st = await router_mod.status_importacao(
        out["job_id"], cu=User(id="u1", role=UserRole.socio))
    assert st["status"] == "concluido"
    assert st["resumo"]["importados"] == 3


async def test_status_job_de_outro_usuario_responde_404():
    """Ownership: job alheio → o MESMO 404 de job inexistente (sem vazar id);
    superadmin/admin enxergam qualquer job."""
    from fastapi import HTTPException
    from app.routers import juris_import as router_mod

    ji_ingest.registrar_job("job-own", {
        "job_id": "job-own", "status": "concluido", "user_id": "dono",
        "resumo": {"importados": 1, "duplicados": 0, "erros": 0},
    })
    # Outro usuário (não-admin) → 404
    with pytest.raises(HTTPException) as exc:
        await router_mod.status_importacao(
            "job-own", cu=User(id="intruso", role=UserRole.advogado))
    assert exc.value.status_code == 404
    # Dono → 200
    st = await router_mod.status_importacao(
        "job-own", cu=User(id="dono", role=UserRole.advogado))
    assert st["status"] == "concluido"
    # Admin (não-dono) → 200
    st = await router_mod.status_importacao(
        "job-own", cu=User(id="adm", role=UserRole.admin))
    assert st["job_id"] == "job-own"


# ── Helpers de normalização ──────────────────────────────────────────────────

def test_normalizar_termos_sem_acentos():
    assert ji_base.normalizar_termos("Negativa de Cobertura Indevida") == [
        "negativa", "cobertura", "indevida"]
