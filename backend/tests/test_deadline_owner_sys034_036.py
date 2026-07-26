"""Testes de REGRESSÃO dos endurecimentos SYS-034 / SYS-035 / SYS-036.

Fecha a brecha de prazos AVULSOS (case_id=NULL) visíveis/mutáveis por qualquer
usuário interno e o lançamento de prazo FATAL confirmado por perfil operacional.

  SYS-034  criação ...... secretaria/estagiário lançam só RASCUNHO (confirmado=
                          False); advogado+ lança prazo confirmado. created_by/
                          owner_id gravados.
  SYS-035  PATCH/confirmar/ciência ... prazo avulso só muta por dono/criador/
                          responsável ou advogado+; CONFIRMAÇÃO exige advogado+.
  SYS-036  listagem ...... escopo de avulsos por dono (owner_id/created_by/
                          responsavel_id), não `case_id IS NULL` amplo.

Padrão do repo (test_hardening_ownership_2026_07.py): sem banco real — fake de
AsyncSession por arquivo + chamada direta do handler/gate.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.user import User, UserRole
from app.models.deadline import Deadline
from app.schemas.deadline import DeadlineCreate, DeadlineUpdate
from app.routers.deadlines import (
    _eh_advogado, _pode_mutar_prazo_avulso, _gate_mutacao_prazo,
    _filtro_escopo_prazos, criar, atualizar, confirmar, confirmar_ciencia,
)


# ── Fakes ──────────────────────────────────────────────────────────────────────

class _Res:
    def __init__(self, scalar_one=None):
        self._scalar_one = scalar_one

    def scalar_one_or_none(self):
        return self._scalar_one


class _FakeDB:
    """AsyncSession fake: devolve _Res em sequência, aceita add e simula o refresh
    aplicando os defaults de coluna que o Postgres preencheria (created_at, bools)
    — necessário p/ o DeadlineResponse.model_validate do handler não quebrar."""

    def __init__(self, results=()):
        self._results = list(results)
        self.added = []
        self.committed = False

    async def execute(self, stmt, *a, **k):
        return self._results.pop(0) if self._results else _Res()

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    async def refresh(self, obj):
        # Aplica os defaults de coluna que o Postgres preencheria no INSERT.
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.now(timezone.utc)
        if getattr(obj, "status", None) is None:
            obj.status = "pendente"
        if getattr(obj, "ciencia_confirmada", None) is None:
            obj.ciencia_confirmada = False
        if getattr(obj, "confirmado", None) is None:
            obj.confirmado = True


def _user(role: UserRole, uid: str = "u1") -> User:
    return User(id=uid, role=role)


def _prazo_avulso(dono: str) -> Deadline:
    """Prazo AVULSO (sem caso) de `dono` — owner/criador/responsável = dono."""
    return Deadline(
        id="d1", titulo="Contestacao", tipo="processual", prioridade="alta",
        status="pendente", data_prazo=date(2026, 8, 1), case_id=None,
        responsavel_id=dono, owner_id=dono, created_by=dono, confirmado=True,
    )


@pytest.fixture(autouse=True)
def _sem_audit(monkeypatch):
    async def _noop(*a, **k):
        return None
    monkeypatch.setattr("app.routers.deadlines.criar_audit_log", _noop)


def _sql(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": False}))


# ── SYS-034: criação — rascunho vs prazo fatal confirmado ───────────────────────

async def test_SYS034_secretaria_cria_rascunho_nao_confirmado():
    """Perfil operacional (secretaria) lança prazo, mas ele NASCE como rascunho
    (confirmado=False) — nunca prazo fatal confirmado."""
    db = _FakeDB()
    payload = DeadlineCreate(titulo="Prazo X", data_prazo=date(2026, 8, 1))
    out = await criar(payload, db, _user(UserRole.secretaria, "sec1"))
    assert out.confirmado is False
    d = db.added[0]
    assert d.confirmado is False
    assert d.created_by == "sec1"        # autoria gravada
    assert d.owner_id == "sec1"          # dono = responsável (default = criador)
    assert db.committed is True


async def test_SYS034_estagiario_cria_rascunho_nao_confirmado():
    db = _FakeDB()
    payload = DeadlineCreate(titulo="Prazo X", data_prazo=date(2026, 8, 1))
    out = await criar(payload, db, _user(UserRole.estagiario, "est1"))
    assert out.confirmado is False


async def test_SYS034_advogado_cria_prazo_confirmado():
    """Advogado+ lança prazo fatal já CONFIRMADO."""
    db = _FakeDB()
    payload = DeadlineCreate(titulo="Prazo X", data_prazo=date(2026, 8, 1))
    out = await criar(payload, db, _user(UserRole.advogado, "adv1"))
    assert out.confirmado is True
    d = db.added[0]
    assert d.created_by == "adv1" and d.owner_id == "adv1"


async def test_SYS034_owner_id_segue_responsavel_id_informado():
    """owner_id acompanha o responsável jurídico informado no payload."""
    db = _FakeDB()
    payload = DeadlineCreate(titulo="Prazo X", data_prazo=date(2026, 8, 1),
                             responsavel_id="adv-resp")
    await criar(payload, db, _user(UserRole.advogado, "adv1"))
    d = db.added[0]
    assert d.owner_id == "adv-resp" and d.responsavel_id == "adv-resp"
    assert d.created_by == "adv1"        # autoria continua sendo quem lançou


# ── SYS-035: mutação/confirmação de prazo avulso ────────────────────────────────

def test_SYS035_gate_avulso_dono_passa():
    d = _prazo_avulso("A")
    assert _pode_mutar_prazo_avulso(_user(UserRole.secretaria, "A"), d) is True


def test_SYS035_gate_avulso_terceiro_operacional_barrado():
    """Prazo avulso de A NÃO é mutável por B (secretaria alheia)."""
    d = _prazo_avulso("A")
    assert _pode_mutar_prazo_avulso(_user(UserRole.secretaria, "B"), d) is False


def test_SYS035_gate_avulso_advogado_alheio_passa():
    """Advogado+ pode alterar prazo avulso mesmo sem ser o dono (piso jurídico)."""
    d = _prazo_avulso("A")
    assert _pode_mutar_prazo_avulso(_user(UserRole.advogado, "B"), d) is True


def test_SYS035_gate_mutacao_avulso_terceiro_403():
    d = _prazo_avulso("A")
    with pytest.raises(HTTPException) as exc:
        _gate_mutacao_prazo(_user(UserRole.secretaria, "B"), d)
    assert exc.value.status_code == 403


async def test_SYS035_patch_avulso_de_A_por_B_403():
    """PATCH em prazo avulso de A por B (secretaria) → 403, sem gravar."""
    db = _FakeDB([_Res(scalar_one=_prazo_avulso("A"))])
    with pytest.raises(HTTPException) as exc:
        await atualizar("d1", DeadlineUpdate(titulo="Sequestrado"), db,
                        _user(UserRole.secretaria, "B"))
    assert exc.value.status_code == 403
    assert db.committed is False


async def test_SYS035_patch_avulso_pelo_dono_ok():
    """O dono (criador) do prazo avulso continua podendo editar (sem lockout)."""
    db = _FakeDB([_Res(scalar_one=_prazo_avulso("A"))])
    out = await atualizar("d1", DeadlineUpdate(titulo="Novo"), db,
                          _user(UserRole.secretaria, "A"))
    assert out.titulo == "Novo"
    assert db.committed is True


async def test_SYS035_confirmar_por_secretaria_403():
    """Confirmação de prazo fatal exige advogado+ — secretaria (mesmo dona) → 403,
    antes de qualquer carga/escrita."""
    db = _FakeDB([_Res(scalar_one=_prazo_avulso("A"))])
    with pytest.raises(HTTPException) as exc:
        await confirmar("d1", db, _user(UserRole.secretaria, "A"))
    assert exc.value.status_code == 403
    assert db.committed is False


async def test_SYS035_confirmar_por_advogado_ok():
    d = _prazo_avulso("A")
    d.confirmado = False  # rascunho lançado por perfil operacional
    db = _FakeDB([_Res(scalar_one=d)])
    out = await confirmar("d1", db, _user(UserRole.advogado, "adv1"))
    assert out.confirmado is True
    assert db.committed is True


async def test_SYS035_ciencia_avulso_de_A_por_B_403():
    db = _FakeDB([_Res(scalar_one=_prazo_avulso("A"))])
    with pytest.raises(HTTPException) as exc:
        await confirmar_ciencia("d1", db, _user(UserRole.secretaria, "B"))
    assert exc.value.status_code == 403
    assert db.committed is False


# ── SYS-036: escopo de listagem por dono ────────────────────────────────────────

def test_SYS036_avulsos_escopados_por_dono_no_sql():
    """O ramo de avulsos deixou de ser `case_id IS NULL` amplo: agora casa
    owner_id/created_by/responsavel_id do usuário."""
    filtrada = _filtro_escopo_prazos(select(Deadline), _user(UserRole.advogado, "u1"))
    sql = _sql(filtrada)
    assert "owner_id" in sql
    assert "created_by" in sql
    assert "IS NULL" in sql            # ainda restrito a avulsos
    assert "cases.id" in sql           # e casos próprios preservados


def test_SYS036_gestao_ve_tudo():
    q = select(Deadline)
    assert _filtro_escopo_prazos(q, _user(UserRole.socio, "u1")) is q


def test_SYS036_eh_advogado_niveis():
    assert _eh_advogado(_user(UserRole.advogado, "u1")) is True
    assert _eh_advogado(_user(UserRole.socio, "u1")) is True
    assert _eh_advogado(_user(UserRole.secretaria, "u1")) is False
    assert _eh_advogado(_user(UserRole.estagiario, "u1")) is False
