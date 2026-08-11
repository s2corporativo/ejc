# ── tests/test_deadlines_recesso_art220.py ───────────────────────────────────
# Regressão P0 — achado PRZ-02 da auditoria de prazos processuais (risco nº1
# de escritório de advocacia: perda de prazo → responsabilidade civil e
# disciplinar).
#
# CPC/2015 (Lei 13.105/2015), art. 220 — recesso forense (20/12 a 20/01,
# inclusive): suspensão INTEGRAL do curso do prazo PROCESSUAL em dias úteis.
# NUNCA se aplica a prazo decadencial ou administrativo em dias corridos
# (docstring de prazo_dias_uteis em app/services/deadline_calculator.py).
#
# prazo_dias_uteis(..., aplicar_recesso=True) já existe e é usado
# corretamente por motor_peca_service.confirmar_e_criar_prazo (referência).
# O caminho que faltava — POST /deadlines, que o advogado usa para criar
# prazo manualmente — não passava esse parâmetro e por isso dava prazo MENOR
# do que o devido para qualquer contagem que atravessasse 20/12–20/01.
#
# Nota de escopo (registrada também no PR): o achado original também cobria
# o aceite de prazo de intimação DJEN (backend/app/routers/intimacoes.py).
# Esse arquivo está sob reescrita ativa no PR #1022 (que remove inteiramente
# o cálculo automático de prazo em Intimações, substituindo por conferência
# manual obrigatória) — mexer nele aqui violaria a regra de não tocar arquivo
# de outro PR ativo. A correção lá fica para depois do merge do #1022,
# quando o desenho de termo inicial for revisitado sobre o código novo.
#
# Fonte: CPC/2015 (Lei 13.105/2015), art. 220 — vigente, sem alteração
# superveniente conhecida.
from __future__ import annotations

from datetime import date

import pytest

from app.models.deadline import Deadline
from app.models.user import User, UserRole
from app.services.deadline_calculator import prazo_dias_uteis


# ── Fakes (mesmo padrão de tests/test_intimacao_prazo_assistido.py) ──────────

class _Res:
    def __init__(self, val):
        self._val = val

    def scalar_one_or_none(self):
        return self._val


class _FakeDB:
    """Fila de resultados para execute(); registra add/commit.

    add() também simula os defaults que um flush real de SQLAlchemy aplicaria
    (Deadline.status/ciencia_confirmada/confirmado/created_at têm default só
    no nível de Column, não no __init__) — necessário aqui porque
    routers.deadlines.criar() serializa o objeto via DeadlineResponse logo
    após o commit, e o commit deste fake não passa pelo banco de verdade.
    """

    def __init__(self, resultados: list | None = None):
        self._resultados = list(resultados or [])
        self.added: list = []
        self.commits = 0

    async def execute(self, *a, **k):
        return _Res(self._resultados.pop(0) if self._resultados else None)

    def add(self, obj):
        if isinstance(obj, Deadline):
            from datetime import datetime, timezone as _tz

            from app.models.deadline import DeadlineStatus

            if obj.status is None:
                obj.status = DeadlineStatus.pendente
            if obj.ciencia_confirmada is None:
                obj.ciencia_confirmada = False
            if getattr(obj, "confirmado", None) is None:
                obj.confirmado = True
            if obj.created_at is None:
                obj.created_at = datetime.now(_tz.utc)
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        pass

    async def rollback(self):
        pass


def _user(role: UserRole = UserRole.advogado, uid: str = "adv-1") -> User:
    u = User(id=uid, email=f"{uid}@ejc.adv.br", full_name="Dra. Fulana", role=role)
    u.is_active = True
    return u


# ── Fixture do achado ─────────────────────────────────────────────────────────

TERMO_INICIAL_RECESSO = date(2025, 12, 15)  # segunda; contagem atravessa 20/12–20/01
DIAS_RECESSO = 10


