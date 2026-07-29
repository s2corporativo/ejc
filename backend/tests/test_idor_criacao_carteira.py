"""Regressão da CLASSE de IDOR: entidade carregada por ID do usuário sem gate.

O bug de referência foi `legal_chat_service.converter_em_caso`, que carregava
`payload.client_id` com `db.get()` sem verificar a carteira. Como
`core/client_ownership.pode_ver_cliente` concede acesso a quem é responsável
por um caso do cliente, criar um caso com UUID alheio FABRICAVA esse vínculo e
liberava o cliente de outra carteira permanentemente (dossiê, CPF/CNPJ,
procurações, data room). Não é write indevido — é escalonamento de privilégio.

A varredura da classe encontrou os mesmos sintomas em três outros pontos, todos
cobertos aqui:

  1. `cases.criar` ............ porta da FRENTE da criação de casos
  2. `ai.visual_law` ............... leitura do dossiê de qualquer caso
  3. `signatures.criar_solicitacao`. documento/cliente de outra carteira

Padrão do repo: sem banco real — fakes de sessão por arquivo e chamada direta
do handler, com o gate canônico monkeypatchado para negar (é ele que decide,
e já tem cobertura própria em test_ownership.py).
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.models.user import User, UserRole


def _user(role: UserRole = UserRole.advogado, uid: str = "adv-a") -> User:
    u = User(id=uid, email=f"{uid}@ejc.adv.br", full_name="Advogado A", role=role)
    u.is_active = True
    return u


class _DBVazio:
    """Sessão fake: o handler não deve chegar a usar nada dela — o gate barra
    antes. Qualquer uso inesperado estoura e denuncia o teste frouxo."""

    async def execute(self, *a, **k):
        raise AssertionError("gate deveria ter barrado antes de qualquer query")

    async def get(self, *a, **k):
        raise AssertionError("gate deveria ter barrado antes de qualquer get")

    def add(self, *a, **k):
        raise AssertionError("nada pode ser gravado quando o gate barra")

    async def commit(self):
        raise AssertionError("nada pode ser commitado quando o gate barra")


def _negar_cliente():
    async def _fake(db, user, client_id):
        # Contrato canônico: 404 uniforme — não confirma que o UUID existe.
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return _fake


def _negar_caso():
    async def _fake(db, user, case_id):
        raise HTTPException(status_code=403, detail="Sem acesso a este caso")
    return _fake


# ── 1. cases.criar ──────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_criar_caso_com_client_id_de_outra_carteira_404(monkeypatch):
    """Sem o gate, o caso nasceria com `advogado_responsavel_id = cu.id` e o
    vínculo criado liberaria o cliente alheio para sempre."""
    import app.core.client_ownership as co
    from app.routers import cases

    monkeypatch.setattr(co, "obter_cliente_autorizado", _negar_cliente())

    payload = cases.CaseCreate(
        titulo="Caso forjado",
        client_id="cliente-de-outra-carteira",
        area="civil",
        proxima_acao="Analisar documentos",
    )
    with pytest.raises(HTTPException) as ei:
        await cases.criar(
            payload, background=None, db=_DBVazio(), cu=_user(),
        )
    assert ei.value.status_code == 404
    # 404 uniforme: a mensagem não pode confirmar existência do UUID alheio.
    assert "não encontrado" in str(ei.value.detail).lower()


def test_criar_caso_usa_o_gate_canonico():
    """Trava a correção contra regressão silenciosa (voltar ao select cru)."""
    import inspect

    from app.routers import cases

    fonte = inspect.getsource(cases.criar)
    assert "obter_cliente_autorizado" in fonte
    # O padrão antigo (só existência, 422) não pode voltar.
    assert 'status_code=422, detail="Cliente não encontrado"' not in fonte


# ── 2. ai.visual_law ─────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_visual_law_de_caso_alheio_barra(monkeypatch):
    """O diagrama materializa o dossiê (partes, cronologia, prazos, valores):
    exige o mesmo vínculo que os endpoints irmãos do arquivo já exigiam."""
    import app.core.ownership as own
    from app.routers import ai as ai_router

    monkeypatch.setattr(own, "verificar_acesso_caso", _negar_caso())

    with pytest.raises(HTTPException) as ei:
        await ai_router.visual_law(
            case_id="caso-de-outra-carteira",
            req=ai_router.VisualLawReq(tipo="partes"),
            db=_DBVazio(),
            cu=_user(UserRole.estagiario, "est-1"),
        )
    assert ei.value.status_code in (403, 404)


def test_visual_law_usa_o_gate_canonico():
    import inspect

    from app.routers import ai as ai_router

    assert "verificar_acesso_caso" in inspect.getsource(ai_router.visual_law)


# ── 3. signatures.criar_solicitacao ──────────────────────────────────────────

def test_criar_solicitacao_assinatura_usa_gates_de_titularidade():
    """A checagem doc↔cliente que já existia NÃO diz nada sobre a carteira de
    quem pede — sem estes gates, o requisitante recebia título do documento e
    nome/e-mail dos logins do portal do cliente alheio, e ainda notificava a
    área dele."""
    import inspect

    from app.routers import signatures

    fonte = inspect.getsource(signatures.criar_solicitacao)
    assert "obter_cliente_autorizado" in fonte
    assert "verificar_acesso_caso" in fonte
    # A coerência doc↔cliente continua valendo (não foi substituída).
    assert "não pertence a este cliente" in fonte
