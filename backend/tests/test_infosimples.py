"""Conector Infosimples (consultas pagas) — sem rede, sem banco.

Cobre: gates de flag/token (503), teto diário de custo (contador persistido),
cache do mesmo dia SEM segunda chamada HTTP, erro 6xx tipado (que ainda conta
no teto), token que NUNCA aparece em logs/erros/audit, mascaramento de PII,
normalização TJMG/Receita, merge TJMG deduplicado pela MESMA chave [dj:hash16]
do DataJud e endpoints (validação CNJ/CPF/CNPJ, montagem em main).
Fakes no padrão test_andamentos_datajud/test_sociedades_cliente.
"""
from __future__ import annotations

import json
import logging

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.config import get_settings
from app.models.case import Case, CaseMovimento
from app.models.user import User, UserRole
from app.services import infosimples_service
from app.services.datajud_service import _hash_mov, upsert_movimentos_no_caso
from app.services.infosimples_service import (
    InfosimplesConsultaError,
    IntegracaoDesligadaError,
    LimiteDiarioAtingidoError,
    consultar,
    hash_parametros,
    mascarar_parametros,
    normalizar_car_demonstrativo,
    normalizar_car_imovel,
    normalizar_processo_tjmg,
    normalizar_receita_cnpj,
    normalizar_receita_cpf,
)

TOKEN_TESTE = "tok-super-secreto-nao-vazar"


@pytest.fixture()
def infosimples_ligado(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "INFOSIMPLES_ENABLED", True)
    monkeypatch.setattr(s, "INFOSIMPLES_TOKEN", TOKEN_TESTE)
    monkeypatch.setattr(s, "INFOSIMPLES_MAX_CONSULTAS_DIA", 50)
    return s


# ── Fakes (sem banco) — dispatch pelo SQL, robusto à ordem das queries ─────────

class _Res:
    def __init__(self, val):
        self._val = val

    def scalar(self):
        return self._val

    def scalar_one_or_none(self):
        return self._val

    def scalars(self):
        return self

    def all(self):
        return self._val


class _FakeDB:
    """Fake do AsyncSession p/ o conector: responde por conteúdo do SQL."""

    def __init__(self, cache: dict | None = None, uso_dia: int = 0,
                 case: Case | None = None, descricoes: list[str] | None = None):
        self.cache = cache
        self.uso_dia = uso_dia
        self.case = case
        self.descricoes = descricoes or []
        self.inserts: list[dict] = []
        self.added: list = []
        self.commits = 0

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "SELECT resultado FROM infosimples_uso" in sql:
            return _Res(json.dumps(self.cache) if self.cache is not None else None)
        if "SELECT COUNT(*) FROM infosimples_uso" in sql:
            return _Res(self.uso_dia)
        if "INSERT INTO infosimples_uso" in sql:
            self.inserts.append(dict(params or {}))
            self.uso_dia += 1
            return _Res(None)
        if "FROM cases" in sql:
            return _Res(self.case)
        if "case_movimentos" in sql:
            return _Res(list(self.descricoes))
        return _Res(None)  # DDL / DELETE / demais

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


def _socio() -> User:
    return User(id="u1", role=UserRole.socio)


def _caso(numero: str | None) -> Case:
    return Case(id="caso1", titulo="Caso TJMG", client_id="cli1",
                numero_processo=numero, deleted_at=None,
                advogado_responsavel_id="u1", advogado_auxiliar_id=None)


def _fake_post(resposta: dict, chamadas: list | None = None):
    async def _post(url, dados, timeout_s):
        if chamadas is not None:
            chamadas.append({"url": url, "dados": dados, "timeout": timeout_s})
        return resposta

    return _post


RESPOSTA_OK = {
    "code": 200,
    "code_message": "A requisição foi processada com sucesso.",
    "data": [{"situacao": "Ativo"}],
    "header": {"price": "0.24"},
    "errors": [],
    "site_receipts": ["https://storage.infosimples.example/comprovante.html"],
}


