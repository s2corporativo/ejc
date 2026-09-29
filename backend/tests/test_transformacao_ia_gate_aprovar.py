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
def sem_bloqueios_anteriores(monkeypatch):
    """Neutraliza os dois bloqueios pré-gate (fora do escopo deste teste)."""

    async def _nao_bloqueia(*a, **k):
        del a, k
        return None

    monkeypatch.setattr(legal_docs_router, "_bloquear_sem_validacao", _nao_bloqueia)
    monkeypatch.setattr(legal_docs_router, "_bloquear_jurisprudencia_nao_validada", _nao_bloqueia)


def test_aprovar_invoke_gate_e_propaga_bloqueio_sem_promover(
    sem_bloqueios_anteriores, monkeypatch
):
    peca, log = _peca(), _log()
    # Aprovar: SELECT doc; _ultima_validacao_peca (gate); SELECT AILog FOR UPDATE.
    db = _FakeDB(results=[_Res(peca), _Res(log), _Res(log)])
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
        "/legal-docs/peca-aprovar/aprovar", json={"observacoes": "revisão sintética"}
    )

    assert r.status_code == 409, r.text
    # O gate foi de fato invocado nesta rota (não contornado).
    assert chamada == {"status": "revisado", "log_id": "log-aprovar", "user_id": "usuario-teste"}
    # Bloqueio impede promoção humana e commit.
    assert peca.human_reviewed is False
    assert peca.revisor_id is None
    assert db.committed == 0


def test_aprovar_promove_log_quando_gate_passa(sem_bloqueios_anteriores, monkeypatch):
    """Quando o gate aprova, a rota marca o log como revisado."""
    peca, log = _peca(), _log()
    db = _FakeDB(results=[_Res(peca), _Res(log), _Res(log)])
    client = _app(db)

    async def _gate_ok(*a, **k):
        del a, k
        return None

    monkeypatch.setattr(citation_gate_service, "aplicar_gate_hitl", _gate_ok)

    r = client.patch(
        "/legal-docs/peca-aprovar/aprovar", json={"observacoes": "revisão sintética"}
    )

    assert r.status_code == 200, r.text
    assert peca.human_reviewed is True
    # log promovido pelo gate
    assert log.status_hitl == legal_docs_router.AIStatusHITL.revisado
