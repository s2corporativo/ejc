"""Núcleo de ajuizamento — rotas, RBAC e segurança (fakes no padrão de
tests/test_legal_doc_protocolo.py: TestClient + dependency_overrides).

Cobre:
  - kill-switch JUDICIAL_FILING_ENABLED (503 sem tocar em banco);
  - RBAC: estagiário/secretaria não praticam ato jurídico (403); perfis de
    tribunal e carga TPU só para admin;
  - ownership por caso (verificar_acesso_caso aplicado em toda rota de filing);
  - respostas nunca ecoam segredo (client_secret/token) nem PII em claro;
  - sanitização da trilha de auditoria.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import UserRole
from app.routers import ajuizamento as router_mod
from app.services.ajuizamento import auditoria as aud


class _Res:
    def __init__(self, one=None, todos=None):
        self._one = one
        self._todos = todos if todos is not None else []

    def scalar_one_or_none(self):
        return self._one

    def scalars(self):
        return self

    def all(self):
        return self._todos


class _FakeDB:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.added = []
        self.committed = 0

    async def execute(self, *a, **k):
        r = self.results.pop(0) if self.results else None
        return r if isinstance(r, _Res) else _Res(r)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def commit(self):
        self.committed += 1

    async def refresh(self, obj):
        pass


def _cliente(role: str = "advogado", db: _FakeDB | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(router_mod.router)
    app.dependency_overrides[get_db] = lambda: db or _FakeDB()
    # `role` precisa ser o enum real: require_roles usa ROLE_LEVEL[role] (hashable).
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id="u1", role=UserRole(role), full_name="Fulano")
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _flag_ligada(monkeypatch):
    """Por padrão a flag fica LIGADA; o teste do kill-switch a desliga."""
    original = get_settings()
    monkeypatch.setattr(router_mod, "get_settings",
                        lambda: original.model_copy(update={"JUDICIAL_FILING_ENABLED": True}))
    yield


@pytest.fixture(autouse=True)
def _sem_ownership(monkeypatch):
    async def _passa(db, cu, case_id):
        return SimpleNamespace(id=case_id, client_id="cli-1", tribunal="TJMG", comarca="Betim",
                               valor_causa=None, sigilo_reforcado=False,
                               advogado_responsavel_id="u1", advogado_auxiliar_id=None)

    monkeypatch.setattr(router_mod, "verificar_acesso_caso", _passa)


# ── Kill-switch ──────────────────────────────────────────────────────────────

def test_flag_desligada_responde_503(monkeypatch):
    original = get_settings()
    monkeypatch.setattr(router_mod, "get_settings",
                        lambda: original.model_copy(update={"JUDICIAL_FILING_ENABLED": False}))
    c = _cliente()
    r = c.post("/ajuizamento/filings", json={"case_id": "caso-1"})
    assert r.status_code == 503 and "JUDICIAL_FILING_ENABLED" in r.json()["detail"]


def test_capacidades_continua_consultavel_com_flag_desligada(monkeypatch):
    original = get_settings()
    monkeypatch.setattr(router_mod, "get_settings",
                        lambda: original.model_copy(update={"JUDICIAL_FILING_ENABLED": False}))

    async def _matriz(db, settings):
        return []

    monkeypatch.setattr(router_mod._roteador, "matriz_completa", _matriz)

    class _TpuVazio:
        def __init__(self, db):
            pass

        async def resumo(self):
            return {"sync": {"estado": "CONDITIONAL", "motivo": "x"}, "por_tipo": {}}

    monkeypatch.setattr(router_mod, "TpuService", _TpuVazio)
    r = _cliente().get("/ajuizamento/capacidades")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["habilitado"] is False
    assert corpo["flags"]["PDPJ_INTEGRATION_ENABLED"] is False
    # Só nomes de flag e estados — nenhum valor de credencial.
    assert "PDPJ_CLIENT_SECRET" not in str(corpo)


# ── RBAC ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("rota,corpo", [
    ("/ajuizamento/filings/f1/aprovar", {"confirmacao": "REVISAR E PROTOCOLAR"}),
    ("/ajuizamento/filings/f1/assinar", {"provider": "registro_externo"}),
    ("/ajuizamento/filings/f1/protocolar", None),
    ("/ajuizamento/filings/f1/confirmar-manual", {"external_protocol": "P-1"}),
])
def test_ato_juridico_exige_advogado(rota, corpo, monkeypatch):
    """Estagiário passa no RBAC de rota (leitura) mas é barrado no ato."""
    async def _obter(self, filing_id, lock=False):
        return SimpleNamespace(id=filing_id, case_id="caso-1", estado="READY_FOR_REVIEW")

    monkeypatch.setattr(router_mod.JudicialFilingService, "obter", _obter)
    r = _cliente(role="estagiario").post(rota, json=corpo)
    assert r.status_code == 403, r.text


@pytest.mark.parametrize("role", ["secretaria", "financeiro", "cliente_externo"])
def test_papeis_sem_acesso_ao_modulo(role):
    r = _cliente(role=role).get("/ajuizamento/filings")
    assert r.status_code == 403


@pytest.mark.parametrize("metodo,rota,corpo", [
    ("post", "/ajuizamento/perfis", {"tribunal_code": "TJMG", "system": "pje_mni"}),
    ("patch", "/ajuizamento/perfis/perf-1", {"authorized": True}),
    ("post", "/ajuizamento/tpu/importar", {"tipo": "classe", "itens": [{"codigo": "7", "descricao": "x"}]}),
    ("post", "/ajuizamento/tpu/sincronizar", {"tipo": "classe", "termo": "comum"}),
])
def test_perfis_e_tpu_exigem_admin(metodo, rota, corpo):
    r = getattr(_cliente(role="advogado"), metodo)(rota, json=corpo)
    assert r.status_code == 403


def test_ownership_negado_propaga_403(monkeypatch):
    async def _nega(db, cu, case_id):
        raise HTTPException(403, "Acesso negado a este caso")

    async def _obter(self, filing_id, lock=False):
        return SimpleNamespace(id=filing_id, case_id="caso-alheio", estado="DRAFT")

    monkeypatch.setattr(router_mod, "verificar_acesso_caso", _nega)
    monkeypatch.setattr(router_mod.JudicialFilingService, "obter", _obter)
    r = _cliente().get("/ajuizamento/filings/f1")
    assert r.status_code == 403


def test_filing_inexistente_e_404(monkeypatch):
    async def _obter(self, filing_id, lock=False):
        raise router_mod.AjuizamentoNaoEncontrado("Ajuizamento não encontrado")

    monkeypatch.setattr(router_mod.JudicialFilingService, "obter", _obter)
    assert _cliente().get("/ajuizamento/filings/f-x").status_code == 404


def test_protocolos_exige_case_id_e_ownership():
    assert _cliente().get("/ajuizamento/protocolos").status_code == 422


# ── Validação de entrada ─────────────────────────────────────────────────────

def test_perfil_recusa_credencial_crua_no_lugar_da_referencia():
    r = _cliente(role="admin").post("/ajuizamento/perfis", json={
        "tribunal_code": "TJMG", "system": "pje_mni", "client_id_ref": "segredo-em-claro"})
    assert r.status_code == 422 and "referência" in r.text


def test_perfil_recusa_base_url_privada():
    db = _FakeDB()
    r = _cliente(role="admin", db=db).post("/ajuizamento/perfis", json={
        "tribunal_code": "TJMG", "system": "pje_mni", "base_url": "https://10.0.0.1/mni"})
    assert r.status_code == 422 and "IP privado" in r.text
    assert db.committed == 0


def test_confirmar_manual_recusa_data_no_futuro(monkeypatch):
    async def _obter(self, filing_id, lock=False):
        return SimpleNamespace(id=filing_id, case_id="caso-1", estado="READY_TO_SUBMIT")

    monkeypatch.setattr(router_mod.JudicialFilingService, "obter", _obter)
    r = _cliente().post("/ajuizamento/filings/f1/confirmar-manual", json={
        "external_protocol": "P-1", "protocolado_em": "2099-01-01T00:00:00Z"})
    assert r.status_code == 422 and "futuro" in r.text


def test_documento_de_tipo_desconhecido_e_recusado_no_schema():
    r = _cliente().post("/ajuizamento/filings", json={
        "case_id": "caso-1",
        "documentos": [{"document_id": "d1", "document_type": "peticao_inicial"}]})
    # peticao_inicial vem da peça (peticao_legal_doc_id), não da lista de anexos.
    assert r.status_code == 422


def test_tpu_tipo_invalido_e_422():
    assert _cliente().get("/ajuizamento/tpu/inexistente").status_code == 422


# ── Auditoria ────────────────────────────────────────────────────────────────

def test_sanitizacao_da_auditoria_remove_segredo_e_pii():
    entrada = {
        "client_secret": "abc", "access_token": "xyz", "documento": "52998224725",
        "documento_mascarado": "***.982.247-**", "documento_hash": "h" * 64,
        "client_id_ref": "pdpj:PDPJ_CLIENT_ID", "case_id": "caso-1",
        "partes": [{"cpf": "52998224725", "nome": "Maria"}],
    }
    saida = aud.sanitizar(entrada)
    assert saida["client_secret"] == "[redigido]"
    assert saida["access_token"] == "[redigido]"
    assert saida["documento"] == "[redigido]"
    assert saida["partes"][0]["cpf"] == "[redigido]"
    assert saida["partes"][0]["nome"] == "Maria"
    # Máscara, hash, referência e ids continuam (são o que a trilha precisa).
    assert saida["documento_mascarado"] == "***.982.247-**"
    assert saida["documento_hash"] == "h" * 64
    assert saida["client_id_ref"] == "pdpj:PDPJ_CLIENT_ID"
    assert saida["case_id"] == "caso-1"


def test_acoes_de_auditoria_cabem_na_coluna():
    from app.models.audit_log import AuditLog

    limite = AuditLog.__table__.columns["acao"].type.length
    acoes = [v for k, v in vars(aud).items() if k.startswith("ACAO_")]
    assert acoes and all(len(a) <= limite for a in acoes)