def test_referencia_recesso_diverge_do_calculo_sem_recesso():
    """Confirma a premissa do achado: para este par (termo_inicial, dias) o
    recesso do art. 220 MUDA o resultado — senão os testes de convergência
    abaixo não provariam nada."""
    sem_recesso = prazo_dias_uteis(TERMO_INICIAL_RECESSO, DIAS_RECESSO)
    com_recesso = prazo_dias_uteis(
        TERMO_INICIAL_RECESSO, DIAS_RECESSO, aplicar_recesso=True
    )
    assert sem_recesso == date(2026, 1, 14)
    assert com_recesso == date(2026, 1, 28)
    assert com_recesso > sem_recesso


@pytest.mark.anyio
async def test_post_deadlines_aplica_recesso_para_tipo_processual():
    """POST /deadlines (criação manual) — antes da correção não passava
    aplicar_recesso=True e dava prazo MENOR do que o devido para contagens
    que atravessam 20/12–20/01."""
    from app.routers.deadlines import criar
    from app.schemas.deadline import DeadlineCreate

    db = _FakeDB()
    payload = DeadlineCreate(
        titulo="Contestação — teste recesso",
        tipo="processual",
        data_intimacao=TERMO_INICIAL_RECESSO,
        dias_prazo=DIAS_RECESSO,
        dias_uteis=True,
    )
    resp = await criar(payload=payload, db=db, cu=_user())

    assert resp.data_prazo == date(2026, 1, 28)  # com recesso (correto)
    assert resp.data_prazo != date(2026, 1, 14)  # sem recesso (bug antigo)


@pytest.mark.anyio
async def test_post_deadlines_nao_aplica_recesso_para_tipo_administrativo():
    """Guarda-corpo do achado: a correção NÃO pode virar suspensão universal —
    prazo administrativo/decadencial NUNCA se suspende no recesso (docstring
    de prazo_dias_uteis). Mesmo que o payload force dias_uteis=True num tipo
    não-processual, aplicar_recesso deve permanecer False."""
    from app.routers.deadlines import criar
    from app.schemas.deadline import DeadlineCreate

    db = _FakeDB()
    payload = DeadlineCreate(
        titulo="Defesa administrativa — teste sem recesso",
        tipo="administrativo",
        data_intimacao=TERMO_INICIAL_RECESSO,
        dias_prazo=DIAS_RECESSO,
        dias_uteis=True,
    )
    resp = await criar(payload=payload, db=db, cu=_user())

    assert resp.data_prazo == date(2026, 1, 14)  # SEM recesso (correto p/ este tipo)


@pytest.mark.anyio
async def test_post_deadlines_converge_com_referencia_do_motor_de_pecas():
    """O núcleo do achado PRZ-02: antes da correção, POST /deadlines DIVERGIA
    do motor de peças (referência correta, `confirmar_e_criar_prazo`, que já
    usava aplicar_recesso=True). Depois da correção os dois CONVERGEM para o
    mesmo resultado, dado o mesmo termo_inicial e a mesma quantidade de dias."""
    from app.routers.deadlines import criar
    from app.schemas.deadline import DeadlineCreate

    # Referência: exatamente a chamada usada por
    # motor_peca_service.confirmar_e_criar_prazo (aplicar_recesso=True) para
    # um prazo processual em dias úteis.
    referencia_motor_peca = prazo_dias_uteis(
        TERMO_INICIAL_RECESSO, DIAS_RECESSO, tribunal="TJMG", aplicar_recesso=True
    )

    db = _FakeDB()
    resp = await criar(
        payload=DeadlineCreate(
            titulo="Contestação",
            tipo="processual",
            data_intimacao=TERMO_INICIAL_RECESSO,
            dias_prazo=DIAS_RECESSO,
            dias_uteis=True,
            tribunal="TJMG",
        ),
        db=db, cu=_user(),
    )

    assert resp.data_prazo == referencia_motor_peca
