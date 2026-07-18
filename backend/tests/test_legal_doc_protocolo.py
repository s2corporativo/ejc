"""Comprovante de protocolo na peça (LegalDoc) — prova de tempestividade.

Contexto (auditoria): o peticionamento no EJC é MANUAL (exporta PDF e protocola
no PJe/eproc por fora). Como nenhum modelo guardava o número/comprovante do
protocolo, a prova de tempestividade ficava fora do sistema. Esta suíte cobre,
sem depender de Postgres:

  - as 4 colunas de protocolo no model LegalDoc;
  - a migration 099 offline (revisão/head na cadeia, DDL idempotente + downgrade);
  - o endpoint PATCH /legal-docs/{id}/protocolo: grava número/tribunal/data (+
    comprovante opcional), rejeita número vazio (422), 404 p/ peça inexistente,
    aplica o gate de ownership por caso e emite audit-log PROTOCOLO_REGISTRADO.

Fakes no padrão de test_correcoes_go_live.py. Dados 100% fictícios.
"""
from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.audit_log import AuditLog
from app.models.legal_doc import LegalDoc, PecaStatus, PecaTipo
from app.routers import legal_docs as legal_docs_router


_VERSIONS = Path(__file__).resolve().parent.parent / "alembic" / "versions"


# ── 1. Colunas no model ───────────────────────────────────────────────────────

def test_model_tem_colunas_de_protocolo():
    cols = LegalDoc.__table__.columns
    for nome in (
        "numero_protocolo", "protocolado_em",
        "protocolo_tribunal", "protocolo_comprovante_doc_id",
    ):
        assert nome in cols, f"coluna {nome} ausente no model LegalDoc"
    # Todas nullable (peças antigas não têm protocolo).
    assert cols["numero_protocolo"].nullable is True
    assert cols["protocolado_em"].nullable is True
    assert cols["protocolo_tribunal"].nullable is True
    assert cols["protocolo_comprovante_doc_id"].nullable is True
    # tz-aware para a data do protocolo.
    assert cols["protocolado_em"].type.timezone is True
    # id de documento SEM FK (padrão audit-actor: não acopla ao ciclo do anexo).
    assert not cols["protocolo_comprovante_doc_id"].foreign_keys


# ── 2. Migration 099 (offline) ────────────────────────────────────────────────

