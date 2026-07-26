"""Revisões imutáveis e gates de fluxo da peça (LegalDoc) — DOC-056/057/058/062/068.

Cobre, sem depender de Postgres (fakes no padrão de test_legal_doc_protocolo.py):

  - DOC-056: editar o conteúdo (PATCH) grava o conteúdo ANTERIOR numa revisão
    imutável e a v1 permanece recuperável via GET /revisoes/{revisao};
  - DOC-057: PATCH genérico marcando status='protocolada' sem número/data de
    protocolo é rejeitado (409);
  - DOC-058: estagiário (papel < advogado) não pode revisar nem aprovar (403);
  - DOC-068: editar peça aprovada reseta o selo (human_reviewed/revisor_id/
    revisado_em) e devolve o status para revisão/rascunho;
  - a migration 125 (revisão/cadeia/DDL idempotente + downgrade).

Dados 100% fictícios.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.audit_log import AuditLog
from app.models.legal_doc import LegalDoc, LegalDocRevisao, PecaStatus, PecaTipo
from app.routers import legal_docs as legal_docs_router


_VERSIONS = Path(__file__).resolve().parent.parent / "alembic" / "versions"


# ── Fakes ─────────────────────────────────────────────────────────────────────

class _Res:
    def __init__(self, one=None, many=None):
        self._one = one
        self._many = list(many or [])

    def scalar_one_or_none(self):
        return self._one

    def scalar(self):
        return self._one

    def scalars(self):
        return self

    def all(self):
        return list(self._many)


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
        status=PecaStatus.rascunho, conteudo="CONTEUDO ORIGINAL V1", versao=1,
        ai_generated=False, human_reviewed=False, revisor_id=None,
        revisado_em=None, notas_revisao=None, case_id=None,
        numero_protocolo=None, protocolado_em=None, protocolo_tribunal=None,
        protocolo_comprovante_doc_id=None,
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
    return TestClient(app)


def _audits(db: _FakeDB):
    return [o for o in db.added if isinstance(o, AuditLog)]


def _revisoes(db: _FakeDB):
    return [o for o in db.added if isinstance(o, LegalDocRevisao)]


# ── DOC-056: histórico imutável + recuperação de v1 ───────────────────────────

def test_editar_conteudo_grava_revisao_do_anterior():
    peca = _peca()
    db = _FakeDB(results=[_Res(one=peca)])
    client = _montar(db)
    r = client.patch("/legal-docs/peca-1", json={"conteudo": "CONTEUDO EDITADO V2"})
    assert r.status_code == 200, r.text
    body = r.json()
    # versão incrementada e conteúdo novo aplicado.
    assert body["versao"] == 2
    # Snapshot imutável do conteúdo ANTERIOR (revisao=1) foi gravado.
    revs = _revisoes(db)
    assert len(revs) == 1
    rev = revs[0]
    assert rev.legal_doc_id == "peca-1"
    assert rev.revisao == 1
    assert rev.conteudo == "CONTEUDO ORIGINAL V1"
    assert rev.origem == "edicao_manual"
    assert rev.gerado_por == "u1"
    assert rev.imutavel is True
    assert isinstance(rev.content_hash, str) and len(rev.content_hash) == 64


def test_recuperar_revisao_v1_apos_editar_para_v2():
    # Fase 1: edita v1 → v2, capturando a revisão imutável gerada.
    peca = _peca()
    db1 = _FakeDB(results=[_Res(one=peca)])
    client1 = _montar(db1)
    r1 = client1.patch("/legal-docs/peca-1", json={"conteudo": "CONTEUDO EDITADO V2"})
    assert r1.status_code == 200, r1.text
    rev = _revisoes(db1)[0]

    # Fase 2: GET /revisoes/1 recupera o CONTEÚDO da v1 preservada.
    db2 = _FakeDB(results=[_Res(one=peca), _Res(one=rev)])
    client2 = _montar(db2)
    r2 = client2.get("/legal-docs/peca-1/revisoes/1")
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["revisao"] == 1
    assert body["conteudo"] == "CONTEUDO ORIGINAL V1"


def test_listar_revisoes_exige_advogado():
    peca = _peca()
    db = _FakeDB(results=[_Res(one=peca)])
    client = _montar(db, role="estagiario")
    r = client.get("/legal-docs/peca-1/revisoes")
    assert r.status_code == 403, r.text


# ── DOC-057: protocolada pelo PATCH genérico exige protocolo prévio ───────────

def test_patch_para_protocolada_sem_numero_rejeitado():
    # Peça aprovada, mas SEM número/data de protocolo → transição bloqueada (409).
    peca = _peca(status=PecaStatus.aprovada, human_reviewed=True)
    db = _FakeDB(results=[_Res(one=peca)])
    client = _montar(db)
    r = client.patch("/legal-docs/peca-1", json={"status": "protocolada"})
    assert r.status_code == 409, r.text
    assert "protocolo" in r.json()["detail"].lower()
    # Nada commitado nem auditado.
    assert db.committed == 0 and not _audits(db)


def test_patch_para_protocolada_com_protocolo_registrado_passa():
    # Com número + data já gravados (pelo endpoint dedicado), a transição passa.
    peca = _peca(
        status=PecaStatus.aprovada, human_reviewed=True,
        numero_protocolo="0801234-56.2026.8.13.0024",
        protocolado_em=datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc),
    )
    # Após o gate DOC-057, o PATCH aplica _bloquear_sem_validacao (status
    # 'protocolada' ∈ STATUS_EXIGE_VALIDACAO) → consulta AILog de validação.
    log = SimpleNamespace(
        id="log-1",
        prompt_sanitizado=(
            "RELATORIO DE VALIDACAO JURIDICA LEGAL_DOC_ID:peca-1 "
            f"score_confianca: 90 veredito: APROVAR CONTENT_HASH:{legal_docs_router._content_hash(peca.conteudo)}"
        ),
        resposta="RELATORIO DE VALIDACAO JURIDICA",
        status_hitl=SimpleNamespace(value="aplicado"),
        created_at=datetime.now(timezone.utc),
    )
    db = _FakeDB(results=[_Res(one=peca), _Res(one=log)])
    client = _montar(db)
    r = client.patch("/legal-docs/peca-1", json={"status": "protocolada"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "protocolada"


# ── DOC-058: revisar/aprovar exigem advogado+ ─────────────────────────────────

def test_estagiario_nao_pode_revisar():
    db = _FakeDB(results=[_Res(one=_peca())])
    client = _montar(db, role="estagiario")
    r = client.post("/legal-docs/peca-1/revisar", json={"aprovado": True})
    assert r.status_code == 403, r.text
    # Bloqueio antes de qualquer escrita.
    assert db.committed == 0 and not _audits(db)


def test_estagiario_nao_pode_aprovar():
    db = _FakeDB(results=[_Res(one=_peca())])
    client = _montar(db, role="estagiario")
    r = client.patch("/legal-docs/peca-1/aprovar", json={"observacoes": "ok"})
    assert r.status_code == 403, r.text
    assert db.committed == 0 and not _audits(db)


def test_revisar_sem_caso_exige_advogado_mesmo_com_case_null():
    # DOC-058: peça sem caso (case_id=NULL) também exige advogado+.
    db = _FakeDB(results=[_Res(one=_peca(case_id=None))])
    client = _montar(db, role="secretaria")
    r = client.post("/legal-docs/peca-1/revisar", json={"aprovado": True})
    assert r.status_code == 403, r.text


# ── DOC-068: editar peça aprovada reseta o selo ──────────────────────────────

def test_editar_peca_aprovada_reseta_selo():
    peca = _peca(
        status=PecaStatus.aprovada, human_reviewed=True,
        revisor_id="revisor-9", revisado_em=datetime.now(timezone.utc),
    )
    db = _FakeDB(results=[_Res(one=peca)])
    client = _montar(db)
    r = client.patch("/legal-docs/peca-1", json={"conteudo": "CONTEUDO EDITADO V2"})
    assert r.status_code == 200, r.text
    body = r.json()
    # Selo invalidado: aprovação anterior deixou de valer.
    assert body["human_reviewed"] is False
    assert body["revisor_id"] is None
    # Status volta para rascunho (peça não-IA) e versão avança.
    assert body["status"] == "rascunho"
    assert body["versao"] == 2
    # E a revisão imutável da versão aprovada foi preservada.
    assert len(_revisoes(db)) == 1


def test_editar_conteudo_de_peca_ia_volta_para_em_revisao():
    peca = _peca(ai_generated=True, human_reviewed=True, status=PecaStatus.aprovada,
                 revisor_id="revisor-9", revisado_em=datetime.now(timezone.utc))
    db = _FakeDB(results=[_Res(one=peca)])
    client = _montar(db)
    r = client.patch("/legal-docs/peca-1", json={"conteudo": "NOVO CORPO IA"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "em_revisao"
    assert body["human_reviewed"] is False


# ── Migration 125 (offline) ───────────────────────────────────────────────────

def test_migration_125_revisao_e_cadeia():
    # Lê o texto (evita importar `alembic.op` fora do contexto Alembic).
    txt = (_VERSIONS / "125_legal_doc_revisao.py").read_text(encoding="utf-8")
    assert 'revision = "125_legal_doc_revisao"' in txt
    assert 'down_revision = "124_data_room_token_hash"' in txt


def test_migration_125_ddl_idempotente_e_downgrade():
    txt = (_VERSIONS / "125_legal_doc_revisao.py").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS legal_doc_revisoes" in txt
    assert "REFERENCES legal_docs(id)" in txt
    assert "REFERENCES users(id)" in txt
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_legal_doc_revisoes_doc_revisao" in txt
    assert "DROP TABLE IF EXISTS legal_doc_revisoes" in txt


# ── DOC-068: validação amarrada ao hash do conteúdo ──────────────────────────

def test_validacao_de_versao_anterior_nao_e_aceita_apos_edicao():
    peca = _peca(status=PecaStatus.aprovada, conteudo="CONTEUDO NOVO")
    # Log de validação carrega o hash de um conteúdo ANTIGO (diferente do atual).
    log = SimpleNamespace(
        id="log-1",
        prompt_sanitizado=(
            "RELATORIO DE VALIDACAO JURIDICA LEGAL_DOC_ID:peca-1 "
            "score_confianca: 95 veredito: APROVAR "
            f"CONTENT_HASH:{legal_docs_router._content_hash('CONTEUDO ANTIGO')}"
        ),
        resposta="RELATORIO DE VALIDACAO JURIDICA",
        status_hitl=SimpleNamespace(value="aplicado"),
        created_at=datetime.now(timezone.utc),
    )
    resultado = legal_docs_router._montar_validacao(log, peca.conteudo)
    assert resultado["apto_fluxo"] is False
    assert resultado["status"] == "conteudo_alterado"
