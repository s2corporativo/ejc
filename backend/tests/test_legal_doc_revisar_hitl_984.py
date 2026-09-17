"""Regressão P0 do endpoint legado de revisão de peças (#984).

O caminho ``POST /legal-docs/{id}/revisar`` não pode ser uma porta lateral
mais fraca que ``conferir-e-assinar``. Estes testes fixam os dois critérios
originais da issue sem tocar runtime, banco real ou dados reais:

- papel não jurídico não registra revisão humana;
- citação bloqueante não promove o AILog nem comita a peça como revisada.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import get_current_user
from app.routers import legal_docs as legal_docs_router
from app.services import citation_gate as citation_gate_service


class _Res:
    """Resultado mínimo compatível com ``scalar_one_or_none``."""

    def __init__(self, one=None):
        self._one = one

    def scalar_one_or_none(self):
        return self._one


class _FakeDB:
    """Sessão assíncrona mínima para provar ausência de promoção/commit."""

    def __init__(self, results=None):
        self.results = list(results or [])
        self.committed = 0
        self.flushed = 0
        self.refreshed = []

    async def execute(self, stmt, *args, **kwargs):
        del stmt, args, kwargs
        item = self.results.pop(0) if self.results else None
        return item if isinstance(item, _Res) else _Res(item)

    async def commit(self):
        self.committed += 1

    async def flush(self):
        self.flushed += 1

    async def refresh(self, obj):
        self.refreshed.append(obj)

    def add(self, obj):
        del obj


def _app(db: _FakeDB, *, role: str) -> TestClient:
    """Monta somente o router real com dependências controladas."""
    app = FastAPI()
    app.include_router(legal_docs_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id="usuario-teste",
        role=SimpleNamespace(value=role),
    )
    # O escopo Client -> LegalDoc tem suíte própria. Aqui isolamos apenas o
    # contrato de autorização/HITL do endpoint legado de revisão.
    app.dependency_overrides[legal_docs_router._enforce_client_legal_doc_scope] = lambda: None
    return TestClient(app)


def _peca():
    """Peça sintética suficiente para chegar ao gate de validação."""
    return SimpleNamespace(
        id="peca-984",
        conteudo="Conteúdo sintético de teste sem dados pessoais.",
        case_id=None,
        ai_generated=True,
        human_reviewed=False,
        revisor_id=None,
        revisado_em=None,
        notas_revisao=None,
        status="rascunho",
    )


def _log():
    """AILog sintético, corrente e ainda não promovido pelo HITL."""
    return SimpleNamespace(
        id="log-984",
        user_id="usuario-teste",
        status_hitl="gerado",
        prompt_sanitizado=(
            "VALIDATION_SCORE:90\n"
            "VALIDATION_VERDICT:APROVAR\n"
        ),
        created_at=datetime.now(timezone.utc),
        revisado_por=None,
        revisado_em=None,
    )


def test_revisar_rejeita_papel_nao_juridico_antes_de_mutar_estado():
    """Critério #984: secretaria não pode registrar revisão humana."""
    db = _FakeDB()
    client = _app(db, role="secretaria")

    resposta = client.post(
        "/legal-docs/peca-984/revisar",
        json={"aprovado": True, "notas": "revisão sintética"},
    )

    assert resposta.status_code == 403, resposta.text
    assert db.committed == 0
    assert db.flushed == 0


def test_revisar_propaga_bloqueio_de_citacao_sem_promover_hitl(monkeypatch):
    """Critério #984: citation gate 409 impede qualquer falsa aprovação."""
    peca = _peca()
    log = _log()
    db = _FakeDB(results=[
        _Res(peca),  # SELECT LegalDoc FOR UPDATE
        _Res(log),   # _ultima_validacao_peca
        _Res(log),   # SELECT AILog FOR UPDATE
    ])
    client = _app(db, role="advogado")
    chamada = {}

    async def _gate_bloqueia(db_arg, log_arg, status, override, justificativa, user):
        chamada.update(
            status=status,
            override=override,
            justificativa=justificativa,
            user_id=user.id,
            log_id=log_arg.id,
        )
        del db_arg
        raise HTTPException(
            status_code=409,
            detail={
                "erro": "citacoes_nao_verificadas",
                "mensagem": "Citação sintética bloqueada pelo gate de teste",
            },
        )

    monkeypatch.setattr(citation_gate_service, "aplicar_gate_hitl", _gate_bloqueia)

    resposta = client.post(
        "/legal-docs/peca-984/revisar",
        json={"aprovado": True, "notas": "revisão sintética"},
    )

    assert resposta.status_code == 409, resposta.text
    assert chamada == {
        "status": "revisado",
        "override": False,
        "justificativa": None,
        "user_id": "usuario-teste",
        "log_id": "log-984",
    }
    assert log.status_hitl == "gerado"
    assert peca.human_reviewed is False
    assert peca.revisor_id is None
    assert db.committed == 0
