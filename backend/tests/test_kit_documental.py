"""Kit documental inicial (P0.3) — POST /cases/{case_id}/kit-documental.

Sem Postgres real (padrão test_provas.py): handlers chamados diretamente com
fake de sessão. Cobre: kit completo (procuração + contrato + checklist, sempre
RASCUNHO + auditoria), caso sem item OAB aplicável ("a definir" — nunca
inventar valor), poderes especiais do art. 105 só quando marcados, e
permissão negada para papéis abaixo de advogado.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.models.audit_log import AuditLog
from app.models.case import Case
from app.models.client import Client
from app.models.legal_doc import LegalDoc, PecaStatus, PecaTipo
from app.models.procuracao import Procuracao
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
    """Sessão fake: fila de resultados para execute(); registra add/commit.
    `gets` mapeia (NomeModelo, pk) → objeto para db.get()."""

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


def _user(role: UserRole, uid: str = "u1") -> User:
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


# ── Rotas montadas ────────────────────────────────────────────────────────────

def test_rota_montada_em_main():
    from app.main import app
    paths = {getattr(r, "path", "") for r in app.routes}
    assert any(p.endswith("/cases/{case_id}/kit-documental") for p in paths)


# ── Gate de papel (advogado+) ────────────────────────────────────────────────

def test_req_advogado_barra_roles_baixas():
    from app.routers.kit_documental import _req_advogado
    for role in (UserRole.estagiario, UserRole.secretaria,
                 UserRole.advogado_auxiliar, UserRole.cliente_externo):
        with pytest.raises(HTTPException) as exc:
            _req_advogado(_user(role))
        assert exc.value.status_code == 403
    # advogado e sócio passam
    assert _req_advogado(_user(UserRole.advogado)).role == UserRole.advogado
    assert _req_advogado(_user(UserRole.socio)).role == UserRole.socio


def test_tipo_poderes_invalido_rejeitado():
    from app.routers.kit_documental import KitDocumentalIn
    with pytest.raises(ValidationError):
        KitDocumentalIn(tipo_poderes="plenos_poderes")


# ── Kit completo ─────────────────────────────────────────────────────────────

async def test_kit_completo_gera_tres_rascunhos_procuracao_e_auditoria():
    from app.routers.kit_documental import gerar_kit_documental

    # execute #1: caso (verificar_acesso_caso); execute #2: itens OAB vigentes;
    # execute #3: proposta de honorários aprovada vigente (FASE 4 — None = sem
    # proposta, contrato mantém placeholders)
    db = _FakeDB([_case(), [_item_oab()], None], gets={("Client", "cli1"): _cli()})
    out = await gerar_kit_documental(case_id="case1", payload=None,
                                     db=db, cu=_user(UserRole.advogado))

    assert out["status"] == "rascunho"
    # 3 LegalDocs, todos RASCUNHO e pendentes de revisão humana (HITL)
    docs = [o for o in db.added if isinstance(o, LegalDoc)]
    assert len(docs) == 3
    assert all(d.status == PecaStatus.rascunho for d in docs)
    assert all(d.human_reviewed is False for d in docs)
    assert all(d.case_id == "case1" for d in docs)
    assert {d.tipo_peca for d in docs} == {PecaTipo.procuracao, PecaTipo.contrato, PecaTipo.outro}

    # Procuração: SÓ a minuta (defaults conservadores, sem art. 105). O registro
    # formal Procuracao NÃO nasce aqui — senão satisfaria o gate "procuração
    # vigente" dos checklists sem qualquer outorga do cliente (achado Médio da
    # auditoria de segurança).
    procs = [o for o in db.added if isinstance(o, Procuracao)]
    assert procs == []
    assert out["procuracao"]["tipo_poderes"] == "ad_judicia"
    assert "pendente de assinatura" in out["procuracao"]["aviso"]
    assert "PROCURACAO AD JUDICIA" in out["procuracao"]["conteudo"]
    assert "renunciar" not in out["procuracao"]["conteudo"].lower()

    # Contrato: referência REAL da tabela OAB, valor contratado segue placeholder
    contrato = out["contrato"]
    assert contrato["valor_sugerido"]["origem"] == "tabela_oab_estruturada"
    assert contrato["valor_sugerido"]["sugerido"]["item_codigo"] == "11.5"
    assert contrato["valor_sugerido"]["sugerido"]["fonte"].startswith("Tabela de Honorarios OAB/MG")
    assert "item 11.5" in contrato["conteudo"]
    assert "R$ [____]" in contrato["conteudo"]  # advogado define o valor final

    # Checklist por área (familia) + itens base
    check = out["checklist"]["conteudo"]
    assert "( ) Procuracao assinada" in check
    assert "( ) Certidoes de nascimento dos filhos" in check

    # Auditoria obrigatória + transação única
    audits = [o for o in db.added if isinstance(o, AuditLog)]
    assert any(a.acao == "KIT_DOCUMENTAL" and a.entidade == "cases"
               and a.registro_id == "case1" for a in audits)
    assert db.commits == 1


async def test_kit_sem_item_oab_aplicavel_fica_a_definir():
    from app.routers.kit_documental import gerar_kit_documental

    db = _FakeDB([_case(area="transito"), [], None], gets={("Client", "cli1"): _cli()})
    out = await gerar_kit_documental(case_id="case1", payload=None,
                                     db=db, cu=_user(UserRole.socio))

    vs = out["contrato"]["valor_sugerido"]
    assert vs["origem"] is None and vs["sugerido"] is None
    assert vs["itens_referencia"] == []
    # Nunca inventar valor: contrato traz "A DEFINIR" explícito + placeholder
    assert "A DEFINIR" in out["contrato"]["conteudo"]
    assert "R$ [____]" in out["contrato"]["conteudo"]


async def test_poderes_especiais_art_105_so_quando_marcados():
    from app.routers.kit_documental import KitDocumentalIn, gerar_kit_documental

    db = _FakeDB([_case(), [], None], gets={("Client", "cli1"): _cli()})
    out = await gerar_kit_documental(
        case_id="case1",
        payload=KitDocumentalIn(tipo_poderes="ad_judicia_et_extra",
                                permite_substabelecimento=False),
        db=db, cu=_user(UserRole.advogado),
    )
    conteudo = out["procuracao"]["conteudo"].lower()
    assert "renunciar" in conteudo               # art. 105 marcado explicitamente
    assert "substabelecer" not in conteudo       # substab não autorizado
    # Nenhum registro formal Procuracao — só a minuta com os poderes marcados
    assert [o for o in db.added if isinstance(o, Procuracao)] == []
    assert out["procuracao"]["tipo_poderes"] == "ad_judicia_et_extra"
    assert out["procuracao"]["permite_substabelecimento"] is False


async def test_cliente_inexistente_404():
    from app.routers.kit_documental import gerar_kit_documental

    db = _FakeDB([_case()], gets={})  # db.get(Client) → None
    with pytest.raises(HTTPException) as exc:
        await gerar_kit_documental(case_id="case1", payload=None,
                                   db=db, cu=_user(UserRole.advogado))
    assert exc.value.status_code == 404


def test_alias_civil_cobre_grafia_civel_do_seed():
    from app.services.geracao_documental import _aliases_area
    assert _aliases_area("civil") == ["civil", "civel"]
    assert _aliases_area("familia") == ["familia"]