def _carregar_099():
    caminho = _VERSIONS / "099_legal_doc_protocolo.py"
    spec = importlib.util.spec_from_file_location("mig099", caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_099_revisao_e_cadeia():
    mod = _carregar_099()
    assert mod.revision == "099_legal_doc_protocolo"
    assert mod.down_revision == "098_deadline_concluido_por"


def test_migration_099_e_head_unico():
    """099 deve ser o ÚNICO filho de 098 — guarda contra heads múltiplos."""
    filhos = []
    for f in _VERSIONS.glob("*.py"):
        txt = f.read_text(encoding="utf-8", errors="ignore")
        if 'down_revision = "098_deadline_concluido_por"' in txt:
            filhos.append(f.name)
    assert filhos == ["099_legal_doc_protocolo.py"], (
        f"heads múltiplos a partir de 098: {sorted(filhos)}"
    )


def test_migration_099_ddl_idempotente_e_downgrade():
    txt = (_VERSIONS / "099_legal_doc_protocolo.py").read_text(encoding="utf-8")
    for col, tipo in (
        ("numero_protocolo", "varchar(120)"),
        ("protocolado_em", "timestamptz"),
        ("protocolo_tribunal", "varchar(120)"),
        ("protocolo_comprovante_doc_id", "varchar(36)"),
    ):
        assert f"ADD COLUMN IF NOT EXISTS {col} {tipo}" in txt
        assert f"DROP COLUMN IF EXISTS {col}" in txt
    # Sempre em legal_docs, nunca criando tabela nova.
    assert "ALTER TABLE legal_docs" in txt
    assert "CREATE TABLE" not in txt


# ── Fakes p/ o endpoint ───────────────────────────────────────────────────────

class _Res:
    def __init__(self, one=None):
        self._one = one

    def scalar_one_or_none(self):
        return self._one


class _FakeDB:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.added = []
        self.committed = 0
        self.refreshed = []

    async def execute(self, stmt, *a, **k):
        r = self.results.pop(0) if self.results else None
        return r if isinstance(r, _Res) else _Res(r)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed += 1

    async def refresh(self, obj):
        self.refreshed.append(obj)


def _peca(**over):
    base = dict(
        id="peca-1", titulo="Contestação", tipo_peca=PecaTipo.contestacao,
        status=PecaStatus.aprovada, conteudo="corpo", versao=1,
        ai_generated=False, human_reviewed=True, case_id=None,
        created_at=datetime.now(timezone.utc),
    )
    base.update(over)
    return LegalDoc(**base)


def _montar(db: _FakeDB):
    app = FastAPI()
    app.include_router(legal_docs_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id="u1", role=SimpleNamespace(value="advogado")
    )
    return TestClient(app)


def _audits(db: _FakeDB):
    return [o for o in db.added if isinstance(o, AuditLog)]


# ── 3. Endpoint PATCH /legal-docs/{id}/protocolo ──────────────────────────────

def test_protocolo_registra_e_audita():
    db = _FakeDB(results=[_Res(one=_peca())])
    client = _montar(db)
    r = client.patch("/legal-docs/peca-1/protocolo", json={
        "numero_protocolo": "  0801234-56.2026.8.13.0024  ",
        "protocolo_tribunal": "TJMG",
        "protocolado_em": "2026-07-18T12:00:00+00:00",
        "protocolo_comprovante_doc_id": "doc-99",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    # Número normalizado (trim) e demais campos gravados + retornados na peça.
    assert body["numero_protocolo"] == "0801234-56.2026.8.13.0024"
    assert body["protocolo_tribunal"] == "TJMG"
    assert body["protocolo_comprovante_doc_id"] == "doc-99"
    assert body["protocolado_em"].startswith("2026-07-18T12:00:00")
    # Auditoria PROTOCOLO_REGISTRADO gravada e commit efetuado.
    logs = _audits(db)
    assert len(logs) == 1 and logs[0].acao == "PROTOCOLO_REGISTRADO"
    assert logs[0].entidade == "legal_docs" and logs[0].registro_id == "peca-1"
    assert db.committed == 1


def test_protocolo_sem_data_assume_agora():
    db = _FakeDB(results=[_Res(one=_peca())])
    client = _montar(db)
    r = client.patch("/legal-docs/peca-1/protocolo", json={
        "numero_protocolo": "PROTO-123",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["numero_protocolo"] == "PROTO-123"
    # Data assumida (não veio no payload) e tribunal/comprovante ausentes → None.
    assert body["protocolado_em"] is not None
    assert body["protocolo_tribunal"] is None
    assert body["protocolo_comprovante_doc_id"] is None


def test_protocolo_numero_vazio_recusado():
    db = _FakeDB(results=[_Res(one=_peca())])
    client = _montar(db)
    r = client.patch("/legal-docs/peca-1/protocolo", json={
        "numero_protocolo": "   ",
    })
    assert r.status_code == 422
    # Nada gravado nem commitado.
    assert not _audits(db) and db.committed == 0


def test_protocolo_peca_inexistente_404():
    db = _FakeDB(results=[_Res(one=None)])
    client = _montar(db)
    r = client.patch("/legal-docs/nao-existe/protocolo", json={
        "numero_protocolo": "X",
    })
    assert r.status_code == 404
    assert not _audits(db) and db.committed == 0


def test_protocolo_gate_ownership_por_caso():
    """Peça vinculada a caso: sem acesso ao caso → 403 (mesmo gate das demais
    rotas). Verifica que verificar_acesso_caso é acionado antes de gravar."""
    from fastapi import HTTPException

    async def _nega(*a, **k):
        raise HTTPException(status_code=403, detail="sem acesso")

    db = _FakeDB(results=[_Res(one=_peca(case_id="caso-1"))])
    orig = legal_docs_router.verificar_acesso_caso
    legal_docs_router.verificar_acesso_caso = _nega
    try:
        client = _montar(db)
        r = client.patch("/legal-docs/peca-1/protocolo", json={
            "numero_protocolo": "PROTO-1",
        })
    finally:
        legal_docs_router.verificar_acesso_caso = orig
    assert r.status_code == 403
    assert not _audits(db) and db.committed == 0
