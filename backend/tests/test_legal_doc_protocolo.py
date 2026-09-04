"""Comprovante de protocolo na peça (LegalDoc) — prova de tempestividade.

Contexto (auditoria): o peticionamento no EJC é MANUAL (exporta PDF e protocola
no PJe/eproc por fora). Como nenhum modelo guardava o número/comprovante do
protocolo, a prova de tempestividade ficava fora do sistema. Esta suíte cobre,
sem depender de Postgres:

  - as 4 colunas de protocolo no model LegalDoc;
  - a migration 099 offline (revisão/head na cadeia, DDL idempotente + downgrade);
  - o endpoint PATCH /legal-docs/{id}/protocolo: grava número/tribunal/data (+
    comprovante opcional), rejeita número vazio (422), 404 p/ peça inexistente,
    aplica o gate de ownership por caso e emite audit-log PROTOCOLO_REGISTRADO;
  - os gates da máquina de estados: papel mínimo advogado (403) e peça em
    status pós-aprovação — aprovada/final/protocolada (422 caso contrário);
  - a validação do comprovante (N3): protocolo_comprovante_doc_id deve apontar
    p/ Document existente, não excluído e do MESMO caso da peça (422 senão);
  - B4: peça SEM case_id não aceita comprovante (422) — doc solto não é prova;
  - B3: protocolado_em no futuro é rejeitado no schema (422);
  - B2: o audit-log registra comprovante antigo→novo e protocolado_em.

Fakes no padrão de test_correcoes_go_live.py. Dados 100% fictícios.
"""
from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

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


def _montar(db: _FakeDB, role: str = "advogado"):
    app = FastAPI()
    app.include_router(legal_docs_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id="u1", role=SimpleNamespace(value=role)
    )
    # Estes testes exercitam protocolo/assinatura, não o novo gate transversal
    # Client -> LegalDoc. O gate tem suíte própria em test_client_legal_doc_scope.py.
    app.dependency_overrides[legal_docs_router._enforce_client_legal_doc_scope] = lambda: None
    return TestClient(app)


def _audits(db: _FakeDB):
    return [o for o in db.added if isinstance(o, AuditLog)]


# ── 3. Endpoint PATCH /legal-docs/{id}/protocolo ──────────────────────────────

def test_protocolo_registra_e_audita():
    # 2ª consulta: validação N3 do comprovante — Document vivo do MESMO caso.
    # (B4: comprovante agora EXIGE peça com caso — ownership liberado no fake.)
    async def _permite(*a, **k):
        return None

    db = _FakeDB(results=[
        _Res(one=_peca(case_id="caso-1")),
        _Res(one=SimpleNamespace(id="doc-99", case_id="caso-1", deleted_at=None)),
    ])
    orig = legal_docs_router.verificar_acesso_caso
    legal_docs_router.verificar_acesso_caso = _permite
    try:
        client = _montar(db)
        r = client.patch("/legal-docs/peca-1/protocolo", json={
            "numero_protocolo": "  0801234-56.2026.8.13.0024  ",
            "protocolo_tribunal": "TJMG",
            "protocolado_em": "2026-07-18T12:00:00+00:00",
            "protocolo_comprovante_doc_id": "doc-99",
        })
    finally:
        legal_docs_router.verificar_acesso_caso = orig
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
    # B2: trilha registra comprovante antigo→novo e a data do protocolo.
    assert "comprovante=-→doc-99" in logs[0].detalhes
    assert "protocolado_em=2026-07-18T12:00:00" in logs[0].detalhes
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


def test_protocolo_bloqueado_em_peca_nao_aprovada():
    """M-B1: protocolo NÃO pode furar a máquina de estados — peça em rascunho,
    em_revisao ou corrigida devolve 422 sem gravar nada."""
    for status in (PecaStatus.rascunho, PecaStatus.em_revisao, PecaStatus.corrigida):
        db = _FakeDB(results=[_Res(one=_peca(status=status))])
        client = _montar(db)
        r = client.patch("/legal-docs/peca-1/protocolo", json={
            "numero_protocolo": "PROTO-1",
        })
        assert r.status_code == 422, (status, r.text)
        assert "aprovada" in r.json()["detail"]
        assert not _audits(db) and db.committed == 0


