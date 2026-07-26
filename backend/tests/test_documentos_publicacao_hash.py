"""Migração 122 — publicação explícita no Portal, hash SHA-256 e antivírus.

Cobre (sem Postgres, no padrão fake/handler-direto do repo):
  • DOC-049/050/SYS-064: GET /portal/documentos filtra por portal_visible=True
    (documento NÃO publicado não aparece).
  • SYS-021/SYS-022: GET /portal/casos/{id} filtra movimentações por
    portal_visible=True (movimentação interna não aparece).
  • DOC-008/009/010: assinatura EICAR é barrada pelo escaner (422), mesmo com o
    antivírus externo desabilitado (default OFF).
  • DOC-022: upload local persiste o SHA-256 do conteúdo em Document.sha256.
"""
from __future__ import annotations

import hashlib
import io
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException
from starlette.datastructures import Headers
from fastapi import UploadFile

from app.models.user import UserRole


# ── FakeDB que compila e captura o SQL de cada execute ────────────────────────
class _Rows:
    def __init__(self, items):
        self._items = list(items)

    def scalars(self):
        return self

    def all(self):
        return list(self._items)

    def scalar_one_or_none(self):
        return self._items[0] if self._items else None

    def scalar(self):
        return self._items[0] if self._items else 0

    def mappings(self):
        return self

    def first(self):
        return self._items[0] if self._items else None


class _FakeDB:
    """Captura o SQL compilado de cada execute e devolve resultados roteados por
    tabela. Prova que os filtros de publicação estão na query (o filtro real é
    aplicado pelo Postgres; aqui garantimos que ele existe e é aplicado)."""

    def __init__(self, case_obj=None):
        self.sqls: list[str] = []
        self._case = case_obj

    async def execute(self, stmt, *a, **k):
        sql = str(stmt)
        self.sqls.append(sql)
        if "case_movimentos" in sql:
            return _Rows([])            # nenhuma movimentação publicada
        if "deadlines" in sql:
            return _Rows([])
        if "FROM cases" in sql or "\ncases" in sql or "cases " in sql:
            return _Rows([self._case] if self._case else [])
        return _Rows([])                # documents etc.

    def add(self, _obj):
        pass

    async def commit(self):
        return None


def _cliente() -> SimpleNamespace:
    return SimpleNamespace(
        id="u-cli", role=UserRole.cliente_externo, client_id="cli-1",
        email="cli@x.com", nome="Cliente",
    )


# ── DOC-049/050/SYS-064 — documento não publicado não aparece no Portal ───────
async def test_portal_documentos_filtra_por_portal_visible():
    from app.routers.portal import documentos

    db = _FakeDB()
    out = await documentos(db=db, cu=_cliente())

    assert out == {"data": []}                       # nada publicado → vazio
    assert len(db.sqls) == 1
    where = db.sqls[0].split("WHERE", 1)[1]
    assert "portal_visible" in where                 # o filtro está no WHERE
    # A confidencialidade NÃO é mais usada como se fosse publicação (fora do WHERE).
    assert "confidencialidade" not in where


# ── SYS-021/SYS-022 — movimentação interna não aparece no Portal ──────────────
async def test_portal_caso_detalhe_filtra_movimentos_por_portal_visible():
    from app.routers.portal import caso_detalhe

    case_obj = SimpleNamespace(
        id="caso-1", numero_interno="DPT-2026-0001", titulo="Caso",
        status="ativo", numero_processo="123", comarca="BH", vara="1a",
        client_id="cli-1", deleted_at=None,
    )
    db = _FakeDB(case_obj=case_obj)
    out = await caso_detalhe(case_id="caso-1", db=db, cu=_cliente())

    assert out["andamentos"] == []                   # nenhuma interna vaza
    mov_sql = next(s for s in db.sqls if "case_movimentos" in s)
    assert "portal_visible" in mov_sql               # filtro fail-closed presente


# ── DOC-008/009/010 — EICAR barrado pelo escaner (mesmo com antivírus OFF) ─────
async def test_eicar_barrado_pelo_escaner(monkeypatch):
    from app.services import malware_scan
    from app.routers.documents import _escanear_malware

    # Garante o cenário default (antivírus externo desabilitado).
    monkeypatch.delenv("MALWARE_SCAN_ENABLED", raising=False)

    eicar = (
        b"X5O!P%@AP[4\\PZX54(P^)7CC)7}"
        b"$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    )
    # Serviço puro levanta ArquivoInfectadoError.
    with pytest.raises(malware_scan.ArquivoInfectadoError):
        await malware_scan.escanear(eicar, "virus.pdf")

    # Helper do router traduz para HTTP 422 (fail-closed).
    with pytest.raises(HTTPException) as exc:
        await _escanear_malware(eicar, "virus.pdf")
    assert exc.value.status_code == 422

    # Conteúdo limpo passa sem erro.
    await _escanear_malware(b"%PDF-1.4 conteudo limpo", "ok.pdf")


# ── DOC-022 — upload local persiste SHA-256 em Document.sha256 ─────────────────
async def test_upload_local_persiste_sha256(monkeypatch, tmp_path):
    from app.routers import documents

    conteudo = b"%PDF-1.4 documento de teste para hash"
    esperado = hashlib.sha256(conteudo).hexdigest()

    monkeypatch.setattr(documents, "_validar_conteudo",
                        lambda ext, c: "application/pdf")
    monkeypatch.setattr(documents, "extrair_texto", lambda *a, **k: "")

    async def _noop_audit(*a, **k):
        return None
    monkeypatch.setattr(documents, "criar_audit_log", _noop_audit)
    monkeypatch.setattr(documents.settings, "UPLOAD_DIR", str(tmp_path))

    capturado: list = []

    class _DB:
        def add(self, obj):
            capturado.append(obj)

        async def commit(self):
            return None

    upload_file = UploadFile(
        file=io.BytesIO(conteudo), filename="doc.pdf",
        headers=Headers({"content-type": "application/pdf"}),
    )
    cu = SimpleNamespace(id="u1", role=SimpleNamespace(value="advogado"))

    resp = await documents.upload(
        background_tasks=BackgroundTasks(),
        file=upload_file, titulo="Teste",
        tipo=None, confidencialidade="normal", case_id=None, client_id=None,
        db=_DB(), cu=cu,
    )

    docs = [o for o in capturado if isinstance(o, documents.Document)]
    assert len(docs) == 1
    assert docs[0].sha256 == esperado
    assert docs[0].portal_visible in (False, None)   # nunca nasce publicado
    assert resp["id"] == docs[0].id