# ── Rotas montadas ─────────────────────────────────────────────────────────────

def test_rotas_montadas_em_main():
    from app.main import app
    paths = {getattr(r, "path", "") for r in app.routes}
    assert any(p.endswith("/infosimples/tjmg/processo") for p in paths)
    assert any(p.endswith("/infosimples/receita/cpf") for p in paths)
    assert any(p.endswith("/infosimples/receita/cnpj") for p in paths)
    assert any(p.endswith("/infosimples/status") for p in paths)


# ── Gates de flag/token ────────────────────────────────────────────────────────

async def test_consultar_flag_desligada(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "INFOSIMPLES_ENABLED", False)
    with pytest.raises(IntegracaoDesligadaError):
        await consultar(_FakeDB(), "tribunal/tjmg/processo", {"numero_processo": "1"})


async def test_consultar_sem_token(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "INFOSIMPLES_ENABLED", True)
    monkeypatch.setattr(s, "INFOSIMPLES_TOKEN", "")
    with pytest.raises(IntegracaoDesligadaError):
        await consultar(_FakeDB(), "tribunal/tjmg/processo", {"numero_processo": "1"})


# ── Sucesso: chamada, registro de custo e audit ────────────────────────────────

async def test_consultar_sucesso_registra_custo_e_audita(infosimples_ligado, monkeypatch):
    chamadas: list = []
    monkeypatch.setattr(infosimples_service, "_post_form", _fake_post(RESPOSTA_OK, chamadas))
    db = _FakeDB()

    r = await consultar(db, "tribunal/tjmg/processo",
                        {"numero_processo": "00000010220208130000"},
                        user_id="u1", user_role="socio")

    assert r["code"] == 200 and r["cache"] is False
    assert r["data"] == [{"situacao": "Ativo"}]
    assert r["site_receipts"] == RESPOSTA_OK["site_receipts"]
    # POST form-urlencoded no caminho certo, com token e timeout no corpo.
    assert chamadas[0]["url"].endswith("/api/v2/consultas/tribunal/tjmg/processo")
    assert chamadas[0]["dados"]["token"] == TOKEN_TESTE
    assert chamadas[0]["dados"]["timeout"] == get_settings().INFOSIMPLES_TIMEOUT
    # Custo persistido (1 linha do dia, com resultado p/ cache) + audit + commit.
    assert len(db.inserts) == 1 and db.inserts[0]["res"] is not None
    audits = [a for a in db.added if a.__class__.__name__ == "AuditLog"]
    assert len(audits) == 1 and audits[0].acao == "CONSULTA_PAGA"
    assert db.commits == 1


# ── Erro 6xx: exceção tipada, conta no teto, sem token na mensagem ─────────────

async def test_consultar_erro_6xx(infosimples_ligado, monkeypatch, caplog):
    resposta = {"code": 612, "code_message": "Não foram encontrados resultados.",
                "data": [], "errors": ["sem resultados"], "site_receipts": []}
    monkeypatch.setattr(infosimples_service, "_post_form", _fake_post(resposta))
    db = _FakeDB()

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(InfosimplesConsultaError) as exc:
            await consultar(db, "receita-federal/cpf",
                            {"cpf": "52998224725", "birthdate": "01/01/1980"})

    assert exc.value.code == 612
    assert "612" in str(exc.value)
    # Consulta EXECUTADA (cobrada) conta no teto mesmo com erro; sem cache.
    assert len(db.inserts) == 1 and db.inserts[0]["res"] is None
    assert db.inserts[0]["code"] == 612
    # Token jamais em exceção ou log.
    assert TOKEN_TESTE not in str(exc.value)
    assert TOKEN_TESTE not in caplog.text


# ── Teto diário de custo ───────────────────────────────────────────────────────

