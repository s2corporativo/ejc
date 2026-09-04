"""Pendências de backend do PR #274 — GED + RAG.

1. GET /documents/ — filtros de tipo, confidencialidade, datas e classificação
   pendente permanecem aditivos ao escopo de visibilidade.
2. PATCH /documents/{id} — atualiza SOMENTE metadados não estruturais
   (titulo/tipo/confidencialidade). Vínculo com caso é operação de domínio
   dedicada; campos extras, físicos ou ``case_id`` falham fechado com 422.
3. DELETE /documents/{id} — soft-delete condicionado à guarda canônica de
   referências, sem expor títulos/PII em conflitos.
4. /rag/buscar e buscar_contexto_rag expõem `doc_id` em cada resultado.

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

class _MappingsResult:
    def __init__(self, payload):
        self.payload = payload

    def all(self):
        return self.payload if isinstance(self.payload, list) else []

    def one(self):
        return self.payload if isinstance(self.payload, dict) else {}


class _Res:
    def __init__(self, one=None, lista=None, scalar=None, mappings=None):
        self._one = one
        self._lista = lista or []
        self._scalar = scalar
        self._mappings = [] if mappings is None else mappings

    def scalar_one_or_none(self):
        return self._one

    def scalar(self):
        return self._scalar

    def scalars(self):
        return SimpleNamespace(all=lambda: self._lista)

    def mappings(self):
        return _MappingsResult(self._mappings)

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
        del a, k
        self.executed.append(stmt)
        result = self.results.pop(0) if self.results else None
        return result if isinstance(result, _Res) else _Res(result)

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
        id="doc-1",
        titulo="Contrato Antigo",
        tipo=None,
        filename="contrato.pdf",
        filepath="2026/07/doc-1.pdf",
        mimetype="application/pdf",
        size_bytes=100,
        confidencialidade=DocConfidencialidade.confidencial,
        case_id=None,
        client_id=None,
        uploaded_by="u1",
        deleted_at=None,
    )
    base.update(kw)
    return Document(**base)


def _audits(db: _FakeDB) -> list[AuditLog]:
    return [obj for obj in db.added if isinstance(obj, AuditLog)]


def _db_listar():
    """Fila do listar: 1º execute = count, 2º = página de rows."""
    return _FakeDB(results=[_Res(scalar=0), _Res(lista=[])])


def _sql_listar(db: _FakeDB) -> str:
    return str(db.executed[-1])


def _referencias(**overrides: bool) -> dict[str, bool]:
    flags = {
        "protocolo": False,
        "prova": False,
        "assinatura": False,
        "centro_custo": False,
        "fee_payment": False,
        "deadline": False,
        "solicitacao_cliente": False,
        "contrato": False,
        "processo_eletronico": False,
        "data_room": False,
        "intake": False,
        "versao_posterior": False,
    }
    flags.update(overrides)
    return flags


# ── 1. GET /documents/ — filtros ──────────────────────────────────────────────

def test_listar_classificacao_pendente_filtra_tipo_null():
    db = _db_listar()
    response = _montar(db).get(
        "/documents/", params={"classificacao_pendente": "true"}
    )
    assert response.status_code == 200
    assert "documents.tipo IS NULL" in _sql_listar(db)


def test_listar_classificacao_pendente_false_filtra_tipo_not_null():
    db = _db_listar()
    response = _montar(db).get(
        "/documents/", params={"classificacao_pendente": "false"}
    )
    assert response.status_code == 200
    assert "documents.tipo IS NOT NULL" in _sql_listar(db)


def test_listar_filtro_tipo_e_confidencialidade():
    db = _db_listar()
    response = _montar(db).get(
        "/documents/",
        params={"tipo": "contrato", "confidencialidade": "restrito"},
    )
    assert response.status_code == 200
    sql = _sql_listar(db)
    assert "documents.tipo =" in sql
    assert "documents.confidencialidade =" in sql


def test_listar_confidencialidade_invalida_422():
    db = _db_listar()
    response = _montar(db).get(
        "/documents/", params={"confidencialidade": "ultrasecreto"}
    )
    assert response.status_code == 422
    assert "Confidencialidade inválida" in response.json()["detail"]
    assert db.executed == []


def test_listar_filtro_datas_sobre_created_at():
    from datetime import datetime, timezone

    db = _db_listar()
    response = _montar(db).get(
        "/documents/",
        params={"data_inicio": "2026-01-01", "data_fim": "2026-01-31"},
    )
    assert response.status_code == 200
    stmt = db.executed[-1]
    sql = str(stmt)
    assert "documents.created_at >=" in sql
    assert "documents.created_at <" in sql
    params = stmt.compile().params
    assert datetime(2026, 1, 1, tzinfo=timezone.utc) in params.values()
    assert datetime(2026, 2, 1, tzinfo=timezone.utc) in params.values()


def test_listar_filtros_nao_afrouxam_escopo_de_confidencialidade():
    db = _db_listar()
    response = _montar(db, user=_user(role=UserRole.advogado)).get(
        "/documents/", params={"confidencialidade": "restrito"}
    )
    assert response.status_code == 200
    sql = _sql_listar(db)
    assert "documents.confidencialidade IN" in sql
    assert "documents.confidencialidade =" in sql


# ── 2. PATCH /documents/{id} — metadados estritos ─────────────────────────────

def test_patch_atualiza_metadados_e_audita():
    doc = _doc()
    db = _FakeDB(results=[_Res(one=doc), _Res(lista=[])])
    response = _montar(db).patch(
        "/documents/doc-1",
        json={"titulo": "Contrato Novo", "tipo": "contrato"},
    )
    assert response.status_code == 200
    assert doc.titulo == "Contrato Novo"
    assert doc.tipo == "contrato"
    body = response.json()
    assert body["titulo"] == "Contrato Novo"
    assert body["tipo"] == "contrato"
    logs = _audits(db)
    assert len(logs) == 1
    assert logs[0].acao == "UPDATE"
    assert logs[0].entidade == "documents"
    assert logs[0].registro_id == "doc-1"
    assert logs[0].dados_depois == {"campos_alterados": ["tipo", "titulo"]}
    assert db.committed == 1


def test_patch_documento_inexistente_404():
    db = _FakeDB(results=[_Res(one=None)])
    response = _montar(db).patch(
        "/documents/nao-existe", json={"titulo": "X"}
    )
    assert response.status_code == 404
    assert db.committed == 0


def test_patch_case_id_e_rejeitado_antes_de_tocar_banco():
    db = _FakeDB()
    response = _montar(db).patch(
        "/documents/doc-1", json={"case_id": "caso-2"}
    )
    assert response.status_code == 422
    assert db.executed == []
    assert db.committed == 0


def test_patch_desvinculo_case_id_null_tambem_e_rejeitado():
    db = _FakeDB()
    response = _montar(db).patch(
        "/documents/doc-1", json={"case_id": None}
    )
    assert response.status_code == 422
    assert db.executed == []


def test_patch_campos_fisicos_extras_sao_rejeitados_fail_closed():
    doc = _doc()
    db = _FakeDB(results=[_Res(one=doc)])
    response = _montar(db).patch(
        "/documents/doc-1",
        json={
            "titulo": "Tentativa",
            "filepath": "../../etc/passwd",
            "filename": "hack.pdf",
            "mimetype": "text/html",
        },
    )
    assert response.status_code == 422
    assert db.executed == []
    assert doc.filepath == "2026/07/doc-1.pdf"
    assert doc.filename == "contrato.pdf"
    assert doc.mimetype == "application/pdf"
    assert doc.titulo == "Contrato Antigo"


def test_patch_tipo_invalido_422():
    doc = _doc()
    db = _FakeDB(results=[_Res(one=doc), _Res(lista=[])])
    response = _montar(db).patch(
        "/documents/doc-1", json={"tipo": "tipo-inventado"}
    )
    assert response.status_code == 422
    assert doc.tipo is None
    assert db.committed == 0


def test_patch_confidencialidade_invalida_422():
    doc = _doc()
    db = _FakeDB(results=[_Res(one=doc)])
    response = _montar(db).patch(
        "/documents/doc-1", json={"confidencialidade": "x"}
    )
    assert response.status_code == 422
    assert db.committed == 0


def test_patch_advogado_nao_eleva_para_cofre_403():
    doc = _doc(
        uploaded_by="u2",
        confidencialidade=DocConfidencialidade.normal,
    )
    db = _FakeDB(results=[_Res(one=doc)])
    response = _montar(
        db,
        user=_user(role=UserRole.advogado, uid="u2"),
    ).patch(
        "/documents/doc-1",
        json={"confidencialidade": "restrito"},
    )
    assert response.status_code == 403
    assert doc.confidencialidade == DocConfidencialidade.normal
    assert db.committed == 0


def test_patch_payload_vazio_422():
    doc = _doc()
    db = _FakeDB(results=[_Res(one=doc)])
    response = _montar(db).patch("/documents/doc-1", json={})
    assert response.status_code == 422


# ── 3. DELETE /documents/{id} — grafo canônico ────────────────────────────────

def test_delete_nao_exclui_documento_com_referencia_ativa_e_nao_vaza_titulo():
    doc = _doc()
    db = _FakeDB(
        results=[
            _Res(one=doc),
            _Res(mappings=_referencias(protocolo=True)),
        ]
    )
    response = _montar(db).delete("/documents/doc-1")
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "comprovante de protocolo" in detail
    assert "Contestação" not in detail
    assert "peca-" not in detail
    assert doc.deleted_at is None
    assert db.committed == 0
    assert not _audits(db)


def test_delete_documento_sem_referencia_segue_soft_delete():
    doc = _doc()
    db = _FakeDB(
        results=[
            _Res(one=doc),
            _Res(mappings=_referencias()),
        ]
    )
    response = _montar(db).delete("/documents/doc-1")
    assert response.status_code == 200
    assert doc.deleted_at is not None
    logs = _audits(db)
    assert len(logs) == 1
    assert logs[0].acao == "DELETE"
    # Auditoria factual: o soft-delete é reversível e não faz I/O no storage,
    # então "preservado" é INTENÇÃO do lifecycle, não fato observado. As duas
    # dimensões ficam separadas — quem ler a trilha sabe que ninguém conferiu
    # a existência física do arquivo.
    assert logs[0].dados_depois == {
        "storage": "local",
        "storage_preservacao_intencao": True,
        "storage_verificado": False,
    }
    assert db.committed == 1


# ── 4. doc_id no /rag/buscar e em buscar_contexto_rag ────────────────────────

async def test_buscar_contexto_rag_textual_expoe_doc_id(monkeypatch):
    """Fallback textual (sem embeddings): cada resultado carrega doc_id."""
    import app.services.embedding_service as emb

    monkeypatch.setattr(emb, "disponivel", lambda: False)

    from app.services.ai_service import buscar_contexto_rag

    linha = SimpleNamespace(
        id="chunk-1",
        doc_id="kdoc-1",
        conteudo="Art. 186 do CC...",
        titulo="Código Civil",
        categoria="legislacao_geral",
        fonte="planalto",
        confianca="alta",
        versao=1,
    )

    class _DBTxt:
        async def execute(self, sql, params=None):
            del sql, params
            return [linha]

    result = await buscar_contexto_rag(
        _DBTxt(), "responsabilidade civil objetiva"
    )
    assert result, "fallback textual deveria retornar o chunk fake"
    assert result[0]["doc_id"] == "kdoc-1"
    assert result[0]["chunk_id"] == "chunk-1"


def test_rag_buscar_semantico_expoe_doc_id(monkeypatch):
    """/rag/buscar repassa o shape do pipeline RAG central governado."""
    monkeypatch.setattr(rag_router, "emb_disponivel", lambda: True)

    row = {
        "chunk_id": "chunk-1",
        "doc_id": "kdoc-1",
        "conteudo": "Súmula 297 STJ",
        "titulo": "Súmula 297",
        "categoria": "sumula_stj",
        "confianca": "alta",
        "score": 0.91,
    }

    async def _fake_buscar(db, consulta, **kwargs):
        del db, consulta, kwargs
        return [row]

    monkeypatch.setattr(rag_router, "buscar_contexto_rag", _fake_buscar)
    db = _FakeDB()
    response = _montar(db).get(
        "/rag/buscar", params={"q": "aplicação do CDC a bancos"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["modo"] == "semantica"
    assert body["resultados"][0]["doc_id"] == "kdoc-1"
    for campo in (
        "chunk_id",
        "conteudo",
        "titulo",
        "categoria",
        "confianca",
        "score",
    ):
        assert campo in body["resultados"][0]
    assert body["pipeline"] == "hibrida_governada"
    assert db.executed == []


def test_sql_das_pernas_rag_seleciona_doc_id():
    """Todas as pernas de busca do ai_service selecionam kc.doc_id."""
    import inspect
    import app.services.ai_service as ai_service

    fonte = inspect.getsource(ai_service.buscar_contexto_rag) + inspect.getsource(
        ai_service._fundir_lexical
    )
    assert fonte.count("kc.doc_id") >= 4
