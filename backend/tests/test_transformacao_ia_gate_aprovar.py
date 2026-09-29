"""Regressão P0: a rota `POST /legal-docs/{id}/aprovar` não pode contornar o gate.

Achado: `aprovar` chamava `_bloquear_sem_validacao` e
`_bloquear_jurisprudencia_nao_validada`, mas NÃO `aplicar_gate_hitl` — ao
contrário do `PATCH`/`revisar`. Isso permitia aprovação → PDF de protocolo
sem a verificação de citações. O teste isola a chamada do gate: neutraliza os
bloqueios anteriores (fora de escopo) e fixa que `aprovar` invoca
`aplicar_gate_hitl` e propaga o bloqueio sem promover a peça.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import get_current_user
from app.routers import legal_docs as legal_docs_router
from app.services import citation_gate as citation_gate_service


class _Res:
    def __init__(self, one=None):
        self._one = one

    def scalar_one_or_none(self):
        return self._one


class _FakeDB:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.committed = 0
        self.added = []

    async def execute(self, stmt, *a, **k):
        del stmt, a, k
        item = self.results.pop(0) if self.results else None
        return item if isinstance(item, _Res) else _Res(item)

    async def commit(self):
        self.committed += 1

    async def flush(self):
        pass

    async def refresh(self, obj):
        del obj

    def add(self, obj):
        self.added.append(obj)


def _app(db) -> TestClient:
    app = FastAPI()
    app.include_router(legal_docs_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id="usuario-teste", role=SimpleNamespace(value="advogado")
    )
    app.dependency_overrides[legal_docs_router._enforce_client_legal_doc_scope] = lambda: None
    return TestClient(app)


def _peca():
    return SimpleNamespace(
        id="peca-aprovar",
        titulo="Peça sintética",
        tipo_peca="peticao",
        versao=1,
        conteudo="Peça sintética. Sem citações. Conteúdo neutro.",
        case_id=None,
        ai_generated=True,
        human_reviewed=False,
        revisor_id=None,
        revisado_em=None,
        notas_revisao=None,
        status="rascunho",
        created_at=datetime.now(timezone.utc),
        deleted_at=None,
    )


def _log():
    return SimpleNamespace(
        id="log-aprovar",
        user_id="usuario-teste",
        status_hitl="gerado",
        prompt_sanitizado="VALIDATION_SCORE:90\nVALIDATION_VERDICT:APROVAR\n",
        created_at=datetime.now(timezone.utc),
        revisado_por=None,
        revisado_em=None,
    )


@pytest.fixture()
def ambiente_gate(monkeypatch):
    """Mantém o quality gate real e isola apenas a jurisprudência."""

    async def _sem_juris(*args, **kwargs):
        del args, kwargs
        return None

    async def _validacao(db, doc):
        del doc
        log = db.validation_log
        hitl = legal_docs_router._status_value(log.status_hitl)
        revisada = hitl in ("revisado", "aplicado")
        return {
            "ai_log_id": log.id,
            "apto_fluxo": revisada,
            "status": "validada" if revisada else "pendente_revisao",
            "motivo": "ok" if revisada else "aguarda HITL",
        }

    monkeypatch.setattr(legal_docs_router, "_ultima_validacao_peca", _validacao)
    monkeypatch.setattr(
        legal_docs_router, "_bloquear_jurisprudencia_nao_validada", _sem_juris
    )


def test_aprovar_invoke_gate_antes_do_quality_gate_e_propaga_bloqueio(
    ambiente_gate, monkeypatch
):
    peca, log = _peca(), _log()
    db = _FakeDB(results=[_Res(peca), _Res(log)])
    db.validation_log = log
    client = _app(db)
    chamada = {}

    async def _gate_bloqueia(db_arg, log_arg, status, override, justificativa, user):
        chamada.update(status=status, log_id=log_arg.id, user_id=user.id)
        del db_arg, override, justificativa
        raise HTTPException(
            status_code=409, detail={"erro": "citacoes_nao_verificadas"}
        )

    monkeypatch.setattr(citation_gate_service, "aplicar_gate_hitl", _gate_bloqueia)

    r = client.patch(
        "/legal-docs/peca-aprovar/aprovar",
        json={"observacoes": "revisão sintética"},
    )

    assert r.status_code == 409, r.text
    assert chamada == {
        "status": "revisado",
        "log_id": "log-aprovar",
        "user_id": "usuario-teste",
    }
    assert peca.human_reviewed is False
    assert peca.revisor_id is None
    assert db.committed == 0


def test_aprovar_transiciona_hitl_antes_de_reavaliar_quality_gate(
    ambiente_gate, monkeypatch
):
    peca, log = _peca(), _log()
    db = _FakeDB(results=[_Res(peca), _Res(log)])
    db.validation_log = log
    client = _app(db)

    async def _gate_ok(*args, **kwargs):
        del args, kwargs
        return None

    monkeypatch.setattr(citation_gate_service, "aplicar_gate_hitl", _gate_ok)

    r = client.patch(
        "/legal-docs/peca-aprovar/aprovar",
        json={"observacoes": "revisão sintética"},
    )

    assert r.status_code == 200, r.text
    assert peca.human_reviewed is True
    assert log.status_hitl == legal_docs_router.AIStatusHITL.revisado
    assert db.committed == 1


def test_aprovar_log_ja_revisado_por_outro_advogado_nao_exige_ownership(
    ambiente_gate, monkeypatch
):
    peca, log = _peca(), _log()
    log.user_id = "outro-advogado"
    log.status_hitl = legal_docs_router.AIStatusHITL.revisado
    db = _FakeDB(results=[_Res(peca), _Res(log)])
    db.validation_log = log
    client = _app(db)
    chamadas = 0

    async def _gate_nao_deve_rodar(*args, **kwargs):
        nonlocal chamadas
        chamadas += 1
        del args, kwargs

    monkeypatch.setattr(
        citation_gate_service, "aplicar_gate_hitl", _gate_nao_deve_rodar
    )

    r = client.patch(
        "/legal-docs/peca-aprovar/aprovar",
        json={"observacoes": "segunda revisão autorizada"},
    )

    assert r.status_code == 200, r.text
    assert chamadas == 0
    assert peca.human_reviewed is True
    assert db.committed == 1
