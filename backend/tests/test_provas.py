"""Gestão de Provas por caso — /casos/{case_id}/provas.

Sem Postgres real (padrão test_sociedades_cliente.py / test_ownership.py):
handlers chamados diretamente com fake de sessão. Cobre: criação + ordenação,
vínculo a documento de OUTRO caso rejeitado, acesso negado a caso alheio,
soft delete, e o HTML do Documento Único de Anexos (anti-injeção + numeração).
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.models.audit_log import AuditLog
from app.models.case import Case
from app.models.document import Document
from app.models.prova import Prova, TipoProva
from app.models.user import User, UserRole
from app.schemas.prova import ProvaCreate


# ── Fakes (sem banco) ─────────────────────────────────────────────────────────

class _Res:
    def __init__(self, val):
        self._val = val

    def scalar_one_or_none(self):
        return self._val

    def scalar(self):
        return self._val

    def all(self):
        return self._val if isinstance(self._val, list) else []


class _FakeDB:
    """Sessão fake: fila de resultados para execute(); registra add/commit."""

    def __init__(self, resultados: list):
        self._resultados = list(resultados)
        self.added: list = []
        self.commits = 0

    async def execute(self, *a, **k):
        return _Res(self._resultados.pop(0))

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


def _user(role: UserRole, uid: str = "u1") -> User:
    return User(id=uid, role=role)


def _case(**kw) -> Case:
    base = dict(id="case1", titulo="Ação de Cobrança", client_id="cli1",
                area="civil", numero_processo=None, numero_interno="DPT-2026-0001",
                advogado_responsavel_id=None, advogado_auxiliar_id=None,
                deleted_at=None)
    base.update(kw)
    return Case(**base)


def _prova(**kw) -> Prova:
    base = dict(id="p1", case_id="case1", tipo="documental", titulo="Prova",
                descricao=None, document_id=None, tese_id=None,
                fato_probando=None, ordem=0, deleted_at=None, created_at=None)
    base.update(kw)
    return Prova(**base)


def _document(**kw) -> Document:
    from app.models.document import DocConfidencialidade
    base = dict(id="d1", case_id="case1", titulo="Contrato.pdf", deleted_at=None,
                confidencialidade=DocConfidencialidade.confidencial)
    base.update(kw)
    return Document(**base)


# ── Rotas montadas ────────────────────────────────────────────────────────────

def test_rotas_montadas_em_main():
    from app.main import app
    paths = {getattr(r, "path", "") for r in app.routes}
    assert any(p.endswith("/casos/{case_id}/provas") for p in paths)
    assert any(p.endswith("/casos/{case_id}/provas/{prova_id}") for p in paths)
    assert any(p.endswith("/casos/{case_id}/provas/documento-unico") for p in paths)
    assert any(p.endswith("/casos/{case_id}/provas/documento-unico/{arquivo_id}/download")
               for p in paths)


# ── Criação ───────────────────────────────────────────────────────────────────

async def test_criacao_prova():
    from app.routers.provas import criar_prova

    db = _FakeDB([_case()])  # gestão: só a query do caso (verificar_acesso_caso)
    out = await criar_prova(
        case_id="case1",
        payload=ProvaCreate(titulo="Contrato assinado", tipo=TipoProva.documental,
                            fato_probando="Existência do vínculo", ordem=2),
        db=db, cu=_user(UserRole.socio),
    )
    assert out["titulo"] == "Contrato assinado"
    assert out["tipo"] == "documental"
    assert out["ordem"] == 2
    provas = [o for o in db.added if isinstance(o, Prova)]
    assert len(provas) == 1 and provas[0].case_id == "case1"
    assert provas[0].created_by == "u1"
    assert any(isinstance(o, AuditLog) and o.entidade == "provas" and o.acao == "CREATE"
               for o in db.added)
    assert db.commits == 1


async def test_vinculo_documento_de_outro_caso_rejeitado():
    from app.routers.provas import criar_prova

    # caso1 acessível (gestão); documento existe mas é de OUTRO caso.
    db = _FakeDB([_case(), _document(case_id="caso-alheio")])
    with pytest.raises(HTTPException) as exc:
        await criar_prova(
            case_id="case1",
            payload=ProvaCreate(titulo="Prova", document_id="d1"),
            db=db, cu=_user(UserRole.socio),
        )
    assert exc.value.status_code == 400
    # Nada persistido quando o vínculo é inválido.
    assert [o for o in db.added if isinstance(o, Prova)] == []


# ── Autorização ───────────────────────────────────────────────────────────────

async def test_acesso_negado_a_caso_alheio_403():
    from app.routers.provas import listar_provas

    # advogado u1 não é responsável nem auxiliar do caso (ambos preenchidos).
    db = _FakeDB([_case(advogado_responsavel_id="outro",
                        advogado_auxiliar_id="outro2")])
    with pytest.raises(HTTPException) as exc:
        await listar_provas(case_id="case1", db=db, cu=_user(UserRole.advogado, "u1"))
    assert exc.value.status_code == 403


async def test_caso_inexistente_404():
    from app.routers.provas import listar_provas

    db = _FakeDB([None])
    with pytest.raises(HTTPException) as exc:
        await listar_provas(case_id="nao-existe", db=db, cu=_user(UserRole.socio))
    assert exc.value.status_code == 404


# ── Listagem + ordenação + nomes vinculados ───────────────────────────────────

async def test_listagem_ordenada_com_nomes_vinculados():
    from app.routers.provas import listar_provas

    rows = [
        (_prova(id="p1", ordem=1, document_id="d1"), "Contrato.pdf", None),
        (_prova(id="p2", ordem=2, tese_id="t1"), None, "Tese da prescrição"),
    ]
    db = _FakeDB([_case(), rows])
    out = await listar_provas(case_id="case1", db=db, cu=_user(UserRole.socio))
    assert out["total"] == 2
    assert [d["ordem"] for d in out["data"]] == [1, 2]
    assert out["data"][0]["documento_nome"] == "Contrato.pdf"
    assert out["data"][0]["tese_titulo"] is None
    assert out["data"][1]["tese_titulo"] == "Tese da prescrição"


# ── Soft delete ───────────────────────────────────────────────────────────────

async def test_soft_delete_marca_deleted_at():
    from app.routers.provas import remover_prova

    prova = _prova(id="p1")
    db = _FakeDB([_case(), prova])
    out = await remover_prova(case_id="case1", prova_id="p1", db=db,
                              cu=_user(UserRole.socio))
    assert "removida" in out.detail
    assert prova.deleted_at is not None  # soft delete: some da lista (WHERE deleted_at IS NULL)
    assert any(isinstance(o, AuditLog) and o.acao == "DELETE" and o.entidade == "provas"
               for o in db.added)
    assert db.commits == 1


async def test_delete_prova_de_outro_caso_404():
    from app.routers.provas import remover_prova

    # caso acessível, mas a prova não pertence a ele (_carregar_prova → None).
    db = _FakeDB([_case(), None])
    with pytest.raises(HTTPException) as exc:
        await remover_prova(case_id="case1", prova_id="p-alheia", db=db,
                            cu=_user(UserRole.socio))
    assert exc.value.status_code == 404


# ── Documento Único de Anexos (HTML) ──────────────────────────────────────────

def test_romano():
    from app.routers.provas import _romano
    assert _romano(1) == "I"
    assert _romano(4) == "IV"
    assert _romano(9) == "IX"
    assert _romano(14) == "XIV"


def test_documento_unico_html_escapa_payload_e_numera_anexos():
    from app.routers.provas import _html_documento_unico

    payload = "<script>alert('xss')</script>"
    html = _html_documento_unico(
        {"titulo": payload, "numero": "001", "cliente": payload, "ramo": "civil"},
        [
            {"tipo": "documental", "titulo": payload, "fato_probando": payload,
             "descricao": None, "documento_nome": None, "tese_titulo": None},
            {"tipo": "pericial", "titulo": "Laudo técnico", "fato_probando": "Nexo causal",
             "descricao": None, "documento_nome": "laudo.pdf", "tese_titulo": "Tese X"},
        ],
    )
    # Anti-injeção: o payload nunca aparece cru; entra escapado.
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html
    # Sumário numerado (Anexo I, II) + uma seção por prova.
    assert "Anexo I" in html and "Anexo II" in html
    assert "Sumário de Anexos" in html
    assert "Laudo técnico" in html
