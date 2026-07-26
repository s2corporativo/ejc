"""Guardas do BPM Workflow (auditoria FLX-062 / FLX-065).

Cobre, sem depender de Postgres (fakes no padrão de test_legal_doc_protocolo.py):

  FLX-062 — avancar_etapa:
    - etapa de OUTRO template → 422 (antes: qualquer etapa era aceita);
    - etapa inexistente → 404;
    - avançar para a própria etapa atual → 422;
    - pular etapa obrigatória nunca visitada → 422;
    - etapa_atual nula (ou órfã) tratada como início do fluxo: pular
      obrigatória anterior → 422; próxima sem obrigatórias antes → 200;
    - obrigatória intermediária JÁ visitada → avanço permitido;
    - retroceder (ordem menor) → permitido.

  FLX-065 — caso encerrado/arquivado não movimenta workflow (409, espelha o
  orquestrador) em iniciar/aplicar-padrão/avancar/concluir; e concluir exige
  toda etapa obrigatória visitada (histórico ∪ etapa atual) → 422 senão.

Dados 100% fictícios.
"""
from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.workflow import CaseWorkflow, WorkflowEtapa, WorkflowStatus
from app.routers import workflow as workflow_router


# ── Fakes ─────────────────────────────────────────────────────────────────────

class _Res:
    def __init__(self, one=None, many=None):
        self._one = one
        self._many = list(many) if many is not None else ([] if one is None else [one])

    def scalar_one_or_none(self):
        return self._one

    def scalars(self):
        return self

    def first(self):
        return self._many[0] if self._many else None

    def all(self):
        return list(self._many)


class _FakeDB:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.added = []
        self.committed = 0

    async def execute(self, stmt, *a, **k):
        return self.results.pop(0) if self.results else _Res()

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def commit(self):
        self.committed += 1

    async def refresh(self, obj):
        pass


def _etapa(id_: str, ordem: int, obrigatoria: bool = True,
           template_id: str = "tpl-1") -> WorkflowEtapa:
    return WorkflowEtapa(
        id=id_, template_id=template_id, nome=f"Etapa {ordem}",
        ordem=ordem, obrigatoria=obrigatoria,
    )


def _cw(etapa_atual: str | None = "e1") -> CaseWorkflow:
    return CaseWorkflow(
        id="cw-1", case_id="caso-1", template_id="tpl-1",
        etapa_atual_id=etapa_atual, status=WorkflowStatus.ativo,
    )


def _liberar_caso(monkeypatch, status: str = "ativo"):
    """Ownership liberado no fake; o caso volta com o status pedido."""
    async def _acesso(db, cu, case_id):
        return SimpleNamespace(id=case_id, status=status)

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(workflow_router, "verificar_acesso_caso", _acesso)
    monkeypatch.setattr(workflow_router, "registrar_acao", _noop)


def _montar(db: _FakeDB, role: str = "advogado") -> TestClient:
    app = FastAPI()
    app.include_router(workflow_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id="u1", role=SimpleNamespace(value=role)
    )
    return TestClient(app)


# ── FLX-062: escopo de template ao avançar ────────────────────────────────────

def test_avancar_etapa_de_outro_template_422(monkeypatch):
    """Etapa que existe mas pertence a OUTRO template → 422, nada gravado."""
    _liberar_caso(monkeypatch)
    db = _FakeDB(results=[
        _Res(one=_cw()),          # workflow ativo do caso
        _Res(one=None),           # busca escopada (id + template) não acha
        _Res(one="e-alheia"),     # ...mas a etapa existe em outro template
    ])
    r = _montar(db).post("/workflow/casos/caso-1/avancar",
                         json={"proxima_etapa_id": "e-alheia"})
    assert r.status_code == 422, r.text
    assert "não pertence ao template" in r.json()["detail"]
    assert db.committed == 0 and not db.added


def test_avancar_etapa_inexistente_404(monkeypatch):
    _liberar_caso(monkeypatch)
    db = _FakeDB(results=[_Res(one=_cw()), _Res(one=None), _Res(one=None)])
    r = _montar(db).post("/workflow/casos/caso-1/avancar",
                         json={"proxima_etapa_id": "nao-existe"})
    assert r.status_code == 404
    assert db.committed == 0


