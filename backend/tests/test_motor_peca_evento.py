"""Fase 2 — Motor de Peça com evento processual + recesso CPC art. 220.

Cobre (padrão _FakeDB, rotas reais com dependency_overrides):
  • /analisar com evento+data_evento deriva o termo DETERMINISTICAMENTE
    (base legal citada) mantendo termo_inicial_confirmado=False e sem Deadline;
  • evento incerto ("verificar") não projeta prazo e traz avisos;
  • /gerar com evento cria o Deadline SÓ com termo_inicial_confirmado=True
    (gate 422 intocado) e usa o termo derivado;
  • /gerar com evento não determinável e sem termo manual ⇒ 422;
  • recesso do art. 220 refletido na contagem de dias úteis do motor.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.deadline import Deadline
from app.models.user import UserRole
from app.routers import motor_peca as mp_router
from app.services import motor_peca_service as mps
from app.services.deadline_calculator import prazo_dias_uteis


# ── Fakes (padrão de test_motor_peca.py) ─────────────────────────────────────

class _Res:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar_one(self):
        return self.value

    def scalars(self):
        return self

    def all(self):
        if isinstance(self.value, list):
            return self.value
        return [] if self.value is None else [self.value]


class _FakeDB:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.added = []
        self.committed = 0

    async def execute(self, stmt, *a, **k):
        return _Res(self.results.pop(0) if self.results else None)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed += 1

    async def rollback(self):
        pass


class _FakeUser:
    def __init__(self, role=UserRole.advogado):
        self.id = f"u-{uuid4().hex[:8]}"
        self.role = role
        self.full_name = "Advogado Teste"


def _fake_case(**kw):
    base = dict(
        id="case-1",
        client_id="cli-1",
        tribunal=None,
        fase=None,
        area=SimpleNamespace(value="civil"),
        descricao_fatos="Fatos do caso para teste com mais de cinquenta caracteres de conteúdo.",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _montar(db, role=UserRole.advogado):
    app = FastAPI()
    app.include_router(mp_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: _FakeUser(role)
    return TestClient(app)


TEXTO_LONGO = (
    "Petição inicial distribuída pelo procedimento comum em face do cliente. "
    "O autor alega inadimplemento contratual e pede indenização por danos."
)


@pytest.fixture
def sem_ia(monkeypatch):
    async def _fake_area(db, cu, case, payload, texto):
        return {"valor": "civil", "origem": "area_do_caso", "ai_log_id": None}

    async def _fake_teses(db, area):
        return []

    monkeypatch.setattr(mp_router.intake_router, "_identificar_area", _fake_area)
    monkeypatch.setattr(mp_router.intake_router, "_buscar_teses", _fake_teses)

    async def _sem_motivacao(*a, **k):
        return None

    monkeypatch.setattr(mps, "motivacao_pecas_ia", _sem_motivacao)


@pytest.fixture
def acesso_ok(monkeypatch):
    case = _fake_case()

    async def _ok(db, cu, case_id):
        return case

    monkeypatch.setattr(mp_router, "verificar_acesso_caso", _ok)
    return case


@pytest.fixture
def texto_fake(monkeypatch):
    async def _texto(db, case, texto=None):
        return texto or TEXTO_LONGO

    monkeypatch.setattr(mps, "texto_base_do_caso", _texto)


@pytest.fixture
def checklist_pronto(monkeypatch):
    async def _chk(db, case, codigo, texto):
        return ([{"key": "qualificacao_cliente", "titulo": "ok", "ok": True,
                  "detalhe": "ok"}], True)

    monkeypatch.setattr(mps, "montar_checklist", _chk)


@pytest.fixture
def redacao_fake(monkeypatch):
    async def _fake_defensiva(payload, db, user_id):
        return {"ai_log_id": "log-1", "is_rascunho": True, "requer_revisao": True}

    monkeypatch.setattr(mp_router, "executar_ia_defensiva", _fake_defensiva)


# ── /analisar com evento ─────────────────────────────────────────────────────

def test_analisar_deriva_termo_de_publicacao_dje(
        sem_ia, acesso_ok, texto_fake, checklist_pronto):
    db = _FakeDB()
    client = _montar(db)
    r = client.post("/cases/case-1/motor-peca/analisar", json={
        "peca_codigo": "contestacao",
        "evento": "publicacao_dje",
        "data_evento": "2026-06-08",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    # termo derivado deterministicamente, mas NUNCA confirmado no /analisar
    assert body["termo_inicial_confirmado"] is False
    ev = body["evento_processual"]
    assert ev["contagem_confirmavel"] is True
    assert "224" in ev["base_legal"]
    assert ev["termo_inicial"] == "2026-06-08"
    assert ev["inicio_contagem"] == "2026-06-09"
    pj = body["prazo_projetado"]
    assert pj["termo_inicial_origem"] == "derivado_de_evento"
    assert pj["evento_base_legal"] == ev["base_legal"]
    assert pj["pendente_confirmacao_humana"] is True
    assert pj["data_projetada"] == prazo_dias_uteis(
        date(2026, 6, 8), 15, aplicar_recesso=True).isoformat()
    # NUNCA cria Deadline no /analisar
    assert not [o for o in db.added if isinstance(o, Deadline)]


def test_analisar_termo_explicito_tem_precedencia_sobre_evento(
        sem_ia, acesso_ok, texto_fake, checklist_pronto):
    client = _montar(_FakeDB())
    r = client.post("/cases/case-1/motor-peca/analisar", json={
        "peca_codigo": "contestacao",
        "termo_inicial": "2026-07-01",
        "evento": "juntada_ar",
        "data_evento": "2026-06-10",
    })
    assert r.status_code == 200, r.text
    pj = r.json()["prazo_projetado"]
    assert pj["termo_inicial_origem"] == "informado_pelo_advogado"
    assert pj["termo_inicial"] == "2026-07-01"


def test_analisar_evento_incerto_nao_projeta_prazo(
        sem_ia, acesso_ok, texto_fake, checklist_pronto):
    db = _FakeDB()
    client = _montar(db)
    r = client.post("/cases/case-1/motor-peca/analisar", json={
        "peca_codigo": "contestacao",
        "evento": "intimacao_eletronica",   # sem meio=consulta ⇒ "verificar"
        "data_evento": "2026-06-10",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    ev = body["evento_processual"]
    assert ev["contagem_confirmavel"] is False
    assert ev["termo_inicial"] is None
    assert ev["avisos"]
    pj = body["prazo_projetado"]
    assert pj["data_projetada"] is None       # nada presumido
    assert pj["termo_inicial_origem"] is None
    assert not [o for o in db.added if isinstance(o, Deadline)]


def test_analisar_recesso_art220_reflete_na_projecao(
        sem_ia, acesso_ok, texto_fake, checklist_pronto):
    client = _montar(_FakeDB())
    r = client.post("/cases/case-1/motor-peca/analisar", json={
        "peca_codigo": "contestacao",
        "termo_inicial": "2025-12-15",
    })
    assert r.status_code == 200, r.text
    pj = r.json()["prazo_projetado"]
    esperado = prazo_dias_uteis(date(2025, 12, 15), 15, aplicar_recesso=True)
    assert pj["data_projetada"] == esperado.isoformat()
    # sem o art. 220 a data seria anterior — o aviso explicita a suspensão
    assert esperado != prazo_dias_uteis(date(2025, 12, 15), 15)
    assert "220" in pj["aviso_recesso"]


# ── /gerar com evento ────────────────────────────────────────────────────────

def _payload_gerar(**kw):
    base = {
        "peca_codigo": "contestacao",
        "rito_codigo": "processo_civil_comum",
        "termo_inicial_confirmado": True,
    }
    base.update(kw)
    return base


def test_gerar_com_evento_cria_deadline_com_termo_derivado(
        acesso_ok, texto_fake, checklist_pronto, redacao_fake):
    db = _FakeDB()
    client = _montar(db)
    r = client.post("/cases/case-1/motor-peca/gerar", json=_payload_gerar(
        evento="juntada_ar", data_evento="2026-06-10"))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["evento_processual"]["base_legal"].startswith("CPC, art. 231")
    deadlines = [o for o in db.added if isinstance(o, Deadline)]
    assert len(deadlines) == 1
    d = deadlines[0]
    assert d.confirmado is True
    assert d.data_intimacao == date(2026, 6, 10)   # termo derivado do evento
    assert d.data_prazo == prazo_dias_uteis(
        date(2026, 6, 10), 15, aplicar_recesso=True)
    assert body["deadline"]["termo_inicial"] == "2026-06-10"


def test_gerar_evento_sem_confirmacao_humana_mantem_gate_422(
        acesso_ok, texto_fake, checklist_pronto):
    db = _FakeDB()
    client = _montar(db)
    r = client.post("/cases/case-1/motor-peca/gerar", json=_payload_gerar(
        evento="juntada_ar", data_evento="2026-06-10",
        termo_inicial_confirmado=False))
    assert r.status_code == 422
    assert r.json()["detail"]["termo_inicial_confirmado"] is False
    assert not [o for o in db.added if isinstance(o, Deadline)]


def test_gerar_evento_incerto_sem_termo_manual_422(
        acesso_ok, texto_fake, checklist_pronto):
    db = _FakeDB()
    client = _montar(db)
    r = client.post("/cases/case-1/motor-peca/gerar", json=_payload_gerar(
        evento="intimacao_eletronica", data_evento="2026-06-10"))
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["avisos"]
    assert "11.419" in detail["base_legal"]
    assert not [o for o in db.added if isinstance(o, Deadline)]


def test_gerar_evento_sem_data_evento_422(acesso_ok, texto_fake, checklist_pronto):
    db = _FakeDB()
    client = _montar(db)
    r = client.post("/cases/case-1/motor-peca/gerar",
                    json=_payload_gerar(evento="juntada_ar"))
    assert r.status_code == 422
    assert "data_evento" in r.json()["detail"]["mensagem"]
    assert not [o for o in db.added if isinstance(o, Deadline)]


def test_gerar_recesso_art220_no_deadline(
        acesso_ok, texto_fake, checklist_pronto, redacao_fake):
    db = _FakeDB()
    client = _montar(db)
    r = client.post("/cases/case-1/motor-peca/gerar", json=_payload_gerar(
        termo_inicial="2025-12-15"))
    assert r.status_code == 201, r.text
    d = [o for o in db.added if isinstance(o, Deadline)][0]
    esperado = prazo_dias_uteis(date(2025, 12, 15), 15, aplicar_recesso=True)
    assert d.data_prazo == esperado
    assert esperado != prazo_dias_uteis(date(2025, 12, 15), 15)  # art. 220 aplicado


def test_gerar_termo_explicito_tem_precedencia_sobre_evento(
        acesso_ok, texto_fake, checklist_pronto, redacao_fake):
    db = _FakeDB()
    client = _montar(db)
    r = client.post("/cases/case-1/motor-peca/gerar", json=_payload_gerar(
        termo_inicial="2026-07-01",
        evento="juntada_ar", data_evento="2026-06-10"))
    assert r.status_code == 201, r.text
    d = [o for o in db.added if isinstance(o, Deadline)][0]
    assert d.data_intimacao == date(2026, 7, 1)
    assert d.data_prazo == prazo_dias_uteis(
        date(2026, 7, 1), 15, aplicar_recesso=True)


# ── Projeção no service (unidade) ────────────────────────────────────────────

def test_calcular_prazo_projetado_aplica_recesso_com_aviso():
    out = mps.calcular_prazo_projetado(
        "contestacao", "processo_civil_comum", date(2025, 12, 15))
    esperado = prazo_dias_uteis(date(2025, 12, 15), 15, aplicar_recesso=True)
    assert out["data_projetada"] == esperado.isoformat()
    assert "220" in out["aviso_recesso"]
    assert out["termo_inicial_confirmado"] is False


def test_calcular_prazo_projetado_fora_do_recesso_sem_aviso():
    out = mps.calcular_prazo_projetado(
        "contestacao", "processo_civil_comum", date(2026, 7, 1))
    assert out["data_projetada"] == prazo_dias_uteis(date(2026, 7, 1), 15).isoformat()
    assert "aviso_recesso" not in out
