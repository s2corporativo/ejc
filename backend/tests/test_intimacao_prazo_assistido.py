"""Fluxo DJEN → revisão humana de prazo — contenção P0 da Issue #968.

A suíte antiga congelava heurísticas juridicamente inseguras (fallback de 15
dias e contagem desde a disponibilização). Esta versão prova o contrato fail-safe:

- nenhuma expressão textual produz vencimento automático;
- disponibilização é exibida como fato da fonte, nunca como termo inicial;
- somente ``data_prazo`` informada pelo usuário pode materializar Deadline;
- ``dias`` sem motor por regime é rejeitado;
- aceite/recusa e marcação como tratada são auditáveis e idempotentes;
- uma comunicação só pode ser tratada após decisão explícita sobre prazo.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.models.audit_log import AuditLog
from app.models.deadline import Deadline
from app.models.user import User, UserRole


class _Res:
    def __init__(self, val):
        self._val = val

    def scalar_one_or_none(self):
        return self._val


class _FakeDB:
    """Fila de resultados para execute(); registra add/commit."""

    def __init__(self, resultados: list | None = None):
        self._resultados = list(resultados or [])
        self.added: list = []
        self.commits = 0

    async def execute(self, *a, **k):
        return _Res(self._resultados.pop(0) if self._resultados else None)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        return None

    async def rollback(self):
        return None


def _user(role: UserRole = UserRole.advogado, uid: str = "adv-1") -> User:
    u = User(
        id=uid,
        email=f"{uid}@ejc.adv.br",
        full_name="Dra. Fulana",
        role=role,
    )
    u.is_active = True
    return u


def _com(**kw):
    from app.models.djen import DjenComunicacao

    base = dict(
        id="com-1",
        advogado_id="adv-1",
        case_id="case-1",
        numero_processo="1001234-56.2024.8.13.0024",
        tribunal="TJMG",
        tipo_comunicacao="Intimação",
        texto_resumo="Fica a parte intimada para apresentar contestação.",
        data_disponibilizacao=date(2026, 3, 2),
        prazo_sugerido_status=None,
        prazo_deadline_id=None,
        processada=False,
    )
    base.update(kw)
    return DjenComunicacao(**base)


def _liberar_caso(monkeypatch):
    from app.routers import intimacoes

    async def _ok(db, user, case_id):
        return object()

    monkeypatch.setattr(intimacoes, "verificar_acesso_caso", _ok)


# ── Fail-safe jurídico ────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "texto",
    [
        "Intimação para opor embargos de declaração",
        "Fica intimado para apresentar contestação",
        "Prazo para interpor apelação da sentença",
        "Intimação de despacho para manifestação",
        "Recurso urgente — prazo legal",
        "Comunicação de ato ordinatório",
    ],
)
def test_texto_da_comunicacao_nunca_calcula_vencimento(texto):
    from app.routers.intimacoes import _calcular_sugestao

    s = _calcular_sugestao(_com(texto_resumo=texto))

    assert s["disponivel"] is False
    assert s["revisao_necessaria"] is True
    assert s["dias"] is None
    assert s["data_base"] is None
    assert s["data_sugerida"] is None
    assert s["fundamentacao"] is None
    assert s["casou"] is False


def test_disponibilizacao_e_preservada_apenas_como_metadado():
    from app.routers.intimacoes import _calcular_sugestao

    s = _calcular_sugestao(_com(data_disponibilizacao=date(2026, 3, 2)))

    assert s["data_disponibilizacao"] == date(2026, 3, 2)
    assert s["data_base"] is None


def test_datetime_de_disponibilizacao_nao_vira_termo_inicial():
    from app.routers.intimacoes import _calcular_sugestao

    s = _calcular_sugestao(
        _com(
            data_disponibilizacao=datetime(
                2026,
                3,
                2,
                14,
                30,
                tzinfo=timezone.utc,
            )
        )
    )

    assert s["data_disponibilizacao"] == date(2026, 3, 2)
    assert s["data_base"] is None
    assert s["data_sugerida"] is None


def test_router_nao_importa_calculador_de_prazo():
    from app.routers import intimacoes

    origem = Path(intimacoes.__file__).read_text(encoding="utf-8")
    assert "deadline_calculator" not in origem
    assert "prazo_dias_uteis" not in origem
    assert "_HEURISTICAS_PRAZO" not in origem


# ── Ownership ────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_intimacao_de_outro_advogado_404():
    from app.routers.intimacoes import prazo_sugerido

    db = _FakeDB([_com(advogado_id="outro-adv")])
    with pytest.raises(HTTPException) as exc:
        await prazo_sugerido(com_id="com-1", db=db, cu=_user())
    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_gestao_enxerga_intimacao_de_qualquer_advogado():
    from app.routers.intimacoes import prazo_sugerido

    db = _FakeDB([_com(advogado_id="outro-adv")])
    out = await prazo_sugerido(
        com_id="com-1",
        db=db,
        cu=_user(UserRole.socio, "s1"),
    )
    assert out["disponivel"] is False
    assert out["revisao_necessaria"] is True


@pytest.mark.anyio
async def test_aceitar_prazo_aplica_ownership_do_caso(monkeypatch):
    from app.routers import intimacoes

    async def _negar(db, user, case_id):
        raise HTTPException(status_code=403, detail="Sem acesso a este caso")

    monkeypatch.setattr(intimacoes, "verificar_acesso_caso", _negar)
    db = _FakeDB([_com()])
    with pytest.raises(HTTPException) as exc:
        await intimacoes.aceitar_prazo(
            com_id="com-1",
            payload=intimacoes.AceitarPrazoRequest(data_prazo=date(2026, 4, 10)),
            db=db,
            cu=_user(),
        )
    assert exc.value.status_code == 403
    assert db.added == []


# ── Materialização: somente vencimento absoluto conferido ────────────────────

@pytest.mark.anyio
async def test_sem_data_manual_nao_cria_deadline(monkeypatch):
    from app.routers import intimacoes

    _liberar_caso(monkeypatch)
    db = _FakeDB([_com()])

    with pytest.raises(HTTPException) as exc:
        await intimacoes.aceitar_prazo(
            com_id="com-1",
            payload=None,
            db=db,
            cu=_user(),
        )

    assert exc.value.status_code == 422
    assert [o for o in db.added if isinstance(o, Deadline)] == []


@pytest.mark.anyio
async def test_dias_sozinho_e_rejeitado_mesmo_com_disponibilizacao(monkeypatch):
    from app.routers import intimacoes

    _liberar_caso(monkeypatch)
    db = _FakeDB([_com(data_disponibilizacao=date(2026, 3, 2))])

    with pytest.raises(HTTPException) as exc:
        await intimacoes.aceitar_prazo(
            com_id="com-1",
            payload=intimacoes.AceitarPrazoRequest(dias=10),
            db=db,
            cu=_user(),
        )

    assert exc.value.status_code == 422
    assert "data_prazo" in str(exc.value.detail)
    assert [o for o in db.added if isinstance(o, Deadline)] == []


@pytest.mark.anyio
async def test_data_prazo_manual_cria_deadline_sem_falso_termo_inicial(monkeypatch):
    from app.routers import intimacoes

    _liberar_caso(monkeypatch)
    comunicacao = _com(data_disponibilizacao=date(2026, 3, 2))
    db = _FakeDB([comunicacao])

    out = await intimacoes.aceitar_prazo(
        com_id="com-1",
        payload=intimacoes.AceitarPrazoRequest(data_prazo=date(2026, 4, 10)),
        db=db,
        cu=_user(),
    )

    prazos = [o for o in db.added if isinstance(o, Deadline)]
    auditorias = [o for o in db.added if isinstance(o, AuditLog)]
    assert len(prazos) == 1
    assert len(auditorias) == 1

    prazo = prazos[0]
    assert out["criado"] is True
    assert prazo.case_id == "case-1"
    assert prazo.origem == "djen"
    assert prazo.data_prazo == date(2026, 4, 10)
    assert prazo.data_intimacao is None
    assert "revisão humana" in (prazo.base_legal or "")
    assert comunicacao.prazo_sugerido_status == "aceito"
    assert comunicacao.prazo_deadline_id == prazo.id
    assert auditorias[0].dados_depois["modo"] == "vencimento_manual_revisado"


@pytest.mark.anyio
async def test_data_absoluta_tem_precedencia_sobre_campo_dias_legado(monkeypatch):
    from app.routers import intimacoes

    _liberar_caso(monkeypatch)
    db = _FakeDB([_com()])
    payload = intimacoes.AceitarPrazoRequest(
        dias=30,
        data_prazo=date(2026, 4, 10),
    )

    await intimacoes.aceitar_prazo(
        com_id="com-1",
        payload=payload,
        db=db,
        cu=_user(),
    )
    prazo = next(o for o in db.added if isinstance(o, Deadline))
    assert prazo.data_prazo == date(2026, 4, 10)


@pytest.mark.anyio
async def test_aceitar_e_idempotente(monkeypatch):
    from app.routers import intimacoes

    _liberar_caso(monkeypatch)
    comunicacao = _com(
        prazo_sugerido_status="aceito",
        prazo_deadline_id="dl-1",
    )
    existente = Deadline(
        id="dl-1",
        titulo="Prazo conferido",
        tipo="processual",
        data_prazo=date(2026, 3, 25),
        case_id="case-1",
    )
    db = _FakeDB([comunicacao, existente])

    out = await intimacoes.aceitar_prazo(
        com_id="com-1",
        payload=intimacoes.AceitarPrazoRequest(data_prazo=date(2026, 4, 10)),
        db=db,
        cu=_user(),
    )

    assert out["criado"] is False
    assert out["deadline_id"] == "dl-1"
    assert [o for o in db.added if isinstance(o, Deadline)] == []


@pytest.mark.anyio
async def test_intimacao_sem_caso_nao_gera_prazo_orfao(monkeypatch):
    from app.routers import intimacoes

    _liberar_caso(monkeypatch)
    db = _FakeDB([_com(case_id=None)])

    with pytest.raises(HTTPException) as exc:
        await intimacoes.aceitar_prazo(
            com_id="com-1",
            payload=intimacoes.AceitarPrazoRequest(data_prazo=date(2026, 4, 10)),
            db=db,
            cu=_user(),
        )

    assert exc.value.status_code == 422
    assert [o for o in db.added if isinstance(o, Deadline)] == []


@pytest.mark.anyio
async def test_responsavel_default_e_o_advogado_da_intimacao(monkeypatch):
    from app.routers import intimacoes

    _liberar_caso(monkeypatch)
    db = _FakeDB([_com(advogado_id="adv-1")])

    await intimacoes.aceitar_prazo(
        com_id="com-1",
        payload=intimacoes.AceitarPrazoRequest(data_prazo=date(2026, 4, 10)),
        db=db,
        cu=_user(UserRole.socio, "socio-9"),
    )

    prazo = next(o for o in db.added if isinstance(o, Deadline))
    assert prazo.responsavel_id == "adv-1"


# ── Decisão explícita + estado tratado ───────────────────────────────────────

@pytest.mark.anyio
async def test_recusar_marca_status_audita_e_nao_cria_prazo(monkeypatch):
    from app.routers import intimacoes

    _liberar_caso(monkeypatch)
    comunicacao = _com()
    db = _FakeDB([comunicacao])

    out = await intimacoes.recusar_prazo(
        com_id="com-1",
        db=db,
        cu=_user(),
    )

    assert out["prazo_sugerido_status"] == "recusado"
    assert comunicacao.prazo_sugerido_status == "recusado"
    assert [o for o in db.added if isinstance(o, Deadline)] == []
    auditorias = [o for o in db.added if isinstance(o, AuditLog)]
    assert len(auditorias) == 1
    assert auditorias[0].dados_depois == {"prazo_sugerido_status": "recusado"}


@pytest.mark.anyio
async def test_recusar_depois_de_prazo_aceito_e_bloqueado(monkeypatch):
    from app.routers import intimacoes

    _liberar_caso(monkeypatch)
    db = _FakeDB(
        [
            _com(
                prazo_sugerido_status="aceito",
                prazo_deadline_id="dl-1",
            )
        ]
    )

    with pytest.raises(HTTPException) as exc:
        await intimacoes.recusar_prazo(
            com_id="com-1",
            db=db,
            cu=_user(),
        )

    assert exc.value.status_code == 409


@pytest.mark.anyio
async def test_nao_pode_marcar_tratada_sem_decisao_de_prazo(monkeypatch):
    from app.routers import intimacoes

    _liberar_caso(monkeypatch)
    comunicacao = _com(prazo_sugerido_status="nenhum")
    db = _FakeDB([comunicacao])

    with pytest.raises(HTTPException) as exc:
        await intimacoes.processar(
            com_id="com-1",
            db=db,
            cu=_user(),
        )

    assert exc.value.status_code == 422
    assert comunicacao.processada is False
    assert db.commits == 0


@pytest.mark.anyio
@pytest.mark.parametrize("decisao", ["aceito", "recusado"])
async def test_tratada_so_depois_de_decisao_e_com_auditoria(monkeypatch, decisao):
    from app.routers import intimacoes

    _liberar_caso(monkeypatch)
    comunicacao = _com(prazo_sugerido_status=decisao)
    db = _FakeDB([comunicacao])

    out = await intimacoes.processar(
        com_id="com-1",
        db=db,
        cu=_user(),
    )

    assert out["detail"] == "Intimação marcada como tratada"
    assert comunicacao.processada is True
    assert comunicacao.processada_por == "adv-1"
    assert comunicacao.processada_em is not None
    assert db.commits == 1
    auditorias = [o for o in db.added if isinstance(o, AuditLog)]
    assert len(auditorias) == 1
    assert auditorias[0].dados_depois["decisao_prazo"] == decisao


@pytest.mark.anyio
async def test_processar_e_idempotente(monkeypatch):
    from app.routers import intimacoes

    _liberar_caso(monkeypatch)
    comunicacao = _com(
        prazo_sugerido_status="recusado",
        processada=True,
    )
    db = _FakeDB([comunicacao])

    out = await intimacoes.processar(
        com_id="com-1",
        db=db,
        cu=_user(),
    )

    assert "já estava" in out["detail"]
    assert db.commits == 0
    assert [o for o in db.added if isinstance(o, AuditLog)] == []