def test_avancar_para_propria_etapa_atual_422(monkeypatch):
    _liberar_caso(monkeypatch)
    db = _FakeDB(results=[
        _Res(one=_cw(etapa_atual="e2")),
        _Res(one=_etapa("e2", 2)),
    ])
    r = _montar(db).post("/workflow/casos/caso-1/avancar",
                         json={"proxima_etapa_id": "e2"})
    assert r.status_code == 422
    assert "já está nesta etapa" in r.json()["detail"]
    assert db.committed == 0


def test_avancar_pulando_obrigatoria_nao_visitada_422(monkeypatch):
    """e1 → e3 pulando e2 (obrigatória, nunca visitada) → 422."""
    _liberar_caso(monkeypatch)
    db = _FakeDB(results=[
        _Res(one=_cw(etapa_atual="e1")),
        _Res(one=_etapa("e3", 3)),                 # próxima (escopada)
        _Res(one=_etapa("e1", 1)),                 # etapa atual
        _Res(many=["e1"]),                         # histórico visitado
        _Res(many=[_etapa("e2", 2)]),              # obrigatórias intermediárias
    ])
    r = _montar(db).post("/workflow/casos/caso-1/avancar",
                         json={"proxima_etapa_id": "e3"})
    assert r.status_code == 422, r.text
    assert "obrigatória" in r.json()["detail"]
    assert "Etapa 2" in r.json()["detail"]
    assert db.committed == 0 and not db.added


def test_avancar_com_obrigatoria_intermediaria_ja_visitada_passa(monkeypatch):
    """e2 já cumprida no histórico: avanço e1→e3 é permitido."""
    _liberar_caso(monkeypatch)
    db = _FakeDB(results=[
        _Res(one=_cw(etapa_atual="e1")),
        _Res(one=_etapa("e3", 3)),
        _Res(one=_etapa("e1", 1)),
        _Res(many=["e1", "e2"]),                   # e2 já visitada
        _Res(many=[_etapa("e2", 2)]),
        _Res(one=None),                            # histórico aberto da atual
    ])
    r = _montar(db).post("/workflow/casos/caso-1/avancar",
                         json={"proxima_etapa_id": "e3"})
    assert r.status_code == 200, r.text
    assert r.json()["etapa_atual"]["id"] == "e3"
    assert db.committed == 1


def test_avancar_com_etapa_atual_nula_pulando_obrigatoria_422(monkeypatch):
    """etapa_atual_id nulo NÃO desliga a guarda: início do fluxo → toda
    obrigatória anterior à próxima precisa ter sido visitada."""
    _liberar_caso(monkeypatch)
    db = _FakeDB(results=[
        _Res(one=_cw(etapa_atual=None)),
        _Res(one=_etapa("e3", 3)),                 # próxima (escopada)
        _Res(many=[]),                             # histórico vazio
        _Res(many=[_etapa("e1", 1), _etapa("e2", 2)]),  # obrigatórias < 3
    ])
    r = _montar(db).post("/workflow/casos/caso-1/avancar",
                         json={"proxima_etapa_id": "e3"})
    assert r.status_code == 422, r.text
    assert "obrigatória" in r.json()["detail"]
    assert "Etapa 1" in r.json()["detail"]
    assert "Etapa 2" in r.json()["detail"]
    assert db.committed == 0 and not db.added


def test_avancar_com_etapa_atual_nula_para_primeira_etapa_passa(monkeypatch):
    """etapa_atual_id nulo + próxima sem obrigatórias anteriores → 200."""
    _liberar_caso(monkeypatch)
    db = _FakeDB(results=[
        _Res(one=_cw(etapa_atual=None)),
        _Res(one=_etapa("e1", 1)),                 # próxima = primeira
        _Res(many=[]),                             # histórico vazio
        _Res(many=[]),                             # nenhuma obrigatória < 1
        _Res(one=None),                            # histórico aberto da atual
    ])
    r = _montar(db).post("/workflow/casos/caso-1/avancar",
                         json={"proxima_etapa_id": "e1"})
    assert r.status_code == 200, r.text
    assert r.json()["etapa_atual"]["id"] == "e1"
    assert db.committed == 1