async def test_consultar_teto_diario_atingido(infosimples_ligado, monkeypatch):
    async def _nao_chamar(*a, **k):
        raise AssertionError("não pode chamar a API paga com o teto atingido")

    monkeypatch.setattr(infosimples_service, "_post_form", _nao_chamar)
    monkeypatch.setattr(get_settings(), "INFOSIMPLES_MAX_CONSULTAS_DIA", 5)
    db = _FakeDB(uso_dia=5)

    with pytest.raises(LimiteDiarioAtingidoError) as exc:
        await consultar(db, "tribunal/tjmg/processo", {"numero_processo": "1"})
    assert "Limite diário" in str(exc.value)
    assert db.inserts == []


# ── Cache do mesmo dia: SEM segunda chamada HTTP nem nova cobrança ─────────────

async def test_consultar_cache_hit_sem_segunda_chamada(infosimples_ligado, monkeypatch):
    async def _nao_chamar(*a, **k):
        raise AssertionError("cache hit não pode gerar nova chamada paga")

    monkeypatch.setattr(infosimples_service, "_post_form", _nao_chamar)
    salvo = {"code": 200, "code_message": "OK", "data": [{"situacao": "Ativo"}],
             "header": {}, "site_receipts": []}
    db = _FakeDB(cache=salvo, uso_dia=1)

    r = await consultar(db, "tribunal/tjmg/processo",
                        {"numero_processo": "00000010220208130000"},
                        user_id="u1", user_role="socio")

    assert r["cache"] is True and r["data"] == salvo["data"]
    assert db.inserts == []  # nenhuma nova cobrança registrada
    audits = [a for a in db.added if a.__class__.__name__ == "AuditLog"]
    assert len(audits) == 1 and "cache" in (audits[0].detalhes or "")


# ── Funções puras: hash, mascaramento, normalização ────────────────────────────

def test_hash_parametros_ignora_token_e_ordem():
    a = hash_parametros({"cpf": "1", "birthdate": "x", "token": "A"})
    b = hash_parametros({"birthdate": "x", "cpf": "1", "token": "B"})
    assert a == b and len(a) == 64


def test_mascarar_parametros_pii():
    m = mascarar_parametros({
        "cpf": "529.982.247-25", "birthdate": "01/01/1980",
        "numero_processo": "00000010220208130000", "token": TOKEN_TESTE,
    })
    assert "token" not in m
    assert m["cpf"].startswith("529") and m["cpf"].endswith("25")
    assert "982" not in m["cpf"]  # miolo mascarado
    assert m["birthdate"] == "**/**/****"
    assert m["numero_processo"] == "00000010220208130000"  # público, em claro


def test_normalizar_processo_tjmg_datas_br_e_ordem():
    proc = normalizar_processo_tjmg({
        "numero": "0000001-02.2020.8.13.0000",
        "classe": "Execução Fiscal",
        "assunto": "IPTU",
        "situacao": "Em andamento",
        "valor_causa": "R$ 10.000,00",
        "partes": [{"nome": "Fulano", "tipo": "Autor"}, "Beltrano"],
        "movimentacoes": [
            {"data": "13/07/2022", "descricao": "Bloqueio/penhora on line"},
            {"data": "01/03/2020", "descricao": "Distribuição"},
            {"data": "02/03/2020", "descricao": ""},  # sem descrição → fora
        ],
    })
    assert proc["classe"] == "Execução Fiscal"
    assert proc["partes"][0]["nome"] == "Fulano"
    assert proc["partes"][1]["nome"] == "Beltrano"
    # Datas dd/mm/aaaa viram ISO e a lista sai ordenada (mais antigo primeiro).
    assert [m["data"] for m in proc["movimentos"]] == ["2020-03-01", "2022-07-13"]


def test_normalizar_receita():
    cpf = normalizar_receita_cpf({"nome": "FULANO DA SILVA",
                                  "situacao_cadastral": "REGULAR"})
    assert cpf["nome"] == "FULANO DA SILVA"
    assert cpf["situacao_cadastral"] == "REGULAR"
    cnpj = normalizar_receita_cnpj({"razao_social": "EMPRESA LTDA",
                                    "situacao": "ATIVA"})
    assert cnpj["razao_social"] == "EMPRESA LTDA"
    assert cnpj["situacao_cadastral"] == "ATIVA"


