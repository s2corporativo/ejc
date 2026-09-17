# ── tests/test_radar_legislativo.py ──────────────────────────────────────────
# Radar Legislativo (Câmara + Senado + ALMG) — Bloco 2 das APIs públicas.
# Tudo SEM rede (indireção _get_json / _BUSCADORES mockada) e SEM Postgres
# (dedup exercitado em SQLite in-memory — DDL da tabela é portátil).
#
# Cobertura:
#   • normalização das 3 fontes (parsers puros, shapes reais e degradados);
#   • dedup persistente: segunda rodada não re-alerta (radar_legislativo_visto);
#   • ALMG timeout/fora do ar → job SEGUE com Câmara e Senado (degradação);
#   • exceção de uma fonte inteira → resumo marca "erro" e as demais coletam;
#   • termos por ramo: tabela `areas` ativa, fallback AREAS_DIREITO e
#     override/adição via RADAR_LEGISLATIVO_TERMOS (JSON, tolerante a lixo).
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.services import radar_legislativo as svc


# ── Fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture
async def db():
    """Sessão SQLite in-memory — suficiente para a tabela de dedup (DDL
    portátil, ON CONFLICT DO NOTHING suportado)."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def alertas_criados(monkeypatch):
    """Substitui _criar_alerta (que grava no modelo do Radar Regulatório —
    exige Postgres) por um coletor em memória."""
    criados: list[tuple[str, str, str]] = []

    async def _fake(db, item, termo):
        criados.append((item["fonte"], item["id_externo"], termo))

    monkeypatch.setattr(svc, "_criar_alerta", _fake)
    return criados


def _prop_camara(pid=101, ementa="Altera a CLT"):
    return {"id": pid, "siglaTipo": "PL", "numero": 123, "ano": 2026,
            "ementa": ementa}


# ── Normalização: Câmara ─────────────────────────────────────────────────────
def test_parse_camara_normaliza_shape_unico():
    itens = svc._parse_camara({"dados": [_prop_camara(), {"sem_id": True}]})
    assert len(itens) == 1                                  # item sem id é descartado
    item = itens[0]
    assert item["fonte"] == "camara"
    assert item["id_externo"] == "101"
    assert (item["tipo"], item["numero"], item["ano"]) == ("PL", 123, 2026)
    assert item["ementa"] == "Altera a CLT"
    assert "idProposicao=101" in item["url"]
    # a lista da Câmara não traz data/tramitação — completadas via detalhe
    assert item["data_apresentacao"] is None and item["ultima_tramitacao"] is None
    # chaves do shape único completas (contrato da tabela/endpoint)
    assert set(item) == {"fonte", "id_externo", "tipo", "numero", "ano",
                         "ementa", "url", "data_apresentacao", "ultima_tramitacao"}


def test_parse_camara_payload_degradado():
    assert svc._parse_camara(None) == []
    assert svc._parse_camara({"dados": None}) == []
    assert svc._parse_camara([1, 2]) == []


def test_parse_camara_detalhe():
    data_apr, tram = svc._parse_camara_detalhe({"dados": {
        "dataApresentacao": "2026-05-02T14:00",
        "statusProposicao": {"dataHora": "2026-07-01T10:00",
                             "descricaoSituacao": "Pronta para Pauta",
                             "descricaoTramitacao": "Parecer do Relator"},
    }})
    assert data_apr == "2026-05-02"
    assert "Pronta para Pauta" in tram and "(2026-07-01)" in tram
    assert svc._parse_camara_detalhe({}) == (None, None)


# ── Normalização: Senado ─────────────────────────────────────────────────────
#
# FIXTURE REAL, recortada da resposta ao vivo de
# `legis.senado.leg.br/dadosabertos/materia/pesquisa/lista.json?ano=2026&
# palavraChave=consumidor` em 04/09/2026 (85 matérias devolvidas).
#
# A fixture anterior era INVENTADA: usava `IdentificacaoMateria.CodigoMateria`,
# `DadosBasicosMateria.EmentaMateria` — um envelope que a API não devolve. Com
# ela, a suíte ficava verde enquanto o parser descartava 100% das matérias
# reais (85 entravam, 0 saíam) e o radar reportava `senado: 0` como sucesso,
# diariamente. Teste que fabrica contrato não protege nada: ele esconde.
#
# Se a API mudar de shape, ESTE teste tem de quebrar — é essa a função dele.
_SENADO_PAYLOAD = {"PesquisaBasicaMateria": {"Materias": {"Materia": [
    {
        "Codigo": "172373",
        "Sigla": "MPV",
        "Numero": "01334",
        "Ano": "2026",
        "Ementa": (
            "Altera a Lei nº 11.738, de 16 de julho de 2008, para dispor sobre "
            "o piso salarial profissional nacional para os profissionais do "
            "magistério público da educação básica."
        ),
        "Data": "2026-01-22",
        "DescricaoIdentificacao": "MPV 1334/2026",
        "UrlDetalheMateria": "http://legis.senado.leg.br/dadosabertos/materia/172373",
    },
]}}}


def test_parse_senado_le_o_shape_real_da_api():
    """Regressão do defeito medido: o shape real é PLANO, sem envelope."""
    itens = svc._parse_senado(_SENADO_PAYLOAD)
    assert len(itens) == 1, "o shape real da API não pode ser descartado"
    item = itens[0]
    assert item["fonte"] == "senado"
    assert item["id_externo"] == "172373"
    assert (item["tipo"], item["numero"], item["ano"]) == ("MPV", 1334, 2026)
    assert "piso salarial" in item["ementa"]
    assert item["data_apresentacao"] == "2026-01-22"


def test_parse_senado_ainda_aceita_o_shape_antigo_com_envelope():
    """Tolerância preservada: se a API voltar ao envelope, não quebra."""
    payload = {"PesquisaBasicaMateria": {"Materias": {"Materia": [{
        "IdentificacaoMateria": {"CodigoMateria": "555",
                                 "SiglaSubtipoMateria": "PLS",
                                 "NumeroMateria": "42", "AnoMateria": "2026"},
        "DadosBasicosMateria": {"EmentaMateria": "Reforma tributária",
                                "DataApresentacao": "2026-03-10"},
    }]}}}
    itens = svc._parse_senado(payload)
    assert len(itens) == 1
    assert itens[0]["id_externo"] == "555"
    assert itens[0]["ementa"] == "Reforma tributária"


def test_parse_senado_um_resultado_vira_dict():
    """A API do Senado devolve dict (não lista) quando há 1 resultado."""
    payload = {"PesquisaBasicaMateria": {"Materias": {"Materia": {
        "IdentificacaoMateria": {"CodigoMateria": 9, "SiglaTipoMateria": "PEC",
                                 "NumeroMateria": 1, "AnoMateria": 2026},
        "EmentaMateria": "Emenda X",
    }}}}
    itens = svc._parse_senado(payload)
    assert len(itens) == 1 and itens[0]["tipo"] == "PEC"


def test_parse_senado_payload_degradado():
    assert svc._parse_senado(None) == []
    assert svc._parse_senado({}) == []
    assert svc._parse_senado({"PesquisaBasicaMateria": {"Materias": None}}) == []


# ── Normalização: ALMG (parser tolerante — swagger inacessível na sondagem) ──
def test_parse_almg_shape_resultado_listaitem():
    payload = {"resultado": {"listaItem": [{
        "id": 777, "siglaTipoProjeto": "PL", "numero": 88, "ano": 2026,
        "ementa": "Licenciamento ambiental em MG",
        "dataPublicacao": "2026-06-30T00:00",
    }]}}
    itens = svc._parse_almg(payload)
    assert len(itens) == 1
    item = itens[0]
    assert item["fonte"] == "almg" and item["id_externo"] == "777"
    assert item["data_apresentacao"] == "2026-06-30"
    assert "almg.gov.br" in item["url"]


def test_parse_almg_shape_lista_crua_e_sem_id():
    itens = svc._parse_almg([
        {"tipo": "PL", "numero": 5, "ano": 2026, "assunto": "ICMS estadual"},
        {"ementa": "sem identificação"},          # sem id nem numero/ano → fora
    ])
    assert len(itens) == 1
    assert itens[0]["id_externo"] == "PL-5-2026"  # chave sintética estável
    assert itens[0]["ementa"] == "ICMS estadual"


def test_parse_almg_payload_degradado():
    assert svc._parse_almg(None) == []
    assert svc._parse_almg("html de erro") == []
    assert svc._parse_almg({"resultado": None}) == []


# ── Dedup persistente (segunda rodada não re-alerta) ─────────────────────────
async def test_dedup_segunda_rodada_nao_realerta(db, alertas_criados, monkeypatch):
    item = svc._item("camara", 101, "PL", 123, 2026, "Altera a CLT",
                     "https://x", data_apresentacao="2026-05-02")

    async def _buscar(termo):
        return [item]

    monkeypatch.setitem(svc._BUSCADORES, "camara", _buscar)
    termos = {"trabalhista": ["CLT"]}

    n1 = await svc.processar_fonte(db, "camara", termos, sleep_s=0)
    n2 = await svc.processar_fonte(db, "camara", termos, sleep_s=0)

    assert n1 == 1 and n2 == 0
    assert alertas_criados == [("camara", "101", "CLT")]   # alerta ÚNICO

    historico = await svc.historico_visto(db)
    assert len(historico) == 1
    assert historico[0]["id_externo"] == "101"
    assert historico[0]["termo"] == "CLT"


async def test_dedup_mesmo_id_em_fontes_diferentes_nao_colide(db, alertas_criados,
                                                              monkeypatch):
    async def _camara(termo):
        return [svc._item("camara", 1, "PL", 1, 2026, "A", "u",
                          data_apresentacao="2026-01-01")]

    async def _senado(termo):
        return [svc._item("senado", 1, "PLS", 1, 2026, "B", "u")]

    monkeypatch.setitem(svc._BUSCADORES, "camara", _camara)
    monkeypatch.setitem(svc._BUSCADORES, "senado", _senado)
    termos = {"civil": ["código civil"]}
    assert await svc.processar_fonte(db, "camara", termos, sleep_s=0) == 1
    assert await svc.processar_fonte(db, "senado", termos, sleep_s=0) == 1


# ── Degradação: ALMG fora do ar não derruba o job ────────────────────────────
async def test_almg_timeout_job_segue_com_as_outras_fontes(db, alertas_criados,
                                                           monkeypatch):
    async def _fake_get_json(fonte, url, params=None, **kw):
        if fonte == "almg":
            return None                       # retries esgotados (timeout 45s)
        if url.endswith("/proposicoes"):      # lista da Câmara
            return {"dados": [_prop_camara()]}
        if "/proposicoes/" in url:            # detalhe/tramitações (Câmara)
            return None                       # detalhe indisponível — tolerado
        if "senado" in url:
            return _SENADO_PAYLOAD
        return None

    async def _termos(db_):
        return {"tributario": ["reforma tributária"]}

    monkeypatch.setattr(svc, "_get_json", _fake_get_json)
    monkeypatch.setattr(svc, "termos_monitorados", _termos)

    resumo = await svc.executar_radar(db, sleep_s=0)

    assert resumo["camara"] == 1 and resumo["senado"] == 1
    assert resumo["almg"] == 0                          # degradou, não explodiu
    assert {a[0] for a in alertas_criados} == {"camara", "senado"}


async def test_excecao_de_fonte_marca_erro_e_nao_derruba(db, alertas_criados,
                                                         monkeypatch):
    original = svc.processar_fonte

    async def _explode_almg(db_, fonte, termos, **kw):
        if fonte == "almg":
            raise RuntimeError("ALMG caiu no meio da fonte")
        return await original(db_, fonte, termos, **kw)

    async def _buscar_ok(termo):
        return [svc._item("senado", 300, "PLS", 3, 2026, "OK", "u")]

    async def _buscar_vazio(termo):
        return []

    async def _termos(db_):
        return {"consumidor": ["código de defesa do consumidor"]}

    monkeypatch.setattr(svc, "processar_fonte", _explode_almg)
    monkeypatch.setattr(svc, "termos_monitorados", _termos)
    monkeypatch.setitem(svc._BUSCADORES, "camara", _buscar_vazio)
    monkeypatch.setitem(svc._BUSCADORES, "senado", _buscar_ok)

    resumo = await svc.executar_radar(db, sleep_s=0)

    assert resumo["almg"] == "erro"
    assert resumo["senado"] == 1                       # coleta das demais preservada


# ── Busca ao vivo (endpoint): fonte com falha é reportada, não propaga ───────
async def test_buscar_ao_vivo_tolerante(monkeypatch):
    async def _ok(termo):
        return [svc._item("camara", 1, "PL", 1, 2026, "A", "u")]

    async def _falha(termo):
        raise TimeoutError("almg 45s")

    monkeypatch.setitem(svc._BUSCADORES, "camara", _ok)
    monkeypatch.setitem(svc._BUSCADORES, "almg", _falha)

    itens, falhas = await svc.buscar_ao_vivo("teste", ("camara", "almg"))
    assert len(itens) == 1 and falhas == ["almg"]


# ── Termos por ramo ───────────────────────────────────────────────────────────
class _FakeResult:
    def __init__(self, vals):
        self._vals = vals

    def scalars(self):
        return self

    def all(self):
        return self._vals


class _FakeDB:
    """Simula a consulta à tabela `areas` (ou a falta dela)."""
    def __init__(self, slugs=None, erro=False):
        self.slugs, self.erro = slugs or [], erro

    async def execute(self, *a, **k):
        if self.erro:
            raise RuntimeError("relation areas does not exist")
        return _FakeResult(self.slugs)


async def test_termos_derivados_dos_ramos_ativos(monkeypatch):
    monkeypatch.setattr(get_settings(), "RADAR_LEGISLATIVO_TERMOS", "")
    termos = await svc.termos_monitorados(_FakeDB(["tributario", "consumidor"]))
    assert set(termos) == {"tributario", "consumidor"}   # só os ramos ATIVOS
    assert "reforma tributária" in termos["tributario"]
    assert termos["consumidor"] == ["código de defesa do consumidor"]


async def test_termos_fallback_areas_direito_sem_tabela(monkeypatch):
    monkeypatch.setattr(get_settings(), "RADAR_LEGISLATIVO_TERMOS", "")
    termos = await svc.termos_monitorados(_FakeDB(erro=True))
    from app.services.peca_service import AREAS_DIREITO
    assert set(termos).issubset(set(AREAS_DIREITO))
    assert "trabalhista" in termos and "digital_lgpd" in termos


async def test_termos_customizados_override_e_aditivo(monkeypatch):
    monkeypatch.setattr(
        get_settings(), "RADAR_LEGISLATIVO_TERMOS",
        '{"tributario": ["CBS IBS"], "agrario": "regularização fundiária"}',
    )
    termos = await svc.termos_monitorados(_FakeDB(["tributario", "ambiental"]))
    assert termos["tributario"] == ["CBS IBS"]           # override do default
    assert termos["agrario"] == ["regularização fundiária"]  # ramo extra aditivo
    assert termos["ambiental"] == ["licenciamento ambiental"]  # default intacto


async def test_termos_customizados_json_invalido_ignorado(monkeypatch):
    monkeypatch.setattr(get_settings(), "RADAR_LEGISLATIVO_TERMOS", "{{{lixo")
    termos = await svc.termos_monitorados(_FakeDB(["civil"]))
    assert termos == {"civil": ["código civil"]}          # nunca derruba o job


# ── heartbeat por resultado ──────────────────────────────────────────────────

async def test_fonte_com_erro_marca_a_execucao_como_erro(monkeypatch):
    """Sem isto, uma perna morta fica invisível: o job termina sem exceção,
    loga 'concluído' e nenhum painel percebe. Foi o que manteve o Senado
    entregando zero por tempo indeterminado."""
    pontos: list[tuple] = []

    async def _espiao(status, detalhe=None):
        pontos.append((status, detalhe))

    async def _resumo_com_erro(db, **kwargs):
        return {"camara": 3, "senado": "erro", "almg": 0}

    monkeypatch.setattr(svc, "_bater_ponto_radar", _espiao)
    monkeypatch.setattr(svc, "executar_radar", _resumo_com_erro)
    monkeypatch.setattr(svc.get_settings(), "RADAR_LEGISLATIVO_ENABLED", True,
                        raising=False)

    await svc.job_radar_legislativo()

    assert pontos and pontos[0][0] == "erro"
    assert "senado" in pontos[0][1]


async def test_execucao_sadia_bate_ponto_ok_com_as_contagens(monkeypatch):
    pontos: list[tuple] = []

    async def _espiao(status, detalhe=None):
        pontos.append((status, detalhe))

    async def _resumo_ok(db, **kwargs):
        return {"camara": 3, "senado": 5, "almg": 0}

    monkeypatch.setattr(svc, "_bater_ponto_radar", _espiao)
    monkeypatch.setattr(svc, "executar_radar", _resumo_ok)
    monkeypatch.setattr(svc.get_settings(), "RADAR_LEGISLATIVO_ENABLED", True,
                        raising=False)

    await svc.job_radar_legislativo()

    assert pontos and pontos[0][0] == "ok"
    # O detalhe carrega as contagens: "0 em todas" fica legível no diagnóstico.
    assert '"senado": 5' in pontos[0][1]
