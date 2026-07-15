# ── tests/test_skill_registry_document_handlers.py ───────────────────────────
# Auditoria 2026-07-15 (achado de code-review/security-review, item ALTO):
# `_h_summarize_document`/`_h_extract_structured_data` buscavam o Document só
# por id/deleted_at e chamavam `documento_service.extrair_e_analisar` direto —
# sem checar ownership (documento de OUTRO caso) nem confidencialidade ("cofre"
# — restrito/confidencial/segredo_justica). IDOR + bypass do controle de sigilo
# já aplicado em `context_builder._documento_autorizado`/`montar_contexto`.
#
# Estes testes travam o guard novo (`_documento_liberado_para_ia`, reusando
# `context_builder._documento_autorizado`): documento de outro caso e documento
# em cofre são REJEITADOS antes de qualquer chamada ao pipeline de intake;
# documento autorizado segue delegando normalmente. Mesmo padrão de mock de
# `app.core.ownership` usado em test_context_builder_ownership.py.
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.core.ownership as ownership
from app.models.document import DocConfidencialidade
from app.services.ai.core import skill_registry


class _FakeResult:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class _FakeDB:
    def __init__(self, doc):
        self._doc = doc

    async def execute(self, *a, **kw):
        return _FakeResult(self._doc)


@pytest.fixture
def _mock_acesso(monkeypatch):
    """Controla verificar_acesso_caso/is_gestao no namespace de ownership
    (importados de forma lazy dentro de context_builder._documento_autorizado)."""
    estado = {"casos_permitidos": set(), "gestao": False}

    async def fake_verificar(db, user, case_id):
        if case_id in estado["casos_permitidos"]:
            return SimpleNamespace(id=case_id)
        raise HTTPException(status_code=403, detail="sem acesso")

    def fake_is_gestao(user):
        return estado["gestao"]

    monkeypatch.setattr(ownership, "verificar_acesso_caso", fake_verificar)
    monkeypatch.setattr(ownership, "is_gestao", fake_is_gestao)
    return estado


_USER = SimpleNamespace(id="user-1", role=SimpleNamespace(value="advogado"))


def _doc(case_id="caso-A", confidencialidade=DocConfidencialidade.normal,
         filepath="/f.pdf", mimetype="application/pdf"):
    return SimpleNamespace(
        id="doc-1", case_id=case_id, uploaded_by=None,
        confidencialidade=confidencialidade,
        filepath=filepath, mimetype=mimetype,
    )


def _bloqueia_pipeline(monkeypatch):
    async def _nao_deve_chamar(*a, **kw):
        raise AssertionError("extrair_e_analisar NÃO deve ser chamado — documento bloqueado")
    monkeypatch.setattr(
        "app.services.documento_service.extrair_e_analisar", _nao_deve_chamar)


# ── _h_summarize_document ──────────────────────────────────────────────────────

async def test_summarize_rejeita_documento_de_outro_caso(_mock_acesso, monkeypatch):
    _mock_acesso["casos_permitidos"] = {"caso-A"}
    _bloqueia_pipeline(monkeypatch)
    db = _FakeDB(_doc(case_id="caso-B"))

    r = await skill_registry._h_summarize_document(
        db, "doc-1", case_id="caso-A", user=_USER)

    assert r["ok"] is False
    assert "não encontrado" in r["erro"].lower()


async def test_summarize_rejeita_documento_em_cofre(_mock_acesso, monkeypatch):
    _mock_acesso["casos_permitidos"] = {"caso-A"}
    _bloqueia_pipeline(monkeypatch)
    db = _FakeDB(_doc(case_id="caso-A", confidencialidade=DocConfidencialidade.restrito))

    r = await skill_registry._h_summarize_document(
        db, "doc-1", case_id="caso-A", user=_USER)

    assert r["ok"] is False
    assert "cofre" in r["erro"].lower()


async def test_summarize_documento_autorizado_delega_ao_pipeline(_mock_acesso, monkeypatch):
    _mock_acesso["casos_permitidos"] = {"caso-A"}
    db = _FakeDB(_doc(case_id="caso-A"))

    capturado = {}

    async def fake_extrair(filepath, mimetype, *, db, enriquecer_rag, user_id):
        capturado["args"] = (filepath, mimetype, enriquecer_rag, user_id)
        return {"ok": True, "intake_result": {"resumo_fatos": "fatos do documento"}}

    monkeypatch.setattr(
        "app.services.documento_service.extrair_e_analisar", fake_extrair)

    r = await skill_registry._h_summarize_document(
        db, "doc-1", case_id="caso-A", user=_USER)

    assert r["ok"] is True
    assert r["resumo_fatos"] == "fatos do documento"
    assert capturado["args"] == ("/f.pdf", "application/pdf", False, "user-1")


# ── _h_extract_structured_data ─────────────────────────────────────────────────

async def test_extract_structured_data_rejeita_documento_de_outro_caso(_mock_acesso, monkeypatch):
    _mock_acesso["casos_permitidos"] = {"caso-A"}
    _bloqueia_pipeline(monkeypatch)
    db = _FakeDB(_doc(case_id="caso-B"))

    r = await skill_registry._h_extract_structured_data(
        db, "doc-1", case_id="caso-A", user=_USER)

    assert r["ok"] is False
    assert "não encontrado" in r["erro"].lower()


async def test_extract_structured_data_rejeita_documento_em_cofre(_mock_acesso, monkeypatch):
    _mock_acesso["casos_permitidos"] = {"caso-A"}
    _bloqueia_pipeline(monkeypatch)
    db = _FakeDB(_doc(case_id="caso-A", confidencialidade=DocConfidencialidade.segredo_justica))

    r = await skill_registry._h_extract_structured_data(
        db, "doc-1", case_id="caso-A", user=_USER)

    assert r["ok"] is False
    assert "cofre" in r["erro"].lower()


async def test_extract_structured_data_documento_autorizado_delega_ao_pipeline(
        _mock_acesso, monkeypatch):
    _mock_acesso["casos_permitidos"] = {"caso-A"}
    db = _FakeDB(_doc(case_id="caso-A"))

    capturado = {}

    async def fake_extrair(filepath, mimetype, *, db, enriquecer_rag, user_id):
        capturado["args"] = (filepath, mimetype, enriquecer_rag, user_id)
        return {"ok": True, "dados_estruturados": {"cpf": "123.456.789-09"}}

    monkeypatch.setattr(
        "app.services.documento_service.extrair_e_analisar", fake_extrair)

    r = await skill_registry._h_extract_structured_data(
        db, "doc-1", case_id="caso-A", user=_USER)

    assert r["ok"] is True
    assert r["dados_estruturados"] == {"cpf": "123.456.789-09"}
    assert capturado["args"] == ("/f.pdf", "application/pdf", True, "user-1")


async def test_summarize_sem_user_e_bloqueado_fail_closed(_mock_acesso, monkeypatch):
    """Sem user autenticado não há como provar o vínculo → nega (mesma regra de
    context_builder._documento_autorizado / _acesso_caso_ok)."""
    _bloqueia_pipeline(monkeypatch)
    db = _FakeDB(_doc(case_id="caso-A"))

    r = await skill_registry._h_summarize_document(
        db, "doc-1", case_id="caso-A", user=None)

    assert r["ok"] is False
    assert "não encontrado" in r["erro"].lower()