# ── Merge TJMG: MESMA chave de dedup [dj:hash16] do DataJud ────────────────────

async def test_merge_tjmg_nao_duplica_movimento_ja_importado_do_datajud():
    case = _caso("0000001-02.2020.8.13.0000")
    # Movimento já importado pelo DataJud (sufixo [dj:hash]) — data ISO.
    h = _hash_mov("2020-03-01", "Distribuição")
    descricoes_existentes = [f"Distribuição [dj:{h}]"]

    # O MESMO movimento vindo do TJMG/Infosimples (data dd/mm/aaaa normalizada).
    proc = normalizar_processo_tjmg({
        "movimentacoes": [
            {"data": "01/03/2020", "descricao": "Distribuição"},
            {"data": "13/07/2022", "descricao": "Bloqueio/penhora on line"},
        ],
    })
    db = _FakeDB(descricoes=descricoes_existentes)
    novos, total = await upsert_movimentos_no_caso(db, case, proc["movimentos"])

    assert (novos, total) == (1, 2)  # só o inédito entra
    inseridos = [m for m in db.added if isinstance(m, CaseMovimento)]
    assert len(inseridos) == 1
    assert "Bloqueio/penhora" in inseridos[0].descricao
    assert "[dj:" in inseridos[0].descricao  # chave compartilhada com o DataJud


# ── Endpoints — TJMG ───────────────────────────────────────────────────────────

def test_schema_tjmg_exige_case_id_ou_numero_valido():
    from app.routers.infosimples_tjmg import TJMGProcessoIn

    with pytest.raises(ValidationError):
        TJMGProcessoIn()
    with pytest.raises(ValidationError):
        TJMGProcessoIn(numero_processo="123")  # CNJ tem 20 dígitos
    ok = TJMGProcessoIn(numero_processo="0000001-02.2020.8.13.0000")
    assert ok.case_id is None


async def test_endpoint_tjmg_503_flag_desligada(monkeypatch):
    from app.routers.infosimples_tjmg import TJMGProcessoIn, consultar_processo_tjmg

    monkeypatch.setattr(get_settings(), "INFOSIMPLES_ENABLED", False)
    body = TJMGProcessoIn(numero_processo="0000001-02.2020.8.13.0000")
    with pytest.raises(HTTPException) as exc:
        await consultar_processo_tjmg(body, db=_FakeDB(), cu=_socio())
    assert exc.value.status_code == 503
    assert "INFOSIMPLES" in exc.value.detail


async def test_endpoint_tjmg_429_teto(infosimples_ligado, monkeypatch):
    from app.routers.infosimples_tjmg import TJMGProcessoIn, consultar_processo_tjmg

    monkeypatch.setattr(get_settings(), "INFOSIMPLES_MAX_CONSULTAS_DIA", 1)
    body = TJMGProcessoIn(numero_processo="0000001-02.2020.8.13.0000")
    with pytest.raises(HTTPException) as exc:
        await consultar_processo_tjmg(body, db=_FakeDB(uso_dia=1), cu=_socio())
    assert exc.value.status_code == 429
    assert TOKEN_TESTE not in exc.value.detail


