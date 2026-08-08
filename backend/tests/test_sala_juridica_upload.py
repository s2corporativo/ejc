"""Upload de anexos da Sala Jurídica (achado F2 — consolidação de ingestão).

`anexar_documentos` (routers/legal_chat.py) passou a usar o mesmo
`upload_lote_service.processar_lote` do Raio-X em vez de duplicar a validação
byte-a-byte. Cobre:
  (a) lote válido grava o anexo em disco e no banco, preservando a extração
      inline (diferença legítima do Raio-X, que processa em fila);
  (b) teto de arquivos por lote responde 422 (mesmo contrato de antes);
  (c) achado corrigido nesta consolidação: o endpoint nunca gravava audit log
      de upload, ao contrário do irmão em raio_x.py — agora grava.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.models.legal_chat import LegalChatAttachment, LegalChatSession


def _user():
    return SimpleNamespace(id="u1", role=SimpleNamespace(value="advogado"))


def _sessao(frozen: bool = False) -> LegalChatSession:
    sessao = LegalChatSession(
        id="s1",
        titulo="Sessão fictícia",
        status="em_analise",
        created_by="u1",
        advogado_responsavel_id="u1",
        workspace_texto="",
        workspace_versao=0,
        custo_ia_total=0,
    )
    sessao.frozen_at = "2026-01-01T00:00:00+00:00" if frozen else None
    return sessao


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDB:
    """Sessão fake para o router: db.get devolve a sessão; execute devolve
    hashes existentes (vazio, sem duplicidade prévia)."""

    def __init__(self, sessao: LegalChatSession):
        self.sessao = sessao
        self.added: list = []
        self.commits = 0
        self.audit_calls: list = []

    async def get(self, model, obj_id):
        return self.sessao if obj_id == self.sessao.id else None

    async def execute(self, stmt):
        return _FakeResult([])

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def flush(self):
        pass

    async def refresh(self, obj):
        pass


def _app(sessao: LegalChatSession) -> tuple[FastAPI, _FakeDB]:
    from app.core.database import get_db
    from app.core.security import get_current_user
    from app.routers.legal_chat import router

    app = FastAPI()
    app.include_router(router)
    db = _FakeDB(sessao)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = _user
    return app, db


def test_upload_grava_anexo_e_extrai_inline(monkeypatch, tmp_path):
    """(a) Lote válido: anexo em disco + LegalChatAttachment no banco, com
    resultado_analise preenchido (extração INLINE, diferente do Raio-X)."""
    st = get_settings()
    monkeypatch.setattr(st, "UPLOAD_DIR", str(tmp_path), raising=False)

    async def fake_extrair(*args, **kwargs):
        return {"ok": True, "_texto_sanitizado": "texto extraído"}

    from app.services import documento_service
    monkeypatch.setattr(documento_service, "extrair_e_analisar", fake_extrair)

    audit_calls: list = []

    async def fake_audit(db, **kwargs):
        audit_calls.append(kwargs)

    import app.routers.legal_chat as legal_chat_router
    monkeypatch.setattr(legal_chat_router, "criar_audit_log", fake_audit)

    sessao = _sessao()
    app, db = _app(sessao)
    with TestClient(app) as client:
        resp = client.post(
            "/sala-juridica/s1/anexos",
            files=[("files", ("peticao.txt", b"Conteudo ficticio de peticao.", "text/plain"))],
        )
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["duplicados"] == []
    assert corpo["erros"] == []
    assert len(corpo["anexados"]) == 1

    anexos = [obj for obj in db.added if isinstance(obj, LegalChatAttachment)]
    assert len(anexos) == 1
    assert anexos[0].resultado_analise["ok"] is True
    assert (Path(str(tmp_path)) / anexos[0].filepath).exists()

    # (c) achado corrigido: agora grava audit log de upload (antes não gravava).
    assert len(audit_calls) == 1
    assert audit_calls[0]["acao"] == "UPLOAD"
    assert audit_calls[0]["entidade"] == "legal_chat_sessions"
    assert audit_calls[0]["registro_id"] == "s1"


def test_upload_acima_do_teto_da_422(monkeypatch, tmp_path):
    """(b) Mesmo contrato de antes: acima do teto de arquivos por lote → 422."""
    st = get_settings()
    monkeypatch.setattr(st, "UPLOAD_DIR", str(tmp_path), raising=False)

    from app.routers import legal_chat as legal_chat_router

    sessao = _sessao()
    app, db = _app(sessao)
    arquivos = [
        ("files", (f"doc{i}.txt", b"conteudo", "text/plain"))
        for i in range(legal_chat_router.MAX_ARQUIVOS + 1)
    ]
    with TestClient(app) as client:
        resp = client.post("/sala-juridica/s1/anexos", files=arquivos)
    assert resp.status_code == 422
    assert db.added == []


def test_upload_em_sessao_congelada_da_409(tmp_path):
    """Sessão já convertida (congelada) recusa novo anexo — inalterado pela
    consolidação (checagem continua fora de processar_lote, específica do
    módulo)."""
    st = get_settings()
    st.UPLOAD_DIR = str(tmp_path)

    sessao = _sessao(frozen=True)
    app, db = _app(sessao)
    with TestClient(app) as client:
        resp = client.post(
            "/sala-juridica/s1/anexos",
            files=[("files", ("peticao.txt", b"conteudo", "text/plain"))],
        )
    assert resp.status_code == 409
    assert db.added == []
