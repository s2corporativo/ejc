"""FASE 4 — Proposta de Honorários imutável + contrato completo por template.

Sem Postgres real (padrão test_kit_documental.py): services/handlers chamados
diretamente com fake de sessão. Cobre: sugestão determinística com/sem item OAB
(sem item → None, NUNCA inventa valor), versionamento (max+1), imutabilidade da
proposta aprovada (mudança = nova versão; anterior aprovada → "substituida"),
aprovação/rejeição HITL com auditoria, contrato completo só com proposta
APROVADA (sem proposta → placeholders atuais, byte-idênticos) e integração do
kit documental com a proposta vigente.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.models.audit_log import AuditLog
from app.models.case import Case
from app.models.client import Client
from app.models.fee_proposal import FeeProposal
from app.models.redesign import TabelaOABHonorario
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
    """Sessão fake: fila de resultados para execute(); registra add/commit."""

    def __init__(self, resultados: list, gets: dict | None = None):
        self._resultados = list(resultados)
        self.gets = gets or {}
        self.added: list = []
        self.commits = 0

    async def execute(self, *a, **k):
        return _Res(self._resultados.pop(0))

    async def get(self, model, pk):
        return self.gets.get((model.__name__, pk))

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


def _user(role: UserRole = UserRole.advogado, uid: str = "u1") -> User:
    return User(id=uid, role=role, full_name="Dra. Fulana")


def _cli() -> Client:
    return Client(id="cli1", nome="Joao da Silva", cpf="00000000000")


def _case(**kw) -> Case:
    base = dict(id="case1", titulo="Guarda dos Filhos", client_id="cli1",
                area="familia", numero_processo=None, numero_interno="DPT-2026-0001",
                advogado_responsavel_id=None, advogado_auxiliar_id=None,
                deleted_at=None)
    base.update(kw)
    return Case(**base)


def _item_oab(**kw) -> TabelaOABHonorario:
    base = dict(id="t1", item_codigo="11.5", descricao="com alimentos, guarda,",
                area_juridica="familia", valor_minimo=10000.0, percentual=10.0,
                unidade="R$", vigencia_inicio=None, vigencia_fim=None,
                fonte="Tabela de Honorarios OAB/MG (PDF institucional)",
                observacoes=None, ativo=True)
    base.update(kw)
    return TabelaOABHonorario(**base)


def _proposta(**kw) -> FeeProposal:
    base = dict(
        id="prop1", case_id="case1", versao=1, status="rascunho",
        origem_tabela={"item_codigo": "11.5"},
        faixas={
            "minimo_etico": {"valor": 10000.0, "memoria_calculo": "verbatim OAB"},
            "recomendado": {"valor": 15000.0, "memoria_calculo": "10000 x 1.5"},
            "estrategico": {"valor": 20000.0, "memoria_calculo": "10000 x 2.0"},
        },
        exito_percentual=30.0,
        parcelamento={"entrada": 5000.0, "num_parcelas": 5, "valor_parcela": 2000.0},
        despesas_criterio=None, justificativa="caso padrao",
        criado_por="u1", criado_em=datetime.now(timezone.utc),
        aprovado_por=None, aprovado_em=None,
    )
    base.update(kw)
    return FeeProposal(**base)


# ── Rotas montadas e gate de papel ───────────────────────────────────────────

def test_rotas_proposta_montadas_em_main():
    from app.main import app
    paths = {getattr(r, "path", "") for r in app.routes}
    assert any(p.endswith("/honorarios-oab/casos/{case_id}/proposta/sugerir") for p in paths)
    assert any(p.endswith("/honorarios-oab/casos/{case_id}/proposta") for p in paths)
    assert any(p.endswith("/honorarios-oab/propostas/{proposta_id}/aprovar") for p in paths)
    assert any(p.endswith("/honorarios-oab/propostas/{proposta_id}/rejeitar") for p in paths)


def test_req_advogado_barra_roles_baixas():
    from app.routers.honorarios_oab import _req_advogado
    for role in (UserRole.estagiario, UserRole.secretaria,
                 UserRole.advogado_auxiliar, UserRole.cliente_externo):
        with pytest.raises(HTTPException) as exc:
            _req_advogado(_user(role))
        assert exc.value.status_code == 403
    assert _req_advogado(_user(UserRole.advogado)).role == UserRole.advogado
    assert _req_advogado(_user(UserRole.socio)).role == UserRole.socio


# ── Sugestão determinística ──────────────────────────────────────────────────

async def test_sugerir_com_item_oab_multiplicadores_fixos():
    from app.services.fee_proposal_service import sugerir_proposta

    db = _FakeDB([[_item_oab()]])
    out = await sugerir_proposta(db, _case(), "familia")

    # Mínimo ético VERBATIM do item OAB; origem verbatim com fonte/vigência
    assert out["origem_tabela"]["item_codigo"] == "11.5"
    assert out["origem_tabela"]["fonte"].startswith("Tabela de Honorarios OAB/MG")
    fx = out["faixas"]
    assert fx["minimo_etico"]["valor"] == 10000.0
    assert "VERBATIM" in fx["minimo_etico"]["memoria_calculo"]
    # Sem campo complexidade no Case → fator 1.0: 1.5x e 2.0x fixos
    assert fx["recomendado"]["valor"] == 15000.0
    assert fx["estrategico"]["valor"] == 20000.0
    # Memória de cálculo explícita
    assert "1.5" in fx["recomendado"]["memoria_calculo"]
    assert "2" in fx["estrategico"]["memoria_calculo"]
    # Nada é persistido
    assert db.added == [] and db.commits == 0


async def test_sugerir_fator_complexidade_alta():
    from app.services.fee_proposal_service import sugerir_proposta

    case = _case()
    case.complexidade = "alta"  # fator fixo 1.5
    db = _FakeDB([[_item_oab()]])
    out = await sugerir_proposta(db, case, "familia")
    assert out["faixas"]["minimo_etico"]["valor"] == 10000.0     # verbatim, sem fator
    assert out["faixas"]["recomendado"]["valor"] == 22500.0      # 10000 x 1.5 x 1.5
    assert out["faixas"]["estrategico"]["valor"] == 30000.0      # 10000 x 2.0 x 1.5
    assert "alta" in out["faixas"]["recomendado"]["memoria_calculo"]


async def test_sugerir_sem_item_oab_nunca_inventa():
    from app.services.fee_proposal_service import sugerir_proposta

    db = _FakeDB([[]])
    out = await sugerir_proposta(db, _case(area="transito"), "transito")
    assert out["origem_tabela"] is None
    for faixa in out["faixas"].values():
        assert faixa["valor"] is None
    assert "sem base OAB" in out["aviso"]
    assert "não preencher automaticamente" in out["aviso"]


async def test_sugerir_item_so_percentual_sem_base_monetaria():
    from app.services.fee_proposal_service import sugerir_proposta

    db = _FakeDB([[_item_oab(valor_minimo=None, percentual=20.0)]])
    out = await sugerir_proposta(db, _case(), "familia")
    # Item existe (origem verbatim), mas SEM base monetária → nada calculado
    assert out["origem_tabela"]["percentual"] == 20.0
    for faixa in out["faixas"].values():
        assert faixa["valor"] is None
    assert "sem base OAB" in out["aviso"]


# ── Versionamento / criação de rascunho ──────────────────────────────────────

async def test_criar_proposta_versao_incremental_e_auditoria():
    from app.services.fee_proposal_service import criar_proposta

    db = _FakeDB([2])  # max(versao) do caso = 2
    p = await criar_proposta(db, "case1", _user(), {
        "faixas": {"minimo_etico": {"valor": 10000.0, "memoria_calculo": "m"}},
        "justificativa": "ajuste",
    })
    assert p.versao == 3 and p.status == "rascunho"
    assert p.criado_por == "u1"
    assert p in db.added
    audits = [o for o in db.added if isinstance(o, AuditLog)]
    assert any(a.acao == "CREATE" and a.entidade == "fee_proposals" for a in audits)
    assert db.commits == 1


async def test_criar_proposta_primeira_versao():
    from app.services.fee_proposal_service import criar_proposta

    db = _FakeDB([None])  # caso sem propostas
    p = await criar_proposta(db, "case1", _user(), {"faixas": {}})
    assert p.versao == 1


async def test_criar_proposta_barra_roles_baixas():
    from app.services.fee_proposal_service import criar_proposta

    with pytest.raises(HTTPException) as exc:
        await criar_proposta(_FakeDB([0]), "case1", _user(UserRole.estagiario), {})
    assert exc.value.status_code == 403


# ── Aprovação HITL / imutabilidade / substituição ────────────────────────────

async def test_aprovar_congela_e_substitui_anteriores():
    from app.services.fee_proposal_service import aprovar

    nova = _proposta(id="prop2", versao=2)
    antiga = _proposta(id="prop1", versao=1, status="aprovada",
                       aprovado_por="u9", aprovado_em=datetime.now(timezone.utc))
    # execute #1: proposta; execute #2: aprovadas anteriores do caso
    db = _FakeDB([nova, [antiga]])
    p = await aprovar(db, "prop2", _user())

    assert p.status == "aprovada"
    assert p.aprovado_por == "u1" and p.aprovado_em is not None
    assert antiga.status == "substituida"          # no máximo 1 aprovada vigente
    audits = [o for o in db.added if isinstance(o, AuditLog)]
    assert any(a.acao == "APROVAR" and a.entidade == "fee_proposals"
               and a.registro_id == "prop2" for a in audits)
    assert db.commits == 1


async def test_aprovada_e_imutavel_409():
    from app.services.fee_proposal_service import aprovar, rejeitar

    for status in ("aprovada", "rejeitada", "substituida"):
        with pytest.raises(HTTPException) as exc:
            await aprovar(_FakeDB([_proposta(status=status)]), "prop1", _user())
        assert exc.value.status_code == 409
        with pytest.raises(HTTPException) as exc:
            await rejeitar(_FakeDB([_proposta(status=status)]), "prop1", _user())
        assert exc.value.status_code == 409


async def test_aprovar_inexistente_404_e_role_baixa_403():
    from app.services.fee_proposal_service import aprovar

    with pytest.raises(HTTPException) as exc:
        await aprovar(_FakeDB([None]), "nada", _user())
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        await aprovar(_FakeDB([_proposta()]), "prop1", _user(UserRole.secretaria))
    assert exc.value.status_code == 403


async def test_rejeitar_rascunho_com_auditoria():
    from app.services.fee_proposal_service import rejeitar

    db = _FakeDB([_proposta()])
    p = await rejeitar(db, "prop1", _user(), motivo="valores revisados")
    assert p.status == "rejeitada"
    audits = [o for o in db.added if isinstance(o, AuditLog)]
    assert any(a.acao == "REJEITAR" and "valores revisados" in (a.detalhes or "")
               for a in audits)
    assert db.commits == 1


async def test_proposta_aprovada_vigente():
    from app.services.fee_proposal_service import proposta_aprovada_vigente

    aprovada = _proposta(status="aprovada")
    assert await proposta_aprovada_vigente(_FakeDB([aprovada]), "case1") is aprovada
    assert await proposta_aprovada_vigente(_FakeDB([None]), "case1") is None


# ── Ponte proposta → contrato ────────────────────────────────────────────────

def test_proposta_para_contrato_exige_aprovada():
    from app.services.fee_proposal_service import proposta_para_contrato

    with pytest.raises(HTTPException) as exc:
        proposta_para_contrato(_proposta(status="rascunho"))
    assert exc.value.status_code == 409

    params = proposta_para_contrato(_proposta(status="aprovada"))
    assert params["valor"] == 15000.0                 # faixa "recomendado"
    assert params["exito_percentual"] == 30.0
    assert "entrada de R$ 5,000.00" in params["forma_pagamento"]
    assert "5 parcelas mensais de R$ 2,000.00" in params["forma_pagamento"]


def test_proposta_para_contrato_fallback_minimo_e_sem_valor():
    from app.services.fee_proposal_service import proposta_para_contrato

    p = _proposta(status="aprovada",
                  faixas={"minimo_etico": {"valor": 8000.0, "memoria_calculo": "m"}})
    assert proposta_para_contrato(p)["valor"] == 8000.0
    # Sem valor em NENHUMA faixa → None (contrato mantém placeholder, nunca inventa)
    p2 = _proposta(status="aprovada", faixas={}, parcelamento=None)
    params = proposta_para_contrato(p2)
    assert params["valor"] is None
    assert params["forma_pagamento"] == "a vista, na assinatura deste contrato"


# ── Contrato: sem proposta = placeholders atuais; com proposta = completo ────

def _contrato(**kw) -> str:
    from app.services.documental import _contrato_honorarios
    return _contrato_honorarios(_case(), _cli(), "Dra. Fulana", "familia", **kw)


def test_contrato_sem_proposta_mantem_placeholders_byte_identico():
    base = _contrato()
    # proposta=None explícito == comportamento default (mudança aditiva)
    assert _contrato(proposta=None) == base
    assert "R$ [____]" in base
    assert "[__]% sobre o proveito economico" in base
    assert "Comarca de [____]/MG" in base
    # Nenhuma cláusula nova vaza para o fluxo sem proposta
    for marcador in ("LGPD", "RESCISAO", "INADIMPLEMENTO", "COMUNICACAO ELETRONICA"):
        assert marcador not in base


def test_contrato_com_proposta_aprovada_sai_completo():
    from app.core.config import get_settings
    from app.services.fee_proposal_service import proposta_para_contrato

    params = proposta_para_contrato(_proposta(status="aprovada"))
    txt = _contrato(referencia_oab="item 11.5", proposta=params)

    s = get_settings()
    assert "R$ 15,000.00" in txt                      # valor da proposta aprovada
    assert "R$ [____]" not in txt                     # sem placeholder de valor
    assert "30% sobre o proveito economico" in txt    # êxito da proposta
    assert "entrada de R$ 5,000.00" in txt            # parcelamento
    assert "proposta de honorarios aprovada (versao 1)" in txt
    # Cláusulas fixas de template (determinísticas, sem LLM)
    for marcador in ("RESCISAO", "INADIMPLEMENTO", "REVOGACAO E RENUNCIA",
                     "LGPD", "COMUNICACAO ELETRONICA"):
        assert marcador in txt
    # Foro na comarca do escritório (settings), não placeholder
    assert f"Comarca de {s.ESCRITORIO_CIDADE}/{s.ESCRITORIO_ESTADO}" in txt
    assert "Comarca de [____]/MG" not in txt


def test_contrato_proposta_sem_valor_mantem_placeholder_de_valor():
    txt = _contrato(proposta={"versao": 2, "valor": None,
                              "forma_pagamento": "a vista, na assinatura deste contrato",
                              "exito_percentual": None, "despesas_criterio": None})
    assert "R$ [____]" in txt                         # nunca inventar valor
    assert "Nao foram ajustados honorarios de exito" in txt
    assert "LGPD" in txt


# ── Kit documental integra a proposta vigente ────────────────────────────────

async def test_kit_usa_proposta_aprovada_vigente():
    from app.routers.kit_documental import gerar_kit_documental

    aprovada = _proposta(status="aprovada", aprovado_por="u1",
                         aprovado_em=datetime.now(timezone.utc))
    # execute #1: caso; #2: itens OAB; #3: proposta aprovada vigente
    db = _FakeDB([_case(), [_item_oab()], aprovada],
                 gets={("Client", "cli1"): _cli()})
    out = await gerar_kit_documental(case_id="case1", payload=None,
                                     db=db, cu=_user(UserRole.advogado))

    contrato = out["contrato"]
    assert contrato["proposta_aprovada"]["id"] == "prop1"
    assert contrato["proposta_aprovada"]["versao"] == 1
    assert contrato["proposta_aprovada"]["valor"] == 15000.0
    assert "R$ 15,000.00" in contrato["conteudo"]
    assert "R$ [____]" not in contrato["conteudo"]
    assert "LGPD" in contrato["conteudo"]
    # Referência OAB continua presente (sugestão não vinculante)
    assert contrato["valor_sugerido"]["origem"] == "tabela_oab_estruturada"


async def test_kit_sem_proposta_mantem_comportamento_atual():
    from app.routers.kit_documental import gerar_kit_documental

    db = _FakeDB([_case(), [_item_oab()], None],
                 gets={("Client", "cli1"): _cli()})
    out = await gerar_kit_documental(case_id="case1", payload=None,
                                     db=db, cu=_user(UserRole.advogado))
    contrato = out["contrato"]
    assert contrato["proposta_aprovada"] is None
    assert "R$ [____]" in contrato["conteudo"]        # placeholders preservados
    assert "LGPD" not in contrato["conteudo"]