async def test_endpoint_tjmg_merge_no_caso(infosimples_ligado, monkeypatch):
    from app.routers import infosimples_tjmg as router_mod

    resposta = {
        **RESPOSTA_OK,
        "data": [{
            "numero": "0000001-02.2020.8.13.0000",
            "classe": "Execução Fiscal",
            "situacao": "Em andamento",
            "movimentacoes": [
                {"data": "01/03/2020", "descricao": "Distribuição"},
                {"data": "13/07/2022", "descricao": "Bloqueio/penhora on line"},
            ],
        }],
    }
    monkeypatch.setattr(infosimples_service, "_post_form", _fake_post(resposta))

    db = _FakeDB(case=_caso("0000001-02.2020.8.13.0000"))
    body = router_mod.TJMGProcessoIn(case_id="caso1")
    resp = await router_mod.consultar_processo_tjmg(body, db=db, cu=_socio())

    assert resp["case_id"] == "caso1"
    assert resp["classe"] == "Execução Fiscal"
    assert resp["movimentos_novos"] == 2
    assert resp["cache"] is False
    movs = [m for m in db.added if isinstance(m, CaseMovimento)]
    assert len(movs) == 2 and all("[dj:" in m.descricao for m in movs)
    # 2 audits: CONSULTA_PAGA (conector) + SYNC (merge na timeline).
    acoes = sorted(a.acao for a in db.added if a.__class__.__name__ == "AuditLog")
    assert acoes == ["CONSULTA_PAGA", "SYNC"]
    assert db.commits == 2  # bookkeeping do custo + merge


async def test_endpoint_tjmg_404_sem_resultado(infosimples_ligado, monkeypatch):
    from app.routers.infosimples_tjmg import TJMGProcessoIn, consultar_processo_tjmg

    monkeypatch.setattr(infosimples_service, "_post_form",
                        _fake_post({**RESPOSTA_OK, "data": []}))
    body = TJMGProcessoIn(numero_processo="0000001-02.2020.8.13.0000")
    with pytest.raises(HTTPException) as exc:
        await consultar_processo_tjmg(body, db=_FakeDB(), cu=_socio())
    assert exc.value.status_code == 404


# ── Endpoints — Receita Federal ────────────────────────────────────────────────

def test_schemas_receita_validam_dv():
    from app.routers.infosimples_receita import ReceitaCNPJIn, ReceitaCPFIn

    ok = ReceitaCPFIn(cpf="529.982.247-25", data_nascimento="01/01/1980")
    assert ok.cpf == "52998224725"
    with pytest.raises(ValidationError):
        ReceitaCPFIn(cpf="529.982.247-26", data_nascimento="01/01/1980")  # DV errado
    with pytest.raises(ValidationError):
        ReceitaCPFIn(cpf="529.982.247-25", data_nascimento="1980-01-01")  # formato

    ok2 = ReceitaCNPJIn(cnpj="11.222.333/0001-81")
    assert ok2.cnpj == "11222333000181"
    with pytest.raises(ValidationError):
        ReceitaCNPJIn(cnpj="11.222.333/0001-82")  # DV errado


async def test_endpoint_receita_cpf_normaliza(infosimples_ligado, monkeypatch):
    from app.routers.infosimples_receita import ReceitaCPFIn, consultar_cpf

    resposta = {**RESPOSTA_OK, "data": [{
        "nome": "FULANO DA SILVA", "situacao_cadastral": "REGULAR",
        "data_inscricao": "01/01/2000",
    }]}
    monkeypatch.setattr(infosimples_service, "_post_form", _fake_post(resposta))

    db = _FakeDB()
    body = ReceitaCPFIn(cpf="529.982.247-25", data_nascimento="01/01/1980")
    resp = await consultar_cpf(body, db=db, cu=_socio())

    assert resp["nome"] == "FULANO DA SILVA"
    assert resp["situacao_cadastral"] == "REGULAR"
    assert resp["cache"] is False
    # Audit com PII mascarada — CPF nunca em claro, nascimento oculto.
    audit = [a for a in db.added if a.__class__.__name__ == "AuditLog"][0]
    dump = json.dumps(audit.dados_depois)
    assert "52998224725" not in dump
    assert "01/01/1980" not in dump


async def test_endpoint_receita_cnpj_503_flag_desligada(monkeypatch):
    from app.routers.infosimples_receita import ReceitaCNPJIn, consultar_cnpj

    monkeypatch.setattr(get_settings(), "INFOSIMPLES_ENABLED", False)
    body = ReceitaCNPJIn(cnpj="11.222.333/0001-81")
    with pytest.raises(HTTPException) as exc:
        await consultar_cnpj(body, db=_FakeDB(), cu=_socio())
    assert exc.value.status_code == 503


