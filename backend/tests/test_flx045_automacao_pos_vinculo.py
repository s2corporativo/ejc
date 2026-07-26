"""FLX-045 — automação após vínculo de documentos (sem Postgres real).

Caso aberto com `aguardar_documentos=True` adia triagem e kit; os pontos de
vínculo da fonte re-agendam ambos em background, de forma idempotente:
  - POST /documents/upload (com case_id);
  - POST /entrada-universal/{batch_id}/vincular-caso;
  - POST /cases/{id}/aplicar-extracao (apenas o apply REAL re-agenda a triagem;
    dry_run não agenda nada).

Padrão test_kit_documental.py / test_provas.py: handlers chamados diretamente
com fakes de sessão e BackgroundTasks. O lado da CRIAÇÃO (adiar na abertura)
é coberto em test_kit_documental.py.
"""
from __future__ import annotations

import io
from types import SimpleNamespace

from fastapi import UploadFile
from starlette.datastructures import Headers

from app.models.case import Case
from app.models.user import User, UserRole


# ── Fakes (sem banco) ─────────────────────────────────────────────────────────

class _Res:
    def __init__(self, val):
        self._val = val

    def scalar_one_or_none(self):
        return self._val

    def scalar(self):
        return self._val

    def scalars(self):
        return self

    def all(self):
        return self._val if isinstance(self._val, list) else []


class _FakeDB:
    def __init__(self, resultados: list):
        self._resultados = list(resultados)
        self.added: list = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, *a, **k):
        return _Res(self._resultados.pop(0))

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        pass

    async def rollback(self):
        self.rollbacks += 1


class _FakeBackground:
    def __init__(self):
        self.tasks: list = []

    def add_task(self, fn, *args, **kwargs):
        self.tasks.append((fn, args, kwargs))


def _user(uid: str = "u1") -> User:
    return User(id=uid, role=UserRole.advogado, full_name="Dra. Fulana")


def _case(**kw) -> Case:
    base = dict(id="case1", titulo="Guarda dos Filhos", client_id="cli1",
                area="familia", numero_processo=None, numero_interno="DPT-2026-0001",
                advogado_responsavel_id="u1", advogado_auxiliar_id=None,
                deleted_at=None)
    base.update(kw)
    return Case(**base)


# ── POST /documents/upload com case_id re-agenda triagem + kit ───────────────

async def test_upload_com_case_id_reagenda_triagem_e_kit(monkeypatch, tmp_path):
    import app.routers.documents as documents

    caso = _case()

    async def _acesso_ok(db, cu, case_id):
        return caso

    monkeypatch.setattr(documents, "verificar_acesso_caso", _acesso_ok)
    monkeypatch.setattr(documents.settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(documents, "_validar_conteudo",
                        lambda ext, conteudo: "application/pdf")
    monkeypatch.setattr(documents, "extrair_texto", lambda *a, **k: None)

    # execute #1: versionamento (doc existente com mesmo título) → None.
    db = _FakeDB([None])
    bg = _FakeBackground()
    arquivo = UploadFile(
        file=io.BytesIO(b"%PDF-1.4 conteudo"), filename="doc.pdf",
        headers=Headers({"content-type": "application/pdf"}),
    )

    resp = await documents.upload(
        background_tasks=bg, file=arquivo, titulo="Doc importado", tipo=None,
        confidencialidade="normal", case_id="case1", client_id=None,
        db=db, cu=_user(),
    )

    assert resp["detail"] == "Documento enviado"
    tarefas = {t[0]: t[1] for t in bg.tasks}
    assert tarefas.get(documents.triagem_caso) == ("case1",)
    assert tarefas.get(documents.gerar_documentos_iniciais_auto) == ("case1", "u1")


async def test_upload_sem_case_id_nao_reagenda(monkeypatch, tmp_path):
    import app.routers.documents as documents

    monkeypatch.setattr(documents.settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(documents, "_validar_conteudo",
                        lambda ext, conteudo: "application/pdf")
    monkeypatch.setattr(documents, "extrair_texto", lambda *a, **k: None)

    db = _FakeDB([])  # sem case_id/client_id: nenhum execute
    bg = _FakeBackground()
    arquivo = UploadFile(
        file=io.BytesIO(b"%PDF-1.4 conteudo"), filename="doc.pdf",
        headers=Headers({"content-type": "application/pdf"}),
    )

    await documents.upload(
        background_tasks=bg, file=arquivo, titulo="Doc avulso", tipo=None,
        confidencialidade="normal", case_id=None, client_id=None,
        db=db, cu=_user(),
    )

    assert bg.tasks == []  # documento órfão: nada a triagem/kit fazerem


# ── POST /entrada-universal/{batch}/vincular-caso re-agenda triagem + kit ────

async def test_vincular_lote_reagenda_triagem_e_kit(monkeypatch):
    import app.routers.entrada_universal_vinculo as vinc

    caso = _case()
    batch = SimpleNamespace(id="batch1", case_id=None, client_id=None)

    async def _batch_ok(db, cu, batch_id):
        return batch

    async def _acesso_ok(db, cu, case_id):
        return caso

    monkeypatch.setattr(vinc, "_acesso_batch", _batch_ok)
    monkeypatch.setattr(vinc, "verificar_acesso_caso", _acesso_ok)

    # execute #1: pares (itens do lote) → []; #2: docs existentes do caso → [].
    db = _FakeDB([[], []])
    bg = _FakeBackground()

    resp = await vinc.vincular_lote_ao_caso(
        batch_id="batch1", req=vinc.VincularCasoRequest(case_id="case1"),
        background=bg, db=db, cu=_user(),
    )

    assert resp["ok"] is True and resp["case_id"] == "case1"
    assert db.commits == 1
    tarefas = {t[0]: t[1] for t in bg.tasks}
    assert tarefas.get(vinc.triagem_caso) == ("case1",)
    assert tarefas.get(vinc.gerar_documentos_iniciais_auto) == ("case1", "u1")


# ── POST /cases/{id}/aplicar-extracao: apply real re-agenda; dry_run não ─────

async def test_aplicar_extracao_real_reagenda_triagem():
    from app.routers import cases as cases_router

    # execute #1: caso; #2: partes existentes → [].
    db = _FakeDB([_case(), []])
    bg = _FakeBackground()

    resp = await cases_router.aplicar_extracao(
        case_id="case1", payload=cases_router.AplicarExtracaoReq(),
        background=bg, dry_run=False, db=db, cu=_user(),
    )

    assert resp["aplicado"] is True
    fns = [t[0] for t in bg.tasks]
    assert cases_router.triagem_caso in fns
    task = next(t for t in bg.tasks if t[0] is cases_router.triagem_caso)
    assert task[1] == ("case1",)


async def test_aplicar_extracao_dry_run_nao_reagenda():
    from app.routers import cases as cases_router

    db = _FakeDB([_case(), []])
    bg = _FakeBackground()

    resp = await cases_router.aplicar_extracao(
        case_id="case1", payload=cases_router.AplicarExtracaoReq(),
        background=bg, dry_run=True, db=db, cu=_user(),
    )

    assert resp["aplicado"] is False and resp["dry_run"] is True
    assert db.rollbacks == 1
    assert bg.tasks == []  # preview: nenhuma automação agendada