def test_retroceder_etapa_continua_permitido(monkeypatch):
    """Voltar para etapa de ordem MENOR não dispara checagem de obrigatórias."""
    _liberar_caso(monkeypatch)
    db = _FakeDB(results=[
        _Res(one=_cw(etapa_atual="e3")),
        _Res(one=_etapa("e1", 1)),                 # próxima (retrocesso)
        _Res(one=_etapa("e3", 3)),                 # etapa atual
        _Res(one=None),                            # histórico aberto da atual
    ])
    r = _montar(db).post("/workflow/casos/caso-1/avancar",
                         json={"proxima_etapa_id": "e1"})
    assert r.status_code == 200, r.text
    assert r.json()["etapa_atual"]["id"] == "e1"
    assert db.committed == 1


# ── FLX-065: caso encerrado/arquivado bloqueia mutação (409) ─────────────────

def test_mutacoes_em_caso_encerrado_ou_arquivado_409(monkeypatch):
    chamadas = (
        ("/workflow/casos/caso-1/iniciar", {"template_id": "tpl-1"}),
        ("/workflow/casos/caso-1/aplicar-padrao", None),
        ("/workflow/casos/caso-1/avancar", {"proxima_etapa_id": "e2"}),
        ("/workflow/casos/caso-1/concluir", None),
    )
    for status_caso in ("encerrado", "arquivado"):
        _liberar_caso(monkeypatch, status=status_caso)
        for url, payload in chamadas:
            db = _FakeDB()
            client = _montar(db)
            r = client.post(url, json=payload) if payload else client.post(url)
            assert r.status_code == 409, (status_caso, url, r.text)
            assert f"Caso {status_caso} — reabra o caso" in r.json()["detail"]
            assert db.committed == 0 and not db.added


def test_caso_encerrado_com_status_enum_409(monkeypatch):
    """Guarda usa getattr(status, 'value', status) — cobre status como enum."""
    async def _acesso(db, cu, case_id):
        return SimpleNamespace(
            id=case_id, status=SimpleNamespace(value="encerrado")
        )

    monkeypatch.setattr(workflow_router, "verificar_acesso_caso", _acesso)
    db = _FakeDB()
    r = _montar(db).post("/workflow/casos/caso-1/concluir")
    assert r.status_code == 409
    assert "encerrado" in r.json()["detail"]


# ── FLX-065: concluir exige obrigatórias visitadas ───────────────────────────

def test_concluir_com_obrigatoria_nao_visitada_422(monkeypatch):
    """e3 obrigatória nunca visitada (nem é a atual) → conclusão bloqueada."""
    _liberar_caso(monkeypatch)
    db = _FakeDB(results=[
        _Res(one=_cw(etapa_atual="e2")),
        _Res(many=["e1"]),                                     # histórico
        _Res(many=[_etapa("e1", 1), _etapa("e2", 2), _etapa("e3", 3)]),
    ])
    r = _montar(db).post("/workflow/casos/caso-1/concluir")
    assert r.status_code == 422, r.text
    assert "não pode ser concluído" in r.json()["detail"]
    assert "Etapa 3" in r.json()["detail"]
    assert db.committed == 0


def test_concluir_com_todas_obrigatorias_visitadas_passa(monkeypatch):
    """Histórico ∪ etapa atual cobre todas as obrigatórias → conclui."""
    _liberar_caso(monkeypatch)
    cw = _cw(etapa_atual="e2")
    db = _FakeDB(results=[
        _Res(one=cw),
        _Res(many=["e1"]),                                     # histórico
        _Res(many=[_etapa("e1", 1), _etapa("e2", 2)]),         # obrigatórias
        _Res(one=None),                                        # hist. aberto
    ])
    r = _montar(db).post("/workflow/casos/caso-1/concluir")
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "concluido"}
    assert cw.status == WorkflowStatus.concluido
    assert db.committed == 1