# ── CAR (SICAR) via conector Infosimples — normalizers + endpoints ────────────

def test_normalizar_car_imovel_tolerante():
    imovel = normalizar_car_imovel({
        "numero": "MG-3106705-ABCD", "area": "42.5", "municipio": "Betim",
        "estado": "MG", "situacao_cadastro": "Ativo",
        "coordenadas": {"lat": -19.9, "lng": -44.2},
    })
    assert imovel["numero_car"] == "MG-3106705-ABCD"
    assert imovel["area_ha"] == "42.5"
    assert imovel["municipio"] == "Betim" and imovel["uf"] == "MG"
    assert imovel["situacao"] == "Ativo"
    # Campos ausentes não quebram (tolerância).
    assert normalizar_car_imovel({})["numero_car"] is None


def test_normalizar_car_demonstrativo_tolerante():
    demo = normalizar_car_demonstrativo({
        "situacao": "Analisado", "area_imovel": "42.5",
        "area_reserva_legal": "8.5", "area_app": "3.0",
    })
    assert demo["situacao"] == "Analisado"
    assert demo["area_total"] == "42.5"
    assert demo["reserva_legal"] == "8.5"
    assert demo["app"] == "3.0"
    assert normalizar_car_demonstrativo({})["situacao"] is None


def test_rotas_car_montadas_em_main():
    from app.main import app
    paths = {getattr(r, "path", "") for r in app.routes}
    assert any(p.endswith("/car/imovel") for p in paths)
    assert any(p.endswith("/car/demonstrativo") for p in paths)


async def test_endpoint_car_imovel_503_flag_desligada(monkeypatch):
    from app.routers.car import CARIn, consultar_imovel

    monkeypatch.setattr(get_settings(), "INFOSIMPLES_ENABLED", False)
    with pytest.raises(HTTPException) as exc:
        await consultar_imovel(CARIn(car="MG-3106705-ABCD"), db=_FakeDB(), cu=_socio())
    assert exc.value.status_code == 503


async def test_endpoint_car_imovel_normaliza(infosimples_ligado, monkeypatch):
    from app.routers.car import CARIn, consultar_imovel

    resposta = {**RESPOSTA_OK, "data": [{
        "numero": "MG-3106705-ABCD", "area": "42.5", "municipio": "Betim",
        "uf": "MG", "situacao": "Ativo",
    }]}
    chamadas: list = []
    monkeypatch.setattr(infosimples_service, "_post_form", _fake_post(resposta, chamadas))

    resp = await consultar_imovel(CARIn(car="MG-3106705-ABCD"), db=_FakeDB(), cu=_socio())

    assert resp["numero_car"] == "MG-3106705-ABCD"
    assert resp["municipio"] == "Betim"
    assert resp["cache"] is False
    # Caminho Infosimples correto e o número CAR vai no corpo (nunca na URL).
    assert chamadas[0]["url"].endswith("/car-imovel")
    assert chamadas[0]["dados"]["car"] == "MG-3106705-ABCD"
    assert TOKEN_TESTE not in chamadas[0]["url"]


async def test_endpoint_car_demonstrativo_404_sem_resultado(infosimples_ligado, monkeypatch):
    from app.routers.car import CARIn, consultar_demonstrativo

    monkeypatch.setattr(infosimples_service, "_post_form",
                        _fake_post({**RESPOSTA_OK, "data": []}))
    with pytest.raises(HTTPException) as exc:
        await consultar_demonstrativo(CARIn(car="MG-3106705-ABCD"),
                                      db=_FakeDB(), cu=_socio())
    assert exc.value.status_code == 404


# ── Status: booleans/contadores, sem segredos ──────────────────────────────────

async def test_status_sem_segredos(infosimples_ligado):
    resp = await infosimples_service.status(_FakeDB(uso_dia=3))
    assert resp == {
        "enabled": True, "configured": True,
        "consultas_hoje": 3, "limite_diario": 50,
    }
    assert TOKEN_TESTE not in str(resp)
