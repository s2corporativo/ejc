"""P1 — Motor de Peça (orquestrador único documento→peça).

Cobre, no padrão _FakeDB (rotas REAIS montadas com dependency_overrides):
  • mapa determinístico peça→base legal→prazo (nunca inventado; incertos =
    contagem "verificar");
  • /analisar NUNCA cria Deadline e sempre devolve termo_inicial_confirmado=False;
  • /gerar: 422 sem checklist pronto; 422 sem termo inicial confirmado;
    Deadline criado SÓ após confirmação (confirmado=True, base legal real);
  • permissões (advogado+ / 403 abaixo);
  • AILog registrado na motivação por IA (sanitizar_pii + AILog em toda IA).
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
from app.models.ai_log import AILog
from app.models.deadline import Deadline, DeadlineTipo
from app.models.user import UserRole
from app.routers import motor_peca as mp_router
from app.services import motor_peca_service as mps
from app.services.deadline_calculator import prazo_dias_uteis


# ── Fakes ─────────────────────────────────────────────────────────────────────

class _Res:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar_one(self):
        return self.value

    def scalars(self):
        return self

    def first(self):
        vals = self.all()
        return vals[0] if vals else None

    def all(self):
        if isinstance(self.value, list):
            return self.value
        return [] if self.value is None else [self.value]


class _FakeDB:
    """Devolve resultados na ordem da fila `results` (um por execute)."""

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
    def __init__(self, role=UserRole.advogado, user_id=None):
        self.id = user_id or f"u-{uuid4().hex[:8]}"
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
    """Rotas determinísticas: sem classificação de área por IA nem motivação."""
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


# ── Mapa determinístico ───────────────────────────────────────────────────────

def test_catalogo_contestacao_cpc_335_15_dias_uteis():
    info = mps.prazo_da_peca("contestacao")
    assert info["prazo_dias"] == 15
    assert info["contagem"] == "uteis"
    assert "335" in info["base_legal"]


def test_catalogo_embargos_declaracao_5_dias_uteis():
    info = mps.prazo_da_peca("embargos_declaracao")
    assert info["prazo_dias"] == 5
    assert info["contagem"] == "uteis"
    assert "1.023" in info["base_legal"]


def test_catalogo_defesa_ambiental_20_corridos():
    info = mps.prazo_da_peca("defesa_administrativa_ambiental")
    assert info["prazo_dias"] == 20
    assert info["contagem"] == "corridos"
    assert "6.514" in info["base_legal"]


def test_catalogo_invariantes_nunca_inventa_prazo():
    """Toda peça: contagem válida; prazo certo ⇔ base legal com dispositivo;
    prazo incerto ⇒ contagem 'verificar' e prazo_dias None."""
    for codigo, info in mps.CATALOGO_PECAS.items():
        assert info["contagem"] in mps.CONTAGENS_VALIDAS, codigo
        assert info["base_legal"], codigo
        assert info["fluxo_geracao"] in ("ia_defensiva", "peca_pipeline"), codigo
        if info["contagem"] == "verificar":
            assert info["prazo_dias"] is None, codigo
        else:
            assert isinstance(info["prazo_dias"], int) and info["prazo_dias"] > 0, codigo


def test_override_contestacao_trabalhista_vira_verificar():
    info = mps.prazo_da_peca("contestacao", "trabalhista_conhecimento")
    assert info["contagem"] == "verificar"
    assert info["prazo_dias"] is None
    assert "847" in info["base_legal"]


def test_override_contestacao_jec_vira_verificar():
    info = mps.prazo_da_peca("contestacao", "jec")
    assert info["contagem"] == "verificar"
    assert "9.099" in info["base_legal"]


def test_pecas_cabiveis_mapa_deterministico():
    assert "contestacao" in mps.pecas_cabiveis("processo_civil_comum", "defesa")
    assert "impugnacao_cumprimento" in mps.pecas_cabiveis(
        "processo_civil_comum", "cumprimento_ou_execucao")
    assert "recurso_inominado" in mps.pecas_cabiveis("jec", "pos_sentenca")
    assert "recurso_ordinario" in mps.pecas_cabiveis(
        "trabalhista_conhecimento", "pos_sentenca")
    assert "defesa_administrativa_ambiental" in mps.pecas_cabiveis(
        "ambiental_administrativo", "administrativa")
    # Criminal: sem mapeamento seguro → lista vazia (nunca inventar)
    assert mps.pecas_cabiveis("jecrim", "defesa") == []
    # Rito desconhecido cai no procedimento comum
    assert mps.pecas_cabiveis("rito_inexistente", "defesa") == \
        mps.pecas_cabiveis("processo_civil_comum", "defesa")


def test_todas_pecas_cabiveis_existem_no_catalogo():
    for rito, mapa in mps._MAPA_PECAS.items():
        for pecas in mapa.values():
            for codigo in pecas:
                assert codigo in mps.CATALOGO_PECAS, f"{rito}: {codigo}"


def test_prazo_projetado_sem_termo_fica_pendente():
    out = mps.calcular_prazo_projetado("contestacao", None, None)
    assert out["data_projetada"] is None
    assert out["termo_inicial_confirmado"] is False
    assert out["pendente_confirmacao_humana"] is True


def test_prazo_projetado_com_termo_calcula_mas_nao_confirma():
    termo = date(2026, 7, 1)
    out = mps.calcular_prazo_projetado("contestacao", "processo_civil_comum", termo)
    assert out["data_projetada"] == prazo_dias_uteis(termo, 15).isoformat()
    assert out["termo_inicial_confirmado"] is False
    assert out["pendente_confirmacao_humana"] is True


def test_prazo_projetado_verificar_nao_calcula():
    out = mps.calcular_prazo_projetado(
        "contestacao", "trabalhista_conhecimento", date(2026, 7, 1))
    assert out["data_projetada"] is None
    assert out["contagem"] == "verificar"


# ── /analisar ─────────────────────────────────────────────────────────────────

def test_analisar_403_para_role_abaixo_de_advogado(acesso_ok):
    db = _FakeDB()
    client = _montar(db, role=UserRole.secretaria)
    r = client.post("/cases/case-1/motor-peca/analisar", json={})
    assert r.status_code == 403


def test_analisar_consolida_e_nunca_cria_deadline(
        sem_ia, acesso_ok, texto_fake, checklist_pronto):
    db = _FakeDB()
    client = _montar(db)
    r = client.post("/cases/case-1/motor-peca/analisar", json={
        "termo_inicial": "2026-07-01",
        "peca_codigo": "contestacao",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "rascunho"
    assert body["termo_inicial_confirmado"] is False
    assert body["peca_principal"] == "contestacao"
    # peça cabível com base legal determinística
    contest = [p for p in body["pecas_cabiveis"] if p["codigo"] == "contestacao"]
    assert contest and "335" in contest[0]["base_legal"]
    # prazo projetado mas pendente de confirmação humana
    pj = body["prazo_projetado"]
    assert pj["pendente_confirmacao_humana"] is True
    assert pj["termo_inicial_confirmado"] is False
    assert pj["data_projetada"] == prazo_dias_uteis(date(2026, 7, 1), 15).isoformat()
    # checklist presente
    assert body["checklist"]["pronto"] is True
    # NUNCA cria Deadline no /analisar
    assert not [o for o in db.added if isinstance(o, Deadline)]


def test_analisar_403_ownership_propaga(sem_ia, monkeypatch):
    from fastapi import HTTPException

    async def _nega(db, cu, case_id):
        raise HTTPException(403, "Sem permissão para este caso")

    monkeypatch.setattr(mp_router, "verificar_acesso_caso", _nega)
    client = _montar(_FakeDB())
    r = client.post("/cases/case-x/motor-peca/analisar", json={})
    assert r.status_code == 403


# ── /gerar ────────────────────────────────────────────────────────────────────

def _gerar_payload(**kw):
    base = {
        "peca_codigo": "contestacao",
        "rito_codigo": "processo_civil_comum",
        "termo_inicial": "2026-07-01",
        "termo_inicial_confirmado": True,
    }
    base.update(kw)
    return base


def test_gerar_422_peca_desconhecida(acesso_ok):
    client = _montar(_FakeDB())
    r = client.post("/cases/case-1/motor-peca/gerar",
                    json=_gerar_payload(peca_codigo="peca_inventada"))
    assert r.status_code == 422
    assert "pecas_validas" in r.json()["detail"]


def test_gerar_422_checklist_nao_pronto(acesso_ok, texto_fake, monkeypatch):
    async def _chk(db, case, codigo, texto):
        return ([{"key": "procuracao_vigente", "titulo": "Procuração",
                  "ok": False, "detalhe": "Nenhuma procuração vigente."}], False)

    monkeypatch.setattr(mps, "montar_checklist", _chk)
    db = _FakeDB()
    client = _montar(db)
    r = client.post("/cases/case-1/motor-peca/gerar", json=_gerar_payload())
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["pendentes"][0]["key"] == "procuracao_vigente"
    assert not [o for o in db.added if isinstance(o, Deadline)]


def test_gerar_422_termo_inicial_nao_confirmado(
        acesso_ok, texto_fake, checklist_pronto):
    db = _FakeDB()
    client = _montar(db)
    r = client.post("/cases/case-1/motor-peca/gerar",
                    json=_gerar_payload(termo_inicial_confirmado=False))
    assert r.status_code == 422
    assert r.json()["detail"]["termo_inicial_confirmado"] is False
    assert not [o for o in db.added if isinstance(o, Deadline)]


def test_gerar_422_sem_termo_inicial_mesmo_confirmado(
        acesso_ok, texto_fake, checklist_pronto):
    db = _FakeDB()
    client = _montar(db)
    r = client.post("/cases/case-1/motor-peca/gerar",
                    json=_gerar_payload(termo_inicial=None))
    assert r.status_code == 422
    assert not [o for o in db.added if isinstance(o, Deadline)]


def test_gerar_422_contagem_verificar_exige_data_manual(
        acesso_ok, texto_fake, checklist_pronto):
    db = _FakeDB()
    client = _montar(db)
    r = client.post("/cases/case-1/motor-peca/gerar", json=_gerar_payload(
        peca_codigo="defesa_administrativa", rito_codigo=None))
    assert r.status_code == 422
    assert "data_prazo_manual" in r.json()["detail"]["mensagem"]
    assert not [o for o in db.added if isinstance(o, Deadline)]


def test_gerar_confirmado_cria_deadline_e_dispara_ia_defensiva(
        acesso_ok, texto_fake, checklist_pronto, monkeypatch):
    chamadas = {}

    async def _fake_defensiva(payload, db, user_id):
        chamadas["etapa"] = payload.etapa
        chamadas["texto"] = payload.peticao_inicial
        return {"ai_log_id": "log-1", "is_rascunho": True, "requer_revisao": True}

    monkeypatch.setattr(mp_router, "executar_ia_defensiva", _fake_defensiva)
    db = _FakeDB()
    client = _montar(db)
    r = client.post("/cases/case-1/motor-peca/gerar", json=_gerar_payload())
    assert r.status_code == 201, r.text
    body = r.json()

    # Deadline criado no padrão raio_x, mas CONFIRMADO (termo validado pelo humano)
    deadlines = [o for o in db.added if isinstance(o, Deadline)]
    assert len(deadlines) == 1
    d = deadlines[0]
    assert d.confirmado is True
    assert d.origem == "motor_peca"
    assert d.tipo == DeadlineTipo.processual
    assert "335" in d.base_legal
    assert d.data_prazo == prazo_dias_uteis(date(2026, 7, 1), 15)
    assert db.committed >= 1  # commit ANTES da redação (prazo nunca se perde)

    # Redação via fluxo existente (ia_defensiva) — etapa de contestação
    assert chamadas["etapa"] == "redigir_contestacao"
    assert body["fluxo_geracao"] == "ia_defensiva"
    assert body["redacao"]["ai_log_id"] == "log-1"
    assert body["status"] == "rascunho"
    assert body["termo_inicial_confirmado"] is True


def test_gerar_peca_nao_defensiva_usa_pipeline_existente(
        acesso_ok, texto_fake, checklist_pronto, monkeypatch):
    chamadas = {}

    async def _fake_pipeline(**kw):
        chamadas.update(kw)
        return {"ai_log_id": "log-2", "legal_doc_id": "doc-1"}

    monkeypatch.setattr(mps, "executar_pipeline_peca", _fake_pipeline)
    db = _FakeDB()
    client = _montar(db)
    r = client.post("/cases/case-1/motor-peca/gerar", json=_gerar_payload(
        peca_codigo="apelacao",
        descricao_fatos=TEXTO_LONGO,
        pedidos="Reforma integral da sentença.",
    ))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["fluxo_geracao"] == "peca_pipeline"
    assert chamadas["codigo_peca"] == "apelacao"
    assert body["redacao"]["legal_doc_id"] == "doc-1"
    deadlines = [o for o in db.added if isinstance(o, Deadline)]
    assert len(deadlines) == 1 and "1.003" in deadlines[0].base_legal


def test_gerar_falha_de_ia_preserva_deadline(
        acesso_ok, texto_fake, checklist_pronto, monkeypatch):
    async def _quebra(payload, db, user_id):
        raise RuntimeError("gateway fora do ar")

    monkeypatch.setattr(mp_router, "executar_ia_defensiva", _quebra)
    db = _FakeDB()
    client = _montar(db)
    r = client.post("/cases/case-1/motor-peca/gerar", json=_gerar_payload())
    assert r.status_code == 201
    body = r.json()
    assert body["redacao"] is None
    assert body["redacao_erro"]
    assert [o for o in db.added if isinstance(o, Deadline)]
    assert db.committed >= 1


def test_gerar_403_para_role_abaixo_de_advogado(acesso_ok):
    client = _montar(_FakeDB(), role=UserRole.estagiario)
    r = client.post("/cases/case-1/motor-peca/gerar", json=_gerar_payload())
    assert r.status_code == 403


# ── Motivação por IA — AILog obrigatório ─────────────────────────────────────

@pytest.mark.asyncio
async def test_motivacao_ia_registra_ailog(monkeypatch):
    import app.services.ai_gateway as gw

    resp = SimpleNamespace(
        texto='{"motivacoes": [{"codigo": "contestacao", "motivacao": "Cabível."}]}',
        provedor="fake", modelo="fake-1", input_tokens=10, output_tokens=20,
        fallback_ativado=False,
    )

    async def _fake_chat(**kw):
        return resp

    monkeypatch.setattr(gw, "chat", _fake_chat)
    monkeypatch.setattr(mps, "get_settings",
                        lambda: SimpleNamespace(AI_ENABLED=True))

    db = _FakeDB()
    pecas = [mps.descrever_peca("contestacao")]
    out = await mps.motivacao_pecas_ia(
        db, "u-1", "case-1", "civil", pecas, TEXTO_LONGO)

    logs = [o for o in db.added if isinstance(o, AILog)]
    assert len(logs) == 1
    assert logs[0].pii_removida is True
    assert db.committed == 1
    assert out["ai_log_id"] == logs[0].id
    assert out["motivacoes"][0]["codigo"] == "contestacao"


@pytest.mark.asyncio
async def test_motivacao_ia_desligada_sem_chamada(monkeypatch):
    monkeypatch.setattr(mps, "get_settings",
                        lambda: SimpleNamespace(AI_ENABLED=False))
    db = _FakeDB()
    out = await mps.motivacao_pecas_ia(
        db, "u-1", "case-1", "civil", [mps.descrever_peca("contestacao")], TEXTO_LONGO)
    assert out is None
    assert db.added == []


# ── Checklist real (consultas no padrão conversao_caso) ──────────────────────

@pytest.mark.asyncio
async def test_montar_checklist_pronto_e_bloqueado():
    case = _fake_case()
    cliente_ok = SimpleNamespace(nome="Cliente", razao_social=None,
                                 cpf="x", cnpj=None)
    # pronto: cliente ok, 1 procuração, texto suficiente
    db = _FakeDB(results=[cliente_ok, 1])
    itens, pronto = await mps.montar_checklist(db, case, "contestacao", TEXTO_LONGO)
    assert pronto is True
    assert {i["key"] for i in itens} == {
        "qualificacao_cliente", "procuracao_vigente", "base_fatica_disponivel"}

    # bloqueado: sem procuração e sem texto
    db2 = _FakeDB(results=[cliente_ok, 0])
    itens2, pronto2 = await mps.montar_checklist(db2, case, "contestacao", "")
    assert pronto2 is False
    pendentes = {i["key"] for i in itens2 if not i["ok"]}
    assert pendentes == {"procuracao_vigente", "base_fatica_disponivel"}