def test_protocolo_aceito_em_status_pos_aprovacao():
    """aprovada/final/protocolada (STATUS_EXIGE_REVISAO) passam pelo gate."""
    for status in (PecaStatus.aprovada, PecaStatus.final, PecaStatus.protocolada):
        db = _FakeDB(results=[_Res(one=_peca(status=status))])
        client = _montar(db)
        r = client.patch("/legal-docs/peca-1/protocolo", json={
            "numero_protocolo": "PROTO-1",
        })
        assert r.status_code == 200, (status, r.text)


def test_protocolo_exige_papel_advogado():
    """M-B1: papel abaixo de advogado (estagiário/secretária) recebe 403 antes
    de qualquer consulta; advogado_auxiliar (nível < advogado) também."""
    for role in ("estagiario", "secretaria", "advogado_auxiliar", "cliente_externo"):
        db = _FakeDB(results=[_Res(one=_peca())])
        client = _montar(db, role=role)
        r = client.patch("/legal-docs/peca-1/protocolo", json={
            "numero_protocolo": "PROTO-1",
        })
        assert r.status_code == 403, (role, r.text)
        assert not _audits(db) and db.committed == 0


def test_protocolo_comprovante_inexistente_422():
    """N3: comprovante que não existe (ou soft-deleted) → 422 sem gravar nada.
    Antes qualquer string era aceita como protocolo_comprovante_doc_id."""
    db = _FakeDB(results=[_Res(one=_peca()), _Res(one=None)])
    client = _montar(db)
    r = client.patch("/legal-docs/peca-1/protocolo", json={
        "numero_protocolo": "PROTO-1",
        "protocolo_comprovante_doc_id": "doc-fantasma",
    })
    assert r.status_code == 422
    assert "Comprovante" in r.json()["detail"]
    assert not _audits(db) and db.committed == 0


def test_protocolo_comprovante_de_caso_alheio_422():
    """N3: Document existente mas de OUTRO caso → 422 (não vira 'prova' de
    tempestividade de peça alheia). Ownership do caso é liberado no fake."""
    async def _permite(*a, **k):
        return None

    db = _FakeDB(results=[
        _Res(one=_peca(case_id="caso-1")),
        _Res(one=SimpleNamespace(id="doc-2", case_id="caso-2", deleted_at=None)),
    ])
    orig = legal_docs_router.verificar_acesso_caso
    legal_docs_router.verificar_acesso_caso = _permite
    try:
        client = _montar(db)
        r = client.patch("/legal-docs/peca-1/protocolo", json={
            "numero_protocolo": "PROTO-1",
            "protocolo_comprovante_doc_id": "doc-2",
        })
    finally:
        legal_docs_router.verificar_acesso_caso = orig
    assert r.status_code == 422
    assert "não pertence ao caso" in r.json()["detail"]
    assert not _audits(db) and db.committed == 0


def test_protocolo_comprovante_em_peca_sem_caso_422():
    """B4: peça sem case_id não pode receber comprovante — documento solto
    não é prova de tempestividade de peça solta (antes: doc sem caso passava)."""
    db = _FakeDB(results=[_Res(one=_peca(case_id=None))])
    client = _montar(db)
    r = client.patch("/legal-docs/peca-1/protocolo", json={
        "numero_protocolo": "PROTO-1",
        "protocolo_comprovante_doc_id": "doc-solto",
    })
    assert r.status_code == 422
    assert "vinculada a um caso" in r.json()["detail"]
    assert not _audits(db) and db.committed == 0


def test_protocolo_sem_comprovante_em_peca_sem_caso_segue_aceito():
    """B4 não regride o fluxo básico: peça sem caso ainda registra número/
    tribunal/data — só o COMPROVANTE exige vínculo com caso."""
    db = _FakeDB(results=[_Res(one=_peca(case_id=None))])
    client = _montar(db)
    r = client.patch("/legal-docs/peca-1/protocolo", json={
        "numero_protocolo": "PROTO-1",
    })
    assert r.status_code == 200, r.text
    assert r.json()["protocolo_comprovante_doc_id"] is None


