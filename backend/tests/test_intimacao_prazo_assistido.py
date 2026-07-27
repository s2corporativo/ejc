"""Fluxo assistido intimação DJEN → prazo (P0 — erro aqui gera PRECLUSÃO).

O plano de simplificação marca este fluxo como P0 justamente porque um prazo
calculado a mais, a menos, duplicado ou silenciosamente não criado custa o
direito da parte. Até aqui ele não tinha NENHUM teste.

Cobre os três endpoints do fluxo (`prazo-sugerido`, `aceitar-prazo`,
`recusar-prazo`) e as invariantes que protegem o prazo:

  • heurística por tipo de comunicação (embargos 5 / contestação 15 / recurso
    15 / manifestação 5), com ordem de precedência dos termos;
  • artigo SÓ citado quando a heurística casou explicitamente — nunca inventado;
  • sem data de disponibilização não há contagem: `disponivel=False` e 422 no
    aceite sem override;
  • precedência do override: data_prazo > dias > sugestão;
  • IDEMPOTÊNCIA: aceitar duas vezes não duplica o prazo (prazo duplicado polui
    a agenda e mascara o verdadeiro);
  • ownership: intimação alheia devolve 404 (não confirma existência) e o
    aceite exige acesso ao caso;
  • intimação sem caso não gera prazo órfão (422).

Padrão do repo: sem Postgres — fakes de sessão por arquivo e chamada direta
dos handlers.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException

from app.models.deadline import Deadline
from app.models.user import User, UserRole


# ── Fakes ────────────────────────────────────────────────────────────────────

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
        pass

    async def rollback(self):
        pass


def _user(role: UserRole = UserRole.advogado, uid: str = "adv-1") -> User:
    u = User(id=uid, email=f"{uid}@ejc.adv.br", full_name="Dra. Fulana", role=role)
    u.is_active = True
    return u


def _com(**kw):
    """Comunicação DJEN com defaults de um caso feliz."""
    from app.models.djen import DjenComunicacao

    base = dict(
        id="com-1",
        advogado_id="adv-1",
        case_id="case-1",
        numero_processo="1001234-56.2024.8.13.0024",
        tribunal="TJMG",
        tipo_comunicacao="Intimação",
        texto_resumo="Fica a parte intimada para apresentar contestação.",
        data_disponibilizacao=date(2026, 3, 2),  # segunda-feira
        prazo_sugerido_status=None,
        prazo_deadline_id=None,
    )
    base.update(kw)
    return DjenComunicacao(**base)


def _liberar_caso(monkeypatch):
    """Ownership de caso concedido (o gate tem cobertura própria)."""
    from app.routers import intimacoes

    async def _ok(db, user, case_id):
        return object()

    monkeypatch.setattr(intimacoes, "verificar_acesso_caso", _ok)


# ── Heurística: dias e fundamentação ─────────────────────────────────────────

@pytest.mark.parametrize(
    "texto,dias_esperados,artigo_trecho",
    [
        ("Intimação para opor embargos de declaração", 5, "art. 1.023"),
        ("Fica intimado para apresentar contestação", 15, "art. 335"),
        ("Prazo para interpor apelação da sentença", 15, "art. 1.003"),
        ("Intimação de despacho para manifestação", 5, "art. 218"),
    ],
)
def test_heuristica_reconhece_tipo_e_cita_o_artigo(texto, dias_esperados, artigo_trecho):
    from app.routers.intimacoes import _calcular_sugestao

    s = _calcular_sugestao(_com(texto_resumo=texto))
    assert s["dias"] == dias_esperados
    assert artigo_trecho in (s["fundamentacao"] or "")


def test_heuristica_prefere_o_termo_mais_especifico():
    """'embargos de declaração' vem ANTES de 'recurso' na tabela: um texto com
    ambos precisa cair em 5 dias, não em 15 — errar aqui perde o prazo."""
    from app.routers.intimacoes import _calcular_sugestao

    s = _calcular_sugestao(
        _com(texto_resumo="Recurso: intimação para opor embargos de declaração")
    )
    assert s["dias"] == 5
    assert "1.023" in (s["fundamentacao"] or "")


def test_tipo_nao_identificado_nao_inventa_artigo():
    """Sem casamento explícito o sistema NÃO pode citar base legal — é a regra
    anti-alucinação do repo aplicada ao prazo."""
    from app.routers.intimacoes import _calcular_sugestao

    s = _calcular_sugestao(_com(texto_resumo="Comunicação de ato ordinatório."))
    assert s["tipo_detectado"] == "não identificado"
    assert s["fundamentacao"] is None
    assert s["dias"] == 15  # default conservador


def test_sem_disponibilizacao_marca_indisponivel():
    from app.routers.intimacoes import _calcular_sugestao

    s = _calcular_sugestao(_com(data_disponibilizacao=None))
    assert s["disponivel"] is False


def test_datetime_de_disponibilizacao_e_normalizado_para_date():
    from app.routers.intimacoes import _calcular_sugestao

    s = _calcular_sugestao(
        _com(data_disponibilizacao=datetime(2026, 3, 2, 14, 30, tzinfo=timezone.utc))
    )
    assert s["disponivel"] is True
    assert isinstance(s["data_sugerida"], date)


# ── Ownership ────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_intimacao_de_outro_advogado_404():
    """404 (não 403): não confirma a existência de intimação alheia."""
    from app.routers.intimacoes import prazo_sugerido

    db = _FakeDB([_com(advogado_id="outro-adv")])
    with pytest.raises(HTTPException) as ei:
        await prazo_sugerido(com_id="com-1", db=db, cu=_user())
    assert ei.value.status_code == 404


@pytest.mark.anyio
async def test_gestao_enxerga_intimacao_de_qualquer_advogado():
    from app.routers.intimacoes import prazo_sugerido

    db = _FakeDB([_com(advogado_id="outro-adv")])
    out = await prazo_sugerido(com_id="com-1", db=db, cu=_user(UserRole.socio, "s1"))
    assert out["disponivel"] is True


@pytest.mark.anyio
async def test_aceitar_prazo_aplica_ownership_do_caso(monkeypatch):
    from app.routers import intimacoes

    async def _negar(db, user, case_id):
        raise HTTPException(status_code=403, detail="Sem acesso a este caso")

    monkeypatch.setattr(intimacoes, "verificar_acesso_caso", _negar)
    db = _FakeDB([_com()])
    with pytest.raises(HTTPException) as ei:
        await intimacoes.aceitar_prazo(com_id="com-1", payload=None, db=db, cu=_user())
    assert ei.value.status_code == 403
    assert db.added == []  # nada gravado quando o gate barra


# ── Aceite: criação do prazo ─────────────────────────────────────────────────

@pytest.mark.anyio
async def test_aceitar_cria_deadline_com_rastreabilidade(monkeypatch):
    from app.routers import intimacoes

    _liberar_caso(monkeypatch)
    com = _com()
    db = _FakeDB([com])
    out = await intimacoes.aceitar_prazo(
        com_id="com-1", payload=None, db=db, cu=_user()
    )

    prazos = [o for o in db.added if isinstance(o, Deadline)]
    assert len(prazos) == 1
    d = prazos[0]
    assert out["criado"] is True
    assert d.case_id == "case-1"
    assert d.origem == "djen"                    # rastreia a fonte do prazo
    assert d.data_intimacao == date(2026, 3, 2)  # termo inicial preservado
    assert d.data_prazo > d.data_intimacao       # nunca retroativo
    assert "335" in (d.base_legal or "")         # contestação → art. 335
    # A intimação passa a apontar para o prazo criado (fecha o ciclo).
    assert com.prazo_sugerido_status == "aceito"
    assert com.prazo_deadline_id == d.id


@pytest.mark.anyio
async def test_aceitar_e_idempotente(monkeypatch):
    """Segundo aceite NÃO duplica: prazo duplicado polui a agenda e mascara o
    verdadeiro."""
    from app.routers import intimacoes

    _liberar_caso(monkeypatch)
    com = _com(prazo_sugerido_status="aceito", prazo_deadline_id="dl-1")
    existente = Deadline(id="dl-1", titulo="Contestação", tipo="processual",
                         data_prazo=date(2026, 3, 25), case_id="case-1")
    db = _FakeDB([com, existente])

    out = await intimacoes.aceitar_prazo(
        com_id="com-1", payload=None, db=db, cu=_user()
    )
    assert out["criado"] is False
    assert out["deadline_id"] == "dl-1"
    assert [o for o in db.added if isinstance(o, Deadline)] == []


# ── Precedência do override: data_prazo > dias > sugestão ────────────────────

@pytest.mark.anyio
async def test_data_prazo_absoluta_vence_dias(monkeypatch):
    from app.routers import intimacoes

    _liberar_caso(monkeypatch)
    db = _FakeDB([_com()])
    payload = intimacoes.AceitarPrazoRequest(
        dias=30, data_prazo=date(2026, 4, 10)
    )
    await intimacoes.aceitar_prazo(
        com_id="com-1", payload=payload, db=db, cu=_user()
    )
    d = next(o for o in db.added if isinstance(o, Deadline))
    assert d.data_prazo == date(2026, 4, 10)


@pytest.mark.anyio
async def test_dias_recalcula_a_partir_da_disponibilizacao(monkeypatch):
    from app.routers import intimacoes
    from app.services.deadline_calculator import prazo_dias_uteis

    _liberar_caso(monkeypatch)
    db = _FakeDB([_com()])
    await intimacoes.aceitar_prazo(
        com_id="com-1",
        payload=intimacoes.AceitarPrazoRequest(dias=10),
        db=db, cu=_user(),
    )
    d = next(o for o in db.added if isinstance(o, Deadline))
    # Dias ÚTEIS forenses — nunca soma corrida (a diferença é o que precluí).
    assert d.data_prazo == prazo_dias_uteis(date(2026, 3, 2), 10, tribunal="TJMG")


@pytest.mark.anyio
async def test_responsavel_default_e_o_advogado_da_intimacao(monkeypatch):
    from app.routers import intimacoes

    _liberar_caso(monkeypatch)
    db = _FakeDB([_com(advogado_id="adv-1")])
    await intimacoes.aceitar_prazo(
        com_id="com-1", payload=None, db=db, cu=_user(UserRole.socio, "socio-9")
    )
    d = next(o for o in db.added if isinstance(o, Deadline))
    # Quem foi intimado responde pelo prazo — não quem clicou.
    assert d.responsavel_id == "adv-1"


# ── Recusas seguras (422) — nunca criar prazo sem base ───────────────────────

@pytest.mark.anyio
async def test_intimacao_sem_caso_nao_gera_prazo_orfao(monkeypatch):
    from app.routers import intimacoes

    _liberar_caso(monkeypatch)
    db = _FakeDB([_com(case_id=None)])
    with pytest.raises(HTTPException) as ei:
        await intimacoes.aceitar_prazo(com_id="com-1", payload=None, db=db, cu=_user())
    assert ei.value.status_code == 422
    assert db.added == []


@pytest.mark.anyio
async def test_sem_disponibilizacao_e_sem_override_recusa(monkeypatch):
    from app.routers import intimacoes

    _liberar_caso(monkeypatch)
    db = _FakeDB([_com(data_disponibilizacao=None)])
    with pytest.raises(HTTPException) as ei:
        await intimacoes.aceitar_prazo(com_id="com-1", payload=None, db=db, cu=_user())
    assert ei.value.status_code == 422
    assert db.added == []


@pytest.mark.anyio
async def test_sem_disponibilizacao_aceita_data_absoluta(monkeypatch):
    """Escape hatch: sem termo inicial, o advogado ainda pode informar a data."""
    from app.routers import intimacoes

    _liberar_caso(monkeypatch)
    db = _FakeDB([_com(data_disponibilizacao=None)])
    await intimacoes.aceitar_prazo(
        com_id="com-1",
        payload=intimacoes.AceitarPrazoRequest(data_prazo=date(2026, 4, 10)),
        db=db, cu=_user(),
    )
    d = next(o for o in db.added if isinstance(o, Deadline))
    assert d.data_prazo == date(2026, 4, 10)


@pytest.mark.anyio
async def test_dias_sem_disponibilizacao_recusa(monkeypatch):
    from app.routers import intimacoes

    _liberar_caso(monkeypatch)
    db = _FakeDB([_com(data_disponibilizacao=None)])
    with pytest.raises(HTTPException) as ei:
        await intimacoes.aceitar_prazo(
            com_id="com-1",
            payload=intimacoes.AceitarPrazoRequest(dias=10),
            db=db, cu=_user(),
        )
    assert ei.value.status_code == 422


# ── Recusa explícita ─────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_recusar_marca_status_e_nao_cria_prazo(monkeypatch):
    from app.routers import intimacoes

    _liberar_caso(monkeypatch)
    com = _com()
    db = _FakeDB([com])
    out = await intimacoes.recusar_prazo(com_id="com-1", db=db, cu=_user())
    assert out["prazo_sugerido_status"] == "recusado"
    assert com.prazo_sugerido_status == "recusado"
    assert [o for o in db.added if isinstance(o, Deadline)] == []
