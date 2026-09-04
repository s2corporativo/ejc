"""Testes de REGRESSÃO dos endurecimentos de RBAC/IDOR do PR #321.

Trava contra regressão os gates de ownership/segregação aplicados nos commits
ffb8bf3 (lote 1: deadlines, data_room, partner_withdrawals, ...) e d1fd24e
(lote 2: atendimentos, ...) e 665e9f1 (clients.PATCH, centro_custos).

Padrão do repo (test_ownership.py / *_dblevel.py): sem banco real — fakes de
`AsyncSession` por arquivo + chamada direta do handler/gate. Postgres NÃO é
requerido aqui (esses testes rodam sempre; os *_dblevel.py cobrem o nível SQL).

Mapa achado→teste:
  A1  clients.PATCH ...... write-IDOR de PII entre carteiras (gate _pode_ver_cliente)
  A2  centro_custos GET ... escopo de custos por casos próprios (não-gestão)
  A3  deadlines GET/CSV ... escopo de prazos por ownership (_filtro_escopo_prazos)
  B1  deadlines DELETE .... superadmin NÃO toma 403 (lockout); financeiro toma 403
  A4  data_room ........... gate de ownership da SALA (_gate_room → 404 alheia)
  A6  partner_withdrawals . segregação de funções (não aprova/paga a própria)
  D9a atendimentos ........ segregação de carteira (_pode_ver_atendimento)
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.models.user import User, UserRole


# ── Fakes de sessão (espelham _FakeDB/_Res de test_ownership.py) ────────────────

_UNSET = object()


class _Res:
    """Resultado configurável de db.execute — expõe os acessores usados pelos
    handlers (scalar_one_or_none / scalar / first / fetchone / scalars().all /
    mappings().first)."""

    def __init__(self, *, scalar_one=None, scalar=0, first=None,
                 fetchone=None, all=_UNSET):
        self._scalar_one = scalar_one
        self._scalar = scalar
        self._first = first
        self._fetchone = fetchone
        self._all = [] if all is _UNSET else all

    def scalar_one_or_none(self):
        return self._scalar_one

    def scalar(self):
        return self._scalar

    def first(self):
        return self._first

    def fetchone(self):
        return self._fetchone

    def scalars(self):
        return self

    def all(self):
        return self._all

    def mappings(self):
        return self


class _SeqDB:
    """AsyncSession fake que devolve _Res em sequência e registra os statements
    executados (para inspeção do SQL gerado)."""

    def __init__(self, results=()):
        self._results = list(results)
        self.executed = []
        self.added: list = []
        self.committed = False

    async def execute(self, stmt, *a, **k):
        self.executed.append(stmt)
        if self._results:
            return self._results.pop(0)
        return _Res()

    def add(self, obj):
        # Aprovar/pagar retirada passou a gravar AuditLog na MESMA sessão; sem
        # `add` o fake estourava AttributeError e escondia a trilha nova.
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        pass

    async def refresh(self, obj):
        pass


def _user(role: UserRole, uid: str = "u1") -> User:
    return User(id=uid, role=role)


def _sql(stmt) -> str:
    """SQL textual do statement (para asserts de shape sem banco)."""
    return str(stmt.compile(compile_kwargs={"literal_binds": False}))


# ══════════════════════════════════════════════════════════════════════════════
# A1 — clients.PATCH /clients/{id}: write-IDOR de PII entre carteiras
# ══════════════════════════════════════════════════════════════════════════════

from app.routers.clients import _pode_ver_cliente, atualizar  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.schemas.client import ClientUpdate  # noqa: E402


async def test_A1_pode_ver_cliente_advogado_fora_carteira_false():
    """Advogado sem titularidade e sem caso vinculado NÃO vê o cliente."""
    cli = Client(id="c1", responsavel_id="outro_adv")
    db = _SeqDB([_Res(first=None)])  # sem vínculo de caso
    assert await _pode_ver_cliente(_user(UserRole.advogado, "u1"), cli, db) is False


async def test_A1_pode_ver_cliente_advogado_da_carteira_true():
    """Advogado responsável pelo cliente vê (sem sequer consultar casos)."""
    cli = Client(id="c1", responsavel_id="u1")
    db = _SeqDB()  # não deve nem consultar
    assert await _pode_ver_cliente(_user(UserRole.advogado, "u1"), cli, db) is True


async def test_A1_pode_ver_cliente_advogado_com_caso_vinculado_true():
    """Advogado sem titularidade mas com caso do cliente na carteira vê."""
    cli = Client(id="c1", responsavel_id="outro_adv")
    db = _SeqDB([_Res(first=("case-1",))])  # há caso vinculado
    assert await _pode_ver_cliente(_user(UserRole.advogado, "u1"), cli, db) is True


async def test_A1_pode_ver_cliente_gestao_true():
    cli = Client(id="c1", responsavel_id="outro_adv")
    assert await _pode_ver_cliente(_user(UserRole.socio, "u1"), cli, _SeqDB()) is True


async def test_A1_atualizar_cliente_fora_carteira_404():
    """PATCH bloqueado ANTES de qualquer escrita: advogado alheio → 404
    (não vaza existência), fechando o write-IDOR de PII cifrada."""
    cli = Client(id="c1", responsavel_id="outro_adv")
    # 1ª execute: SELECT do cliente; 2ª execute (dentro de _pode_ver_cliente):
    # busca de caso vinculado → None (sem acesso).
    db = _SeqDB([_Res(scalar_one=cli), _Res(first=None)])
    with pytest.raises(HTTPException) as exc:
        await atualizar("c1", ClientUpdate(nome="Hackeado"), db,
                        _user(UserRole.advogado, "u1"))
    assert exc.value.status_code == 404
    assert db.committed is False  # nada foi gravado


async def test_A1_atualizar_cliente_da_carteira_ok(monkeypatch):
    """Advogado responsável pelo cliente edita normalmente (gate deixa passar)."""
    monkeypatch.setattr("app.routers.clients.criar_audit_log",
                        lambda *a, **k: _async_noop())
    cli = Client(id="c1", responsavel_id="u1", nome="Antigo")
    db = _SeqDB([_Res(scalar_one=cli)])  # _pode_ver_cliente passa no responsavel_id
    out = await atualizar("c1", ClientUpdate(nome="Novo Nome"), db,
                          _user(UserRole.advogado, "u1"))
    assert out.nome == "Novo Nome"
    assert db.committed is True


async def _async_noop():
    return None


# ══════════════════════════════════════════════════════════════════════════════
# A2 — centro_custos.GET /centro-custos (sem case_id): escopo por casos próprios
# ══════════════════════════════════════════════════════════════════════════════

from app.routers.centro_custos import listar_lancamentos  # noqa: E402


async def test_A2_centro_custos_advogado_sem_case_id_escopa_por_ownership():
    """Sem case_id, não-gestão só enxerga custos dos próprios casos: a query
    ganha a subquery de ownership (SELECT cases.id ...)."""
    db = _SeqDB([_Res(scalar=0), _Res(all=[])])
    await listar_lancamentos(case_id=None, tipo=None, categoria=None, pago=None,
                             page=1, per_page=30, db=db, cu=_user(UserRole.advogado, "u1"))
    sqls = " || ".join(_sql(s) for s in db.executed)
    assert "cases.id" in sqls  # escopo de ownership aplicado


async def test_A2_centro_custos_gestao_sem_case_id_ve_tudo():
    """Gestão (socio+) sem case_id NÃO recebe o filtro de ownership."""
    db = _SeqDB([_Res(scalar=0), _Res(all=[])])
    await listar_lancamentos(case_id=None, tipo=None, categoria=None, pago=None,
                             page=1, per_page=30, db=db, cu=_user(UserRole.socio, "u1"))
    sqls = " || ".join(_sql(s) for s in db.executed)
    assert "cases.id" not in sqls  # sem escopo — vê todos os lançamentos


# ══════════════════════════════════════════════════════════════════════════════
# A3 — deadlines GET/export.csv: escopo de prazos por ownership
# ══════════════════════════════════════════════════════════════════════════════

from sqlalchemy import select  # noqa: E402
from app.routers.deadlines import _filtro_escopo_prazos  # noqa: E402
from app.models.deadline import Deadline  # noqa: E402


async def test_A3_filtro_escopo_prazos_gestao_nao_restringe():
    """Gestão (socio+) enxerga todos os prazos — filtro é identidade."""
    q = select(Deadline)
    assert _filtro_escopo_prazos(q, _user(UserRole.socio, "u1")) is q


async def test_A3_filtro_escopo_prazos_nao_gestao_restringe():
    """Não-gestão recebe o escopo: casos próprios OU responsável direto OU
    prazos avulsos (case_id IS NULL)."""
    q = select(Deadline)
    filtrada = _filtro_escopo_prazos(q, _user(UserRole.advogado, "u1"))
    assert filtrada is not q
    sql = _sql(filtrada)
    assert "cases.id" in sql          # subquery de casos do usuário
    assert "responsavel_id" in sql    # OU responsável direto
    assert "IS NULL" in sql           # OU avulso (case_id IS NULL)


async def test_A3_filtro_escopo_prazos_advogado_auxiliar_tambem_restringe():
    q = select(Deadline)
    filtrada = _filtro_escopo_prazos(q, _user(UserRole.advogado_auxiliar, "u1"))
    assert filtrada is not q
    assert "cases.id" in _sql(filtrada)


# ══════════════════════════════════════════════════════════════════════════════
# B1 — deadlines DELETE /deadlines/{id}: superadmin NÃO toma 403 (lockout)
# ══════════════════════════════════════════════════════════════════════════════

from app.core.security import requer_advogado  # noqa: E402
from app.routers.deadlines import cancelar  # noqa: E402


def test_B1_requer_advogado_nao_barra_superadmin():
    """Regressão do lockout: requer_advogado deixa superadmin(9) passar."""
    requer_advogado(_user(UserRole.superadmin, "u1"))  # não levanta


def test_B1_requer_advogado_barra_financeiro():
    with pytest.raises(HTTPException) as exc:
        requer_advogado(_user(UserRole.financeiro, "u1"))
    assert exc.value.status_code == 403


async def test_B1_cancelar_superadmin_passa_do_gate():
    """DELETE por superadmin passa do gate (não 403); com prazo inexistente
    o resultado é 404 — provando que o piso não o barra mais."""
    db = _SeqDB([_Res(scalar_one=None)])  # prazo não encontrado
    with pytest.raises(HTTPException) as exc:
        await cancelar("d1", db, _user(UserRole.superadmin, "u1"))
    assert exc.value.status_code == 404


async def test_B1_cancelar_financeiro_403():
    with pytest.raises(HTTPException) as exc:
        await cancelar("d1", _SeqDB(), _user(UserRole.financeiro, "u1"))
    assert exc.value.status_code == 403


async def test_B1_cancelar_estagiario_403():
    with pytest.raises(HTTPException) as exc:
        await cancelar("d1", _SeqDB(), _user(UserRole.estagiario, "u1"))
    assert exc.value.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# A4 — data_room: _gate_room aplica ownership da SALA (404 se alheia)
# ══════════════════════════════════════════════════════════════════════════════

from app.routers.data_room import _gate_room  # noqa: E402
from app.models.data_room import DataRoom  # noqa: E402
from app.models.case import Case  # noqa: E402


async def test_A4_gate_room_gestao_passa():
    room = DataRoom(id="r1", case_id="cX", client_id=None)
    out = await _gate_room(_SeqDB(), _user(UserRole.socio, "u1"), room)
    assert out is room


async def test_A4_gate_room_sala_de_caso_alheio_404():
    """Sala vinculada a caso de outra carteira → 404 (verificar_acesso_caso
    daria 403; _gate_room converte para 404 e não vaza a sala)."""
    room = DataRoom(id="r1", case_id="cX", client_id=None)
    caso = Case(id="cX", advogado_responsavel_id="outro", advogado_auxiliar_id="tb_outro")
    db = _SeqDB([_Res(scalar_one=caso)])  # verificar_acesso_caso carrega o caso
    with pytest.raises(HTTPException) as exc:
        await _gate_room(db, _user(UserRole.advogado, "u1"), room)
    assert exc.value.status_code == 404


async def test_A4_gate_room_sala_de_caso_proprio_passa():
    room = DataRoom(id="r1", case_id="cX", client_id=None)
    caso = Case(id="cX", advogado_responsavel_id="u1", advogado_auxiliar_id=None)
    db = _SeqDB([_Res(scalar_one=caso)])
    out = await _gate_room(db, _user(UserRole.advogado, "u1"), room)
    assert out is room


async def test_A4_gate_room_sala_de_cliente_alheio_404():
    """Sala só com client_id de carteira alheia → 404."""
    room = DataRoom(id="r1", case_id=None, client_id="clX")
    cli = Client(id="clX", responsavel_id="outro_adv")
    # 1ª execute: SELECT Client (em _gate_room); 2ª execute: caso vinculado
    # (em _pode_ver_cliente) → None.
    db = _SeqDB([_Res(scalar_one=cli), _Res(first=None)])
    with pytest.raises(HTTPException) as exc:
        await _gate_room(db, _user(UserRole.advogado, "u1"), room)
    assert exc.value.status_code == 404


async def test_A4_gate_room_sala_de_cliente_proprio_passa():
    room = DataRoom(id="r1", case_id=None, client_id="clX")
    cli = Client(id="clX", responsavel_id="u1")
    db = _SeqDB([_Res(scalar_one=cli)])  # _pode_ver_cliente passa no responsavel_id
    out = await _gate_room(db, _user(UserRole.advogado, "u1"), room)
    assert out is room


async def test_A4_gate_room_sala_sem_caso_nem_cliente_passa():
    """Sala legado (sem caso nem cliente) liberada a quem passou no piso."""
    room = DataRoom(id="r1", case_id=None, client_id=None)
    out = await _gate_room(_SeqDB(), _user(UserRole.advogado, "u1"), room)
    assert out is room


# ══════════════════════════════════════════════════════════════════════════════
# A6 — partner_withdrawals: segregação de funções (não aprova/paga a própria)
# ══════════════════════════════════════════════════════════════════════════════

from app.routers.partner_withdrawals import approve_withdrawal, pay_withdrawal  # noqa: E402


class _WUser:
    """current_user do partner_withdrawals: role é comparada com o set de
    strings PRIVILEGED (UserRole é str-enum, mas usamos string crua p/ clareza)."""

    def __init__(self, role: str, uid: str):
        self.role = role
        self.id = uid


async def test_A6_socio_nao_aprova_propria_retirada_403():
    """Auto-aprovação bloqueada (SoD): partner_id == current_user.id → 403."""
    db = _SeqDB([_Res(first={"id": "w1", "partner_id": "socio-1", "status": "pendente"})])
    with pytest.raises(HTTPException) as exc:
        await approve_withdrawal("w1", db, _WUser("socio", "socio-1"))
    assert exc.value.status_code == 403


async def test_A6_socio_aprova_retirada_de_outro_ok():
    """Sócio aprova a retirada de OUTRO sócio (pendente) normalmente."""
    db = _SeqDB([_Res(first={"id": "w1", "partner_id": "socio-2", "status": "pendente"}), _Res()])
    out = await approve_withdrawal("w1", db, _WUser("socio", "socio-1"))
    assert out["status"] == "aprovado"
    assert db.committed is True


async def test_A6_superadmin_nao_aprova_propria_retirada_403():
    """Nem superadmin escapa da segregação (auto-dealing é do indivíduo)."""
    db = _SeqDB([_Res(first={"id": "w1", "partner_id": "god-1", "status": "pendente"})])
    with pytest.raises(HTTPException) as exc:
        await approve_withdrawal("w1", db, _WUser("superadmin", "god-1"))
    assert exc.value.status_code == 403


async def test_A6_socio_nao_paga_propria_retirada_403():
    db = _SeqDB([_Res(first={"id": "w1", "partner_id": "socio-1", "status": "aprovado"})])
    with pytest.raises(HTTPException) as exc:
        await pay_withdrawal("w1", db, _WUser("socio", "socio-1"))
    assert exc.value.status_code == 403


async def test_A6_socio_paga_retirada_de_outro_ok():
    db = _SeqDB([_Res(first={"id": "w1", "partner_id": "socio-2", "status": "aprovado"}), _Res()])
    out = await pay_withdrawal("w1", db, _WUser("socio", "socio-1"))
    assert out["status"] == "pago"


async def test_A6_financeiro_nao_aprova_403():
    """Papel fora de PRIVILEGED (financeiro) segue barrado no piso."""
    with pytest.raises(HTTPException) as exc:
        await approve_withdrawal("w1", _SeqDB(), _WUser("financeiro", "f1"))
    assert exc.value.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# D9a — atendimentos: segregação de carteira (_pode_ver_atendimento)
# ══════════════════════════════════════════════════════════════════════════════

from app.routers.atendimentos import _pode_ver_atendimento  # noqa: E402
from app.models.atendimento import Atendimento  # noqa: E402


def _atend(**kw) -> Atendimento:
    base = dict(id="a1", client_id="clX", created_by="outro",
                advogado_responsavel_id="outro", solicitacao_responsavel_id=None)
    base.update(kw)
    return Atendimento(**base)


async def test_D9a_gestao_ve_qualquer_atendimento():
    a = _atend()
    assert await _pode_ver_atendimento(_SeqDB(), _user(UserRole.socio, "u1"), a) is True


async def test_D9a_secretaria_ve_qualquer_atendimento():
    a = _atend()
    assert await _pode_ver_atendimento(_SeqDB(), _user(UserRole.secretaria, "u1"), a) is True


async def test_D9a_advogado_ve_o_proprio_registro():
    """Criador/responsável do atendimento sempre vê o próprio registro."""
    a = _atend(created_by="u1")
    assert await _pode_ver_atendimento(_SeqDB(), _user(UserRole.advogado, "u1"), a) is True


async def test_D9a_advogado_ve_atendimento_avulso_sem_cliente():
    a = _atend(client_id=None)
    assert await _pode_ver_atendimento(_SeqDB(), _user(UserRole.advogado, "u1"), a) is True


async def test_D9a_advogado_ve_atendimento_de_cliente_da_carteira():
    """Cliente cujo responsavel_id é o advogado → vê."""
    a = _atend()
    cli = Client(id="clX", responsavel_id="u1")
    db = _SeqDB([_Res(scalar_one=cli)])
    assert await _pode_ver_atendimento(db, _user(UserRole.advogado, "u1"), a) is True


async def test_D9a_advogado_NAO_ve_atendimento_de_carteira_alheia():
    """Registro de cliente de OUTRA carteira (sem titularidade e sem caso
    vinculado) → não visível (handler responde 404)."""
    a = _atend()
    cli = Client(id="clX", responsavel_id="outro_adv")
    # 1ª execute: SELECT Client → cli; 2ª execute: caso vinculado → None.
    db = _SeqDB([_Res(scalar_one=cli), _Res(first=None)])
    assert await _pode_ver_atendimento(db, _user(UserRole.advogado, "u1"), a) is False


async def test_D9a_advogado_ve_atendimento_via_caso_vinculado():
    """Sem titularidade do cliente, mas com caso do cliente na carteira → vê."""
    a = _atend()
    cli = Client(id="clX", responsavel_id="outro_adv")
    db = _SeqDB([_Res(scalar_one=cli), _Res(first=("case-1",))])
    assert await _pode_ver_atendimento(db, _user(UserRole.advogado, "u1"), a) is True