def test_protocolado_em_no_futuro_422():
    """B3: data de protocolo no futuro falsificaria a prova de tempestividade —
    rejeitada no schema (Pydantic 422) antes de tocar o banco."""
    db = _FakeDB(results=[_Res(one=_peca())])
    client = _montar(db)
    r = client.patch("/legal-docs/peca-1/protocolo", json={
        "numero_protocolo": "PROTO-1",
        "protocolado_em": "2099-01-01T00:00:00+00:00",
    })
    assert r.status_code == 422
    assert "futuro" in r.text
    assert db.committed == 0 and not _audits(db)


def test_protocolo_comprovante_do_mesmo_caso_aceito():
    """N3: Document vivo do MESMO caso da peça passa e é gravado."""
    async def _permite(*a, **k):
        return None

    db = _FakeDB(results=[
        _Res(one=_peca(case_id="caso-1")),
        _Res(one=SimpleNamespace(id="doc-1", case_id="caso-1", deleted_at=None)),
    ])
    orig = legal_docs_router.verificar_acesso_caso
    legal_docs_router.verificar_acesso_caso = _permite
    try:
        client = _montar(db)
        r = client.patch("/legal-docs/peca-1/protocolo", json={
            "numero_protocolo": "PROTO-1",
            "protocolo_comprovante_doc_id": "doc-1",
        })
    finally:
        legal_docs_router.verificar_acesso_caso = orig
    assert r.status_code == 200, r.text
    assert r.json()["protocolo_comprovante_doc_id"] == "doc-1"


# ── 4. FLX-070: PATCH genérico não protocola sem protocolo registrado ────────

async def _gate_liberado(*a, **k):
    return None


def _patch_status_protocolada(db: _FakeDB, role: str = "advogado"):
    """PATCH /legal-docs/{id} com status=protocolada, liberando os gates de
    validação/jurisprudência (fora do escopo FLX-070, testados em suítes
    próprias) sem alterá-los no código de produção."""
    orig_val = legal_docs_router._bloquear_sem_validacao
    orig_jur = legal_docs_router._bloquear_jurisprudencia_nao_validada
    legal_docs_router._bloquear_sem_validacao = _gate_liberado
    legal_docs_router._bloquear_jurisprudencia_nao_validada = _gate_liberado
    try:
        client = _montar(db, role=role)
        return client.patch("/legal-docs/peca-1", json={"status": "protocolada"})
    finally:
        legal_docs_router._bloquear_sem_validacao = orig_val
        legal_docs_router._bloquear_jurisprudencia_nao_validada = orig_jur


def test_patch_protocolada_sem_numero_protocolo_422():
    """FLX-070: peça aprovada SEM numero_protocolo não vira 'protocolada' pelo
    PATCH genérico — registre antes em PATCH /legal-docs/{id}/protocolo."""
    db = _FakeDB(results=[_Res(one=_peca(status=PecaStatus.aprovada))])
    r = _patch_status_protocolada(db)
    assert r.status_code == 422, r.text
    assert "protocolo" in r.json()["detail"].lower()
    assert "/legal-docs/{id}/protocolo" in r.json()["detail"]
    assert not _audits(db) and db.committed == 0


def test_patch_protocolada_sem_advogado_403():
    """FLX-070: papel abaixo de advogado não marca peça como protocolada,
    mesmo com protocolo já registrado."""
    for role in ("estagiario", "secretaria", "advogado_auxiliar"):
        peca = _peca(status=PecaStatus.aprovada)
        peca.numero_protocolo = "PROTO-1"
        db = _FakeDB(results=[_Res(one=peca)])
        r = _patch_status_protocolada(db, role=role)
        assert r.status_code == 403, (role, r.text)
        assert not _audits(db) and db.committed == 0


def test_patch_protocolada_com_protocolo_registrado_e_advogado_passa():
    """FLX-070 fluxo feliz: aprovada → protocolo registrado no endpoint
    dedicado → PATCH status=protocolada por advogado é aceito."""
    peca = _peca(status=PecaStatus.aprovada)
    peca.numero_protocolo = "0801234-56.2026.8.13.0024"
    db = _FakeDB(results=[_Res(one=peca)])
    r = _patch_status_protocolada(db)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "protocolada"
    assert db.committed == 1
    logs = _audits(db)
    assert len(logs) == 1 and logs[0].acao == "UPDATE"


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
