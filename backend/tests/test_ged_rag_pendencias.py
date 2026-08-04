"""Pendências de backend do PR #274 — GED + RAG.

1. GET /documents/ — filtros novos (tipo, confidencialidade, data_inicio/
   data_fim sobre created_at, classificacao_pendente → tipo IS NULL), sempre
   ADITIVOS ao escopo de visibilidade existente.
2. PATCH /documents/{id} — atualização de METADADOS (titulo/tipo/
   confidencialidade/case_id) com os mesmos gates do delete/download, audit
   log UPDATE e validação doc↔cliente espelhada de signatures.criar_solicitacao.
   filepath/filename/hash nunca são alteráveis.
3. /rag/buscar e buscar_contexto_rag expõem `doc_id` em cada resultado
   (desbloqueia "enviar para curadoria"/preview no Knowledge Hub).

Fakes no padrão de test_correcoes_go_live.py (FakeDB sem Postgres real).
Dados 100% fictícios.
"""
from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.audit_log import AuditLog
from app.models.document import DocConfidencialidade, Document
from app.models.user import UserRole
from app.routers import documents as documents_router
from app.routers import rag as rag_router


# ── Fakes ─────────────────────────────────────────────────────────────────────

class _Res:
    def __init__(self, one=None, lista=None, scalar=None, mappings=None):
        self._one = one
        self._lista = lista or []
        self._scalar = scalar
        self._mappings = mappings or []

    def scalar_one_or_none(self):
        return self._one

    def scalar(self):
        return self._scalar

    def scalars(self):
        return SimpleNamespace(all=lambda: self._lista)

    def mappings(self):
        return SimpleNamespace(all=lambda: self._mappings)

    def all(self):
        return self._lista


class _FakeDB:
    """Devolve resultados na ordem da fila `results` (um por execute)."""

    def __init__(self, results=None):
        self.results = list(results or [])
        self.added = []
        self.committed = 0
        self.executed = []

    async def execute(self, stmt, *a, **k):
        self.executed.append(stmt)
        r = self.results.pop(0) if self.results else None
        return r if isinstance(r, _Res) else _Res(r)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed += 1


def _user(role=UserRole.admin, uid="u1", client_id=None):
    return SimpleNamespace(id=uid, role=role, client_id=client_id)


