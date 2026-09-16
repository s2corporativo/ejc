"""Jurimetria dos tribunais (Issue #1527): classificação por código TPU,
query ao DataJud, agregação e contrato do endpoint.

Sem banco e sem rede: a coleta é substituída por fixtures com a MESMA forma
dos documentos DataJud usados em ``test_saneamento_*``.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.security import get_current_user
from app.models.user import User, UserRole
from app.services.jurimetria_tribunais import agregacao, coleta
from app.services.jurimetria_tribunais import tpu_desfechos as tpu


# ── helpers ─────────────────────────────────────────────────────────────────
def _mov(codigo: int, data: str, nome: str = "") -> dict:
    return {"codigo": codigo, "nome": nome or f"mov {codigo}", "dataHora": data}


def _doc(numero: str, *, grau: str = "G1", orgao: str = "1ª Vara Cível da Comarca de Betim",
         ajuizamento: str = "2024-01-10T00:00:00Z", movimentos: list[dict] | None = None,
         assunto: tuple[int, str] = (9985, "Indenização por Dano Moral"),
         ibge: int | None = None) -> dict:
    oj = {"codigo": 1, "nome": orgao}
    if ibge is not None:
        oj["codigoMunicipioIBGE"] = ibge
    return {
        "numeroProcesso": numero,
        "tribunal": "TJMG",
        "grau": grau,
        "classe": {"codigo": 7, "nome": "Procedimento Comum Cível"},
        "assuntos": [{"codigo": assunto[0], "nome": assunto[1]}],
        "orgaoJulgador": oj,
        "dataAjuizamento": ajuizamento,
        "movimentos": movimentos or [],
    }


# ── classificação por código (fonte: SGT/CNJ, versão 26/05/2026) ────────────
@pytest.mark.parametrize("codigo,esperado", [
    (219, tpu.PROCEDENCIA),
    (221, tpu.PROCEDENCIA_PARCIAL),
    (220, tpu.IMPROCEDENCIA),
    (466, tpu.ACORDO),
    (456, tpu.SEM_MERITO),
    (463, tpu.SEM_MERITO),      # Desistência (filho de 456)
    (11403, tpu.PROCEDENCIA),   # JEC: procedência do pedido + improcedência do contraposto
    (11405, tpu.PROCEDENCIA_PARCIAL),
    (11409, tpu.IMPROCEDENCIA),
])
def test_desfecho_1grau_por_codigo(codigo, esperado):
    r = tpu.desfecho_1grau([_mov(codigo, "2025-03-01T10:00:00Z")])
    assert r is not None and r[0] == esperado


@pytest.mark.parametrize("codigo", [12451, 12453, 246, 60, 15250])
def test_codigos_fora_de_proposito_nao_viram_desfecho(codigo):
    # impugnação à execução, arquivamento, distribuição, socioeducativo
    assert tpu.desfecho_1grau([_mov(codigo, "2025-03-01T10:00:00Z")]) is None


def test_ultimo_movimento_por_data_prevalece():
    movs = [
        _mov(220, "2024-06-01T00:00:00Z"),   # sentença anulada depois
        _mov(219, "2025-02-01T00:00:00Z"),   # nova sentença: procedência
    ]
    r = tpu.desfecho_1grau(movs)
    assert r[0] == tpu.PROCEDENCIA and r[1].year == 2025


def test_movimento_sem_data_ainda_classifica():
    r = tpu.desfecho_1grau([{"codigo": 219, "nome": "Procedência"}])
    assert r == (tpu.PROCEDENCIA, None)


@pytest.mark.parametrize("codigo,esperado", [
    (237, tpu.PROVIMENTO), (238, tpu.PROVIMENTO_PARCIAL), (239, tpu.NAO_PROVIMENTO),
    (240, tpu.PROVIMENTO), (241, tpu.PROVIMENTO_PARCIAL), (242, tpu.NAO_PROVIMENTO),
    (972, tpu.PROVIMENTO), (901, tpu.NAO_PROVIMENTO),
])
def test_resultado_recursal_por_codigo(codigo, esperado):
    r = tpu.resultado_recursal([_mov(codigo, "2025-05-05T00:00:00Z")])
    assert r is not None and r[0] == esperado


def test_merito_de_1grau_nao_e_lido_como_recursal_e_vice_versa():
    assert tpu.resultado_recursal([_mov(219, "2025-01-01T00:00:00Z")]) is None
    assert tpu.desfecho_1grau([_mov(237, "2025-01-01T00:00:00Z")]) is None


# ── query ao DataJud ────────────────────────────────────────────────────────
def test_municipios_validos_normaliza_e_cai_no_padrao():
    assert coleta.municipios_validos(["Betim", " contagem "]) == ["betim", "contagem"]
    assert coleta.municipios_validos(["marte"]) == list(coleta.MUNICIPIOS_PADRAO)
    assert coleta.municipios_validos(None) == list(coleta.MUNICIPIOS_PADRAO)


def test_montar_query_filtra_por_orgao_e_recortes():
    q = coleta.montar_query(["betim"], classe=7, assunto=9985, desde="2024-01-01", ate="2024-12-31")
    b = q["query"]["bool"]
    assert {"match_phrase": {"orgaoJulgador.nome": "Betim"}} in b["should"]
    assert {"term": {"orgaoJulgador.codigoMunicipioIBGE": 3106705}} in b["should"]
    assert b["minimum_should_match"] == 1
    assert {"term": {"classe.codigo": 7}} in b["filter"]
    assert {"term": {"assuntos.codigo": 9985}} in b["filter"]
    assert {"range": {"dataAjuizamento": {"gte": "2024-01-01", "lte": "2024-12-31"}}} in b["filter"]


def test_montar_query_sem_grau_traz_1o_e_2o_grau():
    q = coleta.montar_query(["contagem"])
    assert not any("grau" in f.get("term", {}) for f in q["query"]["bool"]["filter"])


# ── agregação ───────────────────────────────────────────────────────────────
def _amostra() -> list[dict]:
    return [
        _doc("0000001-11.2024.8.13.0027", movimentos=[_mov(219, "2025-01-10T00:00:00Z")]),
        _doc("0000002-11.2024.8.13.0027", movimentos=[_mov(221, "2025-02-10T00:00:00Z")]),
        _doc("0000003-11.2024.8.13.0027", movimentos=[_mov(220, "2025-03-10T00:00:00Z")]),
        _doc("0000004-11.2024.8.13.0027", movimentos=[_mov(466, "2024-08-10T00:00:00Z")]),
        _doc("0000005-11.2024.8.13.0027", movimentos=[_mov(463, "2024-05-10T00:00:00Z")]),
        _doc("0000006-11.2024.8.13.0027", movimentos=[_mov(60, "2024-01-11T00:00:00Z")]),  # sem desfecho
        _doc("0000007-11.2024.8.13.0079", orgao="2ª Vara Cível de Contagem",
             assunto=(10433, "Cobrança"), movimentos=[_mov(219, "2025-04-10T00:00:00Z")]),
        # 2º grau do processo 1 (reformado) e do 3 (mantido)
        _doc("0000001-11.2024.8.13.0027", grau="G2", orgao="10ª Câmara Cível",
             movimentos=[_mov(238, "2025-09-01T00:00:00Z")]),
        _doc("0000003-11.2024.8.13.0027", grau="G2", orgao="10ª Câmara Cível",
             movimentos=[_mov(239, "2025-09-02T00:00:00Z")]),
    ]


def test_agregar_conta_taxas_e_tempo_por_municipio_e_assunto():
    r = agregacao.agregar(_amostra(), ["betim", "contagem", "belo_horizonte"])
    assert r["n_processos_1grau"] == 7
    t = r["total"]
    assert t["n"] == 7 and t["n_com_desfecho"] == 6
    assert (t[tpu.PROCEDENCIA], t[tpu.PROCEDENCIA_PARCIAL], t[tpu.IMPROCEDENCIA]) == (2, 1, 1)
    assert t[tpu.ACORDO] == 1 and t[tpu.SEM_MERITO] == 1
    # (2 + 1) / (2 + 1 + 1): acordo e extinção NÃO entram no denominador
    assert t["decididos_merito"] == 4 and t["taxa_procedencia"] == 0.75
    assert t["taxa_acordo"] == round(1 / 6, 4)
    assert t["amostra_pequena"] is True  # 4 < MIN_AMOSTRA
    # tempo até sentença: só mérito, com data (4 processos)
    assert t["tempo_sentenca"]["n"] == 4
    assert t["tempo_sentenca"]["mediana_dias"] > 0

    por_mun = {m["municipio"]: m for m in r["por_municipio"]}
    assert por_mun["betim"]["n"] == 6 and por_mun["contagem"]["n"] == 1
    assert por_mun["contagem"]["taxa_procedencia"] == 1.0

    por_ass = {a["assunto"]: a for a in r["por_assunto"]}
    assert por_ass["Cobrança"]["n"] == 1 and por_ass["Indenização por Dano Moral"]["n"] == 6

    ref = r["reforma_2grau"]
    assert ref["n_com_recurso_julgado"] == 2
    assert ref[tpu.PROVIMENTO_PARCIAL] == 1 and ref[tpu.NAO_PROVIMENTO] == 1
    assert ref["taxa_reforma"] == 0.5


def test_agregar_detecta_municipio_por_codigo_ibge_quando_nome_nao_ajuda():
    d = _doc("0000009-11.2024.8.13.0024", orgao="Vara Única", ibge=3106200,
             movimentos=[_mov(219, "2025-01-01T00:00:00Z")])
    r = agregacao.agregar([d], ["belo_horizonte"])
    assert r["por_municipio"][0]["municipio"] == "belo_horizonte"


def test_agregar_nao_expoe_numero_de_processo_nem_partes():
    r = agregacao.agregar(_amostra(), ["betim"])
    texto = repr(r)
    assert "0000001-11.2024" not in texto
    assert "numeroProcesso" not in texto


# ── endpoint: RBAC, flag e tradução de erro ──────────────────────────────────
def _client(role: UserRole) -> TestClient:
    # Mesmo desenho de test_rbac_equipe_juridica_694: app mínimo só com o
    # router (sem AuthMiddleware), papel injetado por dependency_overrides.
    from fastapi import FastAPI

    from app.core.database import get_db
    from app.routers import jurimetria as jurimetria_router

    app = FastAPI()
    app.include_router(jurimetria_router.router)
    app.dependency_overrides[get_current_user] = lambda: User(
        id="u-1", role=role, full_name="Fulano de Teste"
    )
    app.dependency_overrides[get_db] = lambda: None
    return TestClient(app)


@pytest.fixture(autouse=True)
def _limpa_cache():
    coleta.limpar_cache()
    yield
    coleta.limpar_cache()


def test_status_sem_flag_diz_desabilitado_sem_io(monkeypatch):
    monkeypatch.delenv("JURIMETRIA_TRIBUNAIS_ENABLED", raising=False)
    r = _client(UserRole.advogado).get("/jurimetria/tribunais/status")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["habilitado"] is False
    assert corpo["tpu_versao"] == "26/05/2026"
    assert [m["chave"] for m in corpo["municipios"]] == ["belo_horizonte", "contagem", "betim"]


def test_desfechos_com_flag_desligada_e_503_controlado(monkeypatch):
    monkeypatch.delenv("JURIMETRIA_TRIBUNAIS_ENABLED", raising=False)
    r = _client(UserRole.advogado).get("/jurimetria/tribunais/desfechos")
    assert r.status_code == 503
    assert "JURIMETRIA_TRIBUNAIS_ENABLED" in r.json()["detail"]


def test_desfechos_financeiro_nao_acessa(monkeypatch):
    monkeypatch.setenv("JURIMETRIA_TRIBUNAIS_ENABLED", "true")
    r = _client(UserRole.financeiro).get("/jurimetria/tribunais/desfechos")
    assert r.status_code == 403


def test_desfechos_agrega_a_coleta(monkeypatch):
    monkeypatch.setenv("JURIMETRIA_TRIBUNAIS_ENABLED", "true")

    async def _coleta_fake(municipios, **kw):
        return _amostra(), {"cache": False, "coletado_em": "2026-09-05T12:00:00Z",
                            "maximo": 2000, "n_documentos": 9, "truncado": False}

    from app.services.jurimetria_tribunais import servico

    monkeypatch.setattr(servico, "coletar", _coleta_fake)
    r = _client(UserRole.advogado).get(
        "/jurimetria/tribunais/desfechos?municipios=betim,contagem&assunto=9985"
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["fonte"].startswith("DataJud/CNJ")
    assert corpo["escopo"]["municipios"] == ["Betim", "Contagem"]
    assert corpo["escopo"]["assunto"] == 9985
    assert corpo["total"]["taxa_procedencia"] == 0.75
    assert corpo["coleta"]["n_documentos"] == 9
    assert corpo["limitacoes"]


def test_desfechos_traduz_datajud_desligado_em_503(monkeypatch):
    monkeypatch.setenv("JURIMETRIA_TRIBUNAIS_ENABLED", "true")
    from app.services import datajud_service as djs
    from app.services.jurimetria_tribunais import servico

    async def _coleta_fake(municipios, **kw):
        raise djs.DataJudDesabilitadoError("Integração DataJud desativada (DATAJUD_ENABLED)")

    monkeypatch.setattr(servico, "coletar", _coleta_fake)
    r = _client(UserRole.advogado).get("/jurimetria/tribunais/desfechos")
    assert r.status_code == 503
    assert "DATAJUD_ENABLED" in r.json()["detail"]


def test_desfechos_traduz_falha_de_rede_em_502_sem_stack(monkeypatch):
    monkeypatch.setenv("JURIMETRIA_TRIBUNAIS_ENABLED", "true")
    import httpx

    from app.services.jurimetria_tribunais import servico

    async def _coleta_fake(municipios, **kw):
        raise httpx.ConnectError("boom interno com detalhes")

    monkeypatch.setattr(servico, "coletar", _coleta_fake)
    r = _client(UserRole.advogado).get("/jurimetria/tribunais/desfechos")
    assert r.status_code == 502
    assert "boom" not in r.text


def test_data_invalida_e_422():
    r = _client(UserRole.advogado).get("/jurimetria/tribunais/desfechos?desde=05/09/2026")
    assert r.status_code == 422