def _montar(db: _FakeDB, user=None):
    app = FastAPI()
    app.include_router(documents_router.router)
    app.include_router(rag_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user or _user()
    return TestClient(app)


def _doc(**kw):
    base = dict(
        id="doc-1", titulo="Contrato Antigo", tipo=None,
        filename="contrato.pdf", filepath="2026/07/doc-1.pdf",
        mimetype="application/pdf", size_bytes=100,
        confidencialidade=DocConfidencialidade.confidencial,
        case_id=None, client_id=None, uploaded_by="u1", deleted_at=None,
    )
    base.update(kw)
    return Document(**base)


def _audits(db: _FakeDB) -> list[AuditLog]:
    return [o for o in db.added if isinstance(o, AuditLog)]


def _db_listar():
    """Fila do listar: 1º execute = count, 2º = página de rows."""
    return _FakeDB(results=[_Res(scalar=0), _Res(lista=[])])


def _sql_listar(db: _FakeDB) -> str:
    # último execute é o SELECT paginado (o 1º é o count sobre a subquery)
    return str(db.executed[-1])


# ── 1. GET /documents/ — filtros novos ────────────────────────────────────────

def test_listar_classificacao_pendente_filtra_tipo_null():
    db = _db_listar()
    r = _montar(db).get("/documents/", params={"classificacao_pendente": "true"})
    assert r.status_code == 200
    assert "documents.tipo IS NULL" in _sql_listar(db)


def test_listar_classificacao_pendente_false_filtra_tipo_not_null():
    db = _db_listar()
    r = _montar(db).get("/documents/", params={"classificacao_pendente": "false"})
    assert r.status_code == 200
    assert "documents.tipo IS NOT NULL" in _sql_listar(db)


def test_listar_filtro_tipo_e_confidencialidade():
    db = _db_listar()
    r = _montar(db).get("/documents/", params={
        "tipo": "contrato", "confidencialidade": "restrito",
    })
    assert r.status_code == 200
    sql = _sql_listar(db)
    assert "documents.tipo =" in sql
    assert "documents.confidencialidade =" in sql


def test_listar_confidencialidade_invalida_422():
    db = _db_listar()
    r = _montar(db).get("/documents/", params={"confidencialidade": "ultrasecreto"})
    assert r.status_code == 422
    assert "Confidencialidade inválida" in r.json()["detail"]
    assert db.executed == []  # rejeitado antes de tocar o banco


def test_listar_filtro_datas_sobre_created_at():
    from datetime import datetime, timezone
    db = _db_listar()
    r = _montar(db).get("/documents/", params={
        "data_inicio": "2026-01-01", "data_fim": "2026-01-31",
    })
    assert r.status_code == 200
    stmt = db.executed[-1]
    sql = str(stmt)
    assert "documents.created_at >=" in sql
    assert "documents.created_at <" in sql
    # data_fim é INCLUSIVA: limite superior exclusivo no dia seguinte, 00:00 UTC
    params = stmt.compile().params
    assert datetime(2026, 1, 1, tzinfo=timezone.utc) in params.values()
    assert datetime(2026, 2, 1, tzinfo=timezone.utc) in params.values()


def test_listar_filtros_nao_afrouxam_escopo_de_confidencialidade():
    """Advogado (abaixo de socio) segue restrito a normal/interno mesmo pedindo
    confidencialidade=restrito — o filtro é ADITIVO (AND), nunca substitui o gate."""
    db = _db_listar()
    r = _montar(db, user=_user(role=UserRole.advogado)).get(
        "/documents/", params={"confidencialidade": "restrito"}
    )
    assert r.status_code == 200
    sql = _sql_listar(db)
    assert "documents.confidencialidade IN" in sql   # gate de escopo intacto
    assert "documents.confidencialidade =" in sql    # filtro aditivo


# ── 2. PATCH /documents/{id} ─────────────────────────────────────────────────

def test_patch_atualiza_metadados_e_audita():
    doc = _doc()
    # fila: SELECT doc → SELECT tipos do master (vazio → só legados valem)
    db = _FakeDB(results=[_Res(one=doc), _Res(lista=[])])
    r = _montar(db).patch("/documents/doc-1", json={
        "titulo": "Contrato Novo", "tipo": "contrato",
    })
    assert r.status_code == 200
    assert doc.titulo == "Contrato Novo"
    assert doc.tipo == "contrato"
    body = r.json()
    assert body["titulo"] == "Contrato Novo" and body["tipo"] == "contrato"
    logs = _audits(db)
    assert len(logs) == 1 and logs[0].acao == "UPDATE"
    assert logs[0].entidade == "documents" and logs[0].registro_id == "doc-1"
    assert db.committed == 1


def test_patch_documento_inexistente_404():
    db = _FakeDB(results=[_Res(one=None)])
    r = _montar(db).patch("/documents/nao-existe", json={"titulo": "X"})
    assert r.status_code == 404
    assert db.committed == 0


def test_patch_case_de_outro_cliente_400():
    doc = _doc(client_id="cli-1")
    caso = SimpleNamespace(
        id="caso-2", client_id="cli-2",
        advogado_responsavel_id=None, advogado_auxiliar_id=None,
    )
    # fila: SELECT doc → checagem M2 (não é comprovante de protocolo) →
    # SELECT case (verificar_acesso_caso)
    db = _FakeDB(results=[_Res(one=doc), _Res(one=None), _Res(one=caso)])
    r = _montar(db).patch("/documents/doc-1", json={"case_id": "caso-2"})
    assert r.status_code == 400
    assert "outro cliente" in r.json()["detail"]
    assert doc.case_id is None            # nada aplicado
    assert db.committed == 0 and not _audits(db)


def test_patch_vincula_caso_do_mesmo_cliente_e_deriva_client():
    doc = _doc(client_id=None)
    caso = SimpleNamespace(
        id="caso-1", client_id="cli-1",
        advogado_responsavel_id=None, advogado_auxiliar_id=None,
    )
    db = _FakeDB(results=[_Res(one=doc), _Res(one=None), _Res(one=caso)])
    r = _montar(db).patch("/documents/doc-1", json={"case_id": "caso-1"})
    assert r.status_code == 200
    assert doc.case_id == "caso-1"
    assert doc.client_id == "cli-1"       # regra #8 do upload: derivado do caso
    assert db.committed == 1


def test_patch_nao_move_comprovante_de_protocolo_409():
    """M2 (TOCTOU): documento referenciado em legal_docs.protocolo_comprovante_
    doc_id é prova de tempestividade — mover de caso quebraria a validação N3
    feita no registro do protocolo. 409 com a peça que referencia."""
    doc = _doc(case_id="caso-1")
    peca = SimpleNamespace(id="peca-7", titulo="Contestação X")
    # fila: SELECT doc → SELECT case (ownership do doc.case_id atual) →
    # checagem M2 encontra a peça que referencia
    db = _FakeDB(results=[
        _Res(one=doc), _Res(one=SimpleNamespace(id="caso-1")), _Res(one=peca),
    ])
    r = _montar(db).patch("/documents/doc-1", json={"case_id": "caso-2"})
    assert r.status_code == 409
    assert "Contestação X" in r.json()["detail"]
    assert "peca-7" in r.json()["detail"]
    assert doc.case_id == "caso-1"        # nada aplicado
    assert db.committed == 0 and not _audits(db)


def test_patch_nao_desvincula_comprovante_de_protocolo_409():
    """M2: desvincular (case_id=None) também quebra a prova — mesmo 409."""
    doc = _doc(case_id="caso-1")
    peca = SimpleNamespace(id="peca-7", titulo="Contestação X")
    db = _FakeDB(results=[
        _Res(one=doc), _Res(one=SimpleNamespace(id="caso-1")), _Res(one=peca),
    ])
    r = _montar(db).patch("/documents/doc-1", json={"case_id": None})
    assert r.status_code == 409
    assert doc.case_id == "caso-1"
    assert db.committed == 0


def test_delete_nao_exclui_comprovante_de_protocolo_409():
    """M2: soft-delete de comprovante referenciado em peça → 409; documento
    permanece vivo e nada é auditado/commitado."""
    doc = _doc(case_id="caso-1")
    peca = SimpleNamespace(id="peca-7", titulo="Contestação X")
    # fila: SELECT doc → SELECT case (ownership) → checagem M2 acha a peça
    db = _FakeDB(results=[
        _Res(one=doc), _Res(one=SimpleNamespace(id="caso-1")), _Res(one=peca),
    ])
    r = _montar(db).delete("/documents/doc-1")
    assert r.status_code == 409
    assert "comprovante de protocolo" in r.json()["detail"]
    assert doc.deleted_at is None
    assert db.committed == 0 and not _audits(db)


def test_delete_documento_sem_referencia_segue_funcionando():
    """M2 não regride o delete normal: sem peça referenciando, soft-delete ok."""
    doc = _doc()
    db = _FakeDB(results=[_Res(one=doc), _Res(one=None)])
    r = _montar(db).delete("/documents/doc-1")
    assert r.status_code == 200
    assert doc.deleted_at is not None
    logs = _audits(db)
    assert len(logs) == 1 and logs[0].acao == "DELETE"
    assert db.committed == 1


def test_patch_campos_proibidos_sao_ignorados():
    """filepath/filename/hash não existem no schema do PATCH — extras são
    descartados pelo Pydantic e o arquivo físico permanece intocado."""
    doc = _doc()
    db = _FakeDB(results=[_Res(one=doc)])
    r = _montar(db).patch("/documents/doc-1", json={
        "titulo": "Ok",
        "filepath": "../../etc/passwd",
        "filename": "hack.pdf",
        "mimetype": "text/html",
    })
    assert r.status_code == 200
    assert doc.filepath == "2026/07/doc-1.pdf"
    assert doc.filename == "contrato.pdf"
    assert doc.mimetype == "application/pdf"
    assert doc.titulo == "Ok"


def test_patch_tipo_invalido_422():
    doc = _doc()
    db = _FakeDB(results=[_Res(one=doc), _Res(lista=[])])
    r = _montar(db).patch("/documents/doc-1", json={"tipo": "tipo-inventado"})
    assert r.status_code == 422
    assert doc.tipo is None and db.committed == 0


def test_patch_confidencialidade_invalida_422():
    doc = _doc()
    db = _FakeDB(results=[_Res(one=doc)])
    r = _montar(db).patch("/documents/doc-1", json={"confidencialidade": "x"})
    assert r.status_code == 422
    assert db.committed == 0


def test_patch_advogado_nao_eleva_para_cofre_403():
    """Quem não é socio+ não move documento para restrito+ (senão se trancaria
    fora e/ou criaria cofre sem o gate de leitura correspondente)."""
    doc = _doc(uploaded_by="u2")
    db = _FakeDB(results=[_Res(one=doc)])
    r = _montar(db, user=_user(role=UserRole.advogado, uid="u2")).patch(
        "/documents/doc-1", json={"confidencialidade": "restrito"}
    )
    assert r.status_code == 403
    assert doc.confidencialidade == DocConfidencialidade.normal
    assert db.committed == 0


def test_patch_payload_vazio_422():
    doc = _doc()
    db = _FakeDB(results=[_Res(one=doc)])
    r = _montar(db).patch("/documents/doc-1", json={})
    assert r.status_code == 422


# ── 3. doc_id no /rag/buscar e em buscar_contexto_rag ────────────────────────

async def test_buscar_contexto_rag_textual_expoe_doc_id(monkeypatch):
    """Fallback textual (sem embeddings): cada resultado carrega doc_id."""
    import app.services.embedding_service as emb
    monkeypatch.setattr(emb, "disponivel", lambda: False)

    from app.services.ai_service import buscar_contexto_rag

    linha = SimpleNamespace(
        id="chunk-1", doc_id="kdoc-1", conteudo="Art. 186 do CC...",
        titulo="Código Civil", categoria="legislacao_geral",
        fonte="planalto", confianca="alta", versao=1,
    )

    class _DBTxt:
        async def execute(self, sql, params=None):
            return [linha]

    res = await buscar_contexto_rag(_DBTxt(), "responsabilidade civil objetiva")
    assert res, "fallback textual deveria retornar o chunk fake"
    assert res[0]["doc_id"] == "kdoc-1"
    assert res[0]["chunk_id"] == "chunk-1"


def test_rag_buscar_semantico_expoe_doc_id(monkeypatch):
    """/rag/buscar repassa o shape do pipeline RAG central governado."""
    monkeypatch.setattr(rag_router, "emb_disponivel", lambda: True)

    row = {
        "chunk_id": "chunk-1", "doc_id": "kdoc-1", "conteudo": "Súmula 297 STJ",
        "titulo": "Súmula 297", "categoria": "sumula_stj",
        "confianca": "alta", "score": 0.91,
    }
    async def _fake_buscar(db, consulta, **kwargs):
        return [row]

    monkeypatch.setattr(rag_router, "buscar_contexto_rag", _fake_buscar)
    db = _FakeDB()
    r = _montar(db).get("/rag/buscar", params={"q": "aplicação do CDC a bancos"})
    assert r.status_code == 200
    body = r.json()
    assert body["modo"] == "semantica"
    assert body["resultados"][0]["doc_id"] == "kdoc-1"
    # campos pré-existentes preservados (contrato não alterado)
    for campo in ("chunk_id", "conteudo", "titulo", "categoria", "confianca", "score"):
        assert campo in body["resultados"][0]
    assert body["pipeline"] == "hibrida_governada"
    assert db.executed == []  # rota não mantém um segundo SQL que burle os gates


def test_sql_das_pernas_rag_seleciona_doc_id():
    """Todas as pernas de busca do ai_service (semântica, trigram, FTS e
    textual) selecionam kc.doc_id — nenhum caminho perde a origem do chunk."""
    import inspect
    import app.services.ai_service as ai_service
    fonte = inspect.getsource(ai_service.buscar_contexto_rag) + inspect.getsource(
        ai_service._fundir_lexical
    )
    assert fonte.count("kc.doc_id") >= 4
