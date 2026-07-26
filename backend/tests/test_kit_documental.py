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

    async def refresh(self, obj):
        pass

    async def rollback(self):
        pass


class _FakeSessionCtx:
    """Faz um _FakeDB posar de `async with AsyncSessionLocal() as db` (usado
    para exercitar background tasks que abrem a própria sessão)."""

    def __init__(self, db: _FakeDB):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *exc):
        return False


class _FakeBackground:
    """BackgroundTasks fake: registra (fn, args, kwargs) de cada add_task."""

    def __init__(self):
        self.tasks: list = []

    def add_task(self, fn, *args, **kwargs):
        self.tasks.append((fn, args, kwargs))


def _user(role: UserRole, uid: str = "u1") -> User:
    return User(id=uid, role=role, full_name="Dra. Fulana")


def _cli() -> Client:
    # Cutover C6/LGPD: documento vive cifrado; a qualificação decifra (cpf_plain).
    from app.services.pii_crypto import encrypt
    return Client(id="cli1", nome="Joao da Silva", cpf_enc=encrypt("00000000000"))


def _case(**kw) -> Case:
    # Responsável = "u1" (o mesmo uid do _user default): o advogado que gera o
    # kit é o dono do caso — happy-path autorizado e realista. Necessário após o
    # hardening do gate: caso ÓRFÃO (sem responsável) só é acessível à gestão, e
    # estes testes exercitam a geração do kit, não o gate de ownership. Passe
    # advogado_responsavel_id=None explicitamente se precisar de um caso órfão.
    base = dict(id="case1", titulo="Guarda dos Filhos", client_id="cli1",
                area="familia", numero_processo=None, numero_interno="DPT-2026-0001",
                advogado_responsavel_id="u1", advogado_auxiliar_id=None,
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

    # execute #1: caso (verificar_acesso_caso); execute #2: kit já existente
    # (dedup idempotente — [] = não existe); execute #3: itens OAB vigentes;
    # execute #4: proposta de honorários aprovada vigente (FASE 4 — None = sem
    # proposta, contrato mantém placeholders)
    db = _FakeDB([_case(), [], [_item_oab()], None], gets={("Client", "cli1"): _cli()})
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

    db = _FakeDB([_case(area="transito"), [], [], None],
                 gets={("Client", "cli1"): _cli()})
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

    db = _FakeDB([_case(), [], [], None], gets={("Client", "cli1"): _cli()})
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


# ── Idempotência (follow-up PR #283) ─────────────────────────────────────────

def _kit_existente(case) -> list[LegalDoc]:
    """Os 3 rascunhos do kit com os MESMOS títulos que o service gera."""
    from app.services.document_format import padronizar_documento_juridico as pdj

    def _d(did, prefixo, tipo):
        return LegalDoc(id=did, titulo=pdj(prefixo + case.titulo)[:200],
                        tipo_peca=tipo, status=PecaStatus.rascunho,
                        conteudo=f"conteudo {did}", case_id=case.id,
                        created_by="u0", human_reviewed=False, deleted_at=None)

    return [
        _d("d-proc", "Procuracao - ", PecaTipo.procuracao),
        _d("d-cont", "Contrato de Honorarios - ", PecaTipo.contrato),
        _d("d-chk", "Checklist Documental Inicial - ", PecaTipo.outro),
    ]


async def test_kit_ja_existente_nao_duplica_e_devolve_ja_existia():
    from app.routers.kit_documental import gerar_kit_documental

    case = _case()
    # execute #1: caso; execute #2: dedup encontra os 3 rascunhos do kit
    db = _FakeDB([case, _kit_existente(case)], gets={("Client", "cli1"): _cli()})
    out = await gerar_kit_documental(case_id="case1", payload=None,
                                     db=db, cu=_user(UserRole.advogado))

    assert out["ja_existia"] is True
    assert out["status"] == "rascunho"
    assert out["procuracao"]["legal_doc_id"] == "d-proc"
    assert out["contrato"]["legal_doc_id"] == "d-cont"
    assert out["checklist"]["legal_doc_id"] == "d-chk"
    assert "forcar_novo" in out["aviso"]
    # NADA criado, auditado ou commitado — dedup é somente leitura
    assert db.added == [] and db.commits == 0


async def test_kit_parcial_nao_conta_como_existente():
    from app.routers.kit_documental import gerar_kit_documental

    case = _case()
    # Só 2 dos 3 rascunhos existem → gera kit novo (fluxo normal completo)
    db = _FakeDB([case, _kit_existente(case)[:2], [_item_oab()], None],
                 gets={("Client", "cli1"): _cli()})
    out = await gerar_kit_documental(case_id="case1", payload=None,
                                     db=db, cu=_user(UserRole.advogado))
    assert out["ja_existia"] is False
    assert len([o for o in db.added if isinstance(o, LegalDoc)]) == 3
    assert db.commits == 1


async def test_forcar_novo_regenera_sem_consultar_dedup():
    from app.routers.kit_documental import KitDocumentalIn, gerar_kit_documental

    # Com forcar_novo=True a consulta de dedup NEM roda: fila volta a ser
    # caso → itens OAB → proposta (contrato de resposta do fluxo normal).
    db = _FakeDB([_case(), [_item_oab()], None], gets={("Client", "cli1"): _cli()})
    out = await gerar_kit_documental(
        case_id="case1", payload=KitDocumentalIn(forcar_novo=True),
        db=db, cu=_user(UserRole.advogado))
    assert out["ja_existia"] is False
    docs = [o for o in db.added if isinstance(o, LegalDoc)]
    assert len(docs) == 3
    assert all(d.human_reviewed is False for d in docs)   # HITL intacto
    audits = [o for o in db.added if isinstance(o, AuditLog)]
    assert any(a.acao == "KIT_DOCUMENTAL" for a in audits)  # auditoria intacta


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


# ── Paridade de gates do endpoint legado /cases/{id}/gerar-documentos ────────
# (auditoria item 5): mesmo gate advogado+ e mesmo rate limit "kit-documental"
# do kit — sem isso qualquer autenticado geraria procuração com poderes
# especiais pela rota legada.

def test_gerar_documentos_endpoint_reusa_gate_advogado_do_kit():
    import inspect
    from app.routers import cases as cases_router
    from app.routers.kit_documental import _req_advogado

    sig = inspect.signature(cases_router.gerar_documentos)
    dep = sig.parameters["cu"].default
    assert getattr(dep, "dependency", None) is _req_advogado


def test_gerar_documentos_endpoint_tem_rate_limit_na_rota():
    from app.main import app
    rotas = [r for r in app.routes
             if getattr(r, "path", "").endswith("/cases/{case_id}/gerar-documentos")]
    assert rotas and rotas[0].dependencies   # Depends(rate_limit("kit-documental", 5))


# ── Gatilho AUTOMÁTICO na abertura do caso (gerar_documentos_iniciais_auto) ───

async def test_auto_wrapper_gera_kit_poderes_gerais_e_nao_cria_registro_formal(monkeypatch):
    # (b)/(d): o wrapper de background gera o kit (procuração + contrato +
    # checklist) com a POLÍTICA CENTRAL de PODERES GERAIS (ad_judicia_et_extra),
    # tudo RASCUNHO/HITL, e NÃO cria o registro formal Procuracao.
    from app.services import case_automacao

    case = _case(advogado_responsavel_id="u1")
    # Fresh: dedup vazio → itens OAB → proposta None (contrato com placeholders)
    db = _FakeDB([[], [_item_oab()], None],
                 gets={("Case", "case1"): case, ("Client", "cli1"): _cli(),
                       ("User", "u1"): _user(UserRole.advogado, "u1")})
    monkeypatch.setattr(case_automacao, "AsyncSessionLocal", lambda: _FakeSessionCtx(db))

    await case_automacao.gerar_documentos_iniciais_auto("case1", "u1")

    docs = [o for o in db.added if isinstance(o, LegalDoc)]
    assert {d.tipo_peca for d in docs} == {PecaTipo.procuracao, PecaTipo.contrato, PecaTipo.outro}
    assert all(d.status == PecaStatus.rascunho for d in docs)
    assert all(d.human_reviewed is False and d.ai_generated is True for d in docs)  # gate HITL
    proc = next(d for d in docs if d.tipo_peca == PecaTipo.procuracao)
    # (d) política central: PODERES GERAIS + OUTORGADO fixo (sócio-titular)
    assert "AD JUDICIA ET EXTRA - PODERES GERAIS" in proc.conteudo
    assert "JOAO PEDRO RODRIGUES TEIXEIRA" in proc.conteudo
    # Item 6: NENHUM registro formal Procuracao no fluxo automático (só a minuta)
    assert [o for o in db.added if isinstance(o, Procuracao)] == []
    assert db.commits == 1


async def test_auto_wrapper_idempotente_reusa_ja_existia(monkeypatch):
    # (b) idempotência: reprocessar não duplica — o dedup encontra os 3 rascunhos
    # e devolve ja_existia (nada é criado/auditado/commitado).
    from app.services import case_automacao

    case = _case(advogado_responsavel_id="u1")
    db = _FakeDB([_kit_existente(case)],
                 gets={("Case", "case1"): case, ("Client", "cli1"): _cli(),
                       ("User", "u1"): _user(UserRole.advogado, "u1")})
    monkeypatch.setattr(case_automacao, "AsyncSessionLocal", lambda: _FakeSessionCtx(db))

    await case_automacao.gerar_documentos_iniciais_auto("case1", "u1")

    # Guarda anti-falso-positivo: o dedup REALMENTE rodou (fila consumida) e, ainda
    # assim, nada foi criado/commitado — é o caminho ja_existia, não um erro engolido.
    assert db._resultados == []
    assert [o for o in db.added if isinstance(o, LegalDoc)] == []
    assert db.commits == 0


async def test_auto_wrapper_sem_cliente_nao_derruba(monkeypatch):
    # Fail-safe: caso sem cliente não gera kit nem levanta exceção.
    from app.services import case_automacao

    case = _case(client_id=None, advogado_responsavel_id="u1")
    db = _FakeDB([], gets={("Case", "case1"): case,
                           ("User", "u1"): _user(UserRole.advogado, "u1")})
    monkeypatch.setattr(case_automacao, "AsyncSessionLocal", lambda: _FakeSessionCtx(db))

    await case_automacao.gerar_documentos_iniciais_auto("case1", "u1")
    assert db.added == [] and db.commits == 0


async def test_abertura_de_caso_agenda_gerar_documentos_iniciais_auto():
    # (a): POST /cases (criar) agenda o gatilho em BACKGROUND com (case_id, user_id).
    from app.routers import cases as cases_router
    from app.schemas.case import CaseCreate

    cu = _user(UserRole.advogado, "u1")
    payload = CaseCreate(titulo="Guarda dos Filhos", area="familia", client_id="cli1",
                         proxima_acao="Definir estratégia de guarda")
    # execute #1: validação do cliente (scalar_one_or_none); #2: advisory lock;
    # #3: SELECT numero_interno (scalar → None = primeiro do ano).
    db = _FakeDB([_cli(), None, None])
    bg = _FakeBackground()

    ret = await cases_router.criar(payload=payload, background=bg, db=db, cu=cu)

    case_obj = next(o for o in db.added if isinstance(o, Case))
    assert ret is case_obj
    task = next((t for t in bg.tasks
                 if t[0] is cases_router.gerar_documentos_iniciais_auto), None)
    assert task is not None, "criar() deve agendar gerar_documentos_iniciais_auto"
    assert task[1] == (case_obj.id, "u1")   # (case_id, user_id do criador)


# ── FASE 2: honorários do cadastro na abertura do caso ───────────────────────

def test_casecreate_aceita_honorarios_e_sem_honorarios():
    """(a) CaseCreate aceita o objeto `honorarios` (4 campos) e também sem ele."""
    from app.schemas.case import CaseCreate, HonorariosCreate

    # Sem honorários (legado) → None.
    c0 = CaseCreate(titulo="Guarda", area="familia", client_id="cli1")
    assert c0.honorarios is None

    # Com honorários — contrato de campos ESTÁVEL (não renomear).
    c1 = CaseCreate(titulo="Guarda", area="familia", client_id="cli1",
                    honorarios={"valor_contratual": 10000.0, "percentual_exito": 20.0,
                                "forma_pagamento": "à vista", "observacoes": "obs"})
    assert isinstance(c1.honorarios, HonorariosCreate)
    assert c1.honorarios.valor_contratual == 10000.0
    assert c1.honorarios.percentual_exito == 20.0
    assert c1.honorarios.forma_pagamento == "à vista"
    assert c1.honorarios.observacoes == "obs"

    # Todos opcionais: objeto vazio é válido (contrato seguirá com placeholders).
    assert CaseCreate(titulo="G", area="familia", client_id="cli1",
                      honorarios={}).honorarios.valor_contratual is None

    # Valores inválidos → 422 na entrada (nunca 500 no INSERT).
    with pytest.raises(ValidationError):
        CaseCreate(titulo="G", area="familia", client_id="cli1",
                   honorarios={"valor_contratual": -1})
    with pytest.raises(ValidationError):
        CaseCreate(titulo="G", area="familia", client_id="cli1",
                   honorarios={"percentual_exito": 150})


async def test_criar_caso_com_honorarios_semeia_proposta_aprovada_antes_do_kit():
    """(b)/ordem: POST /cases com `honorarios` cria a proposta APROVADA na MESMA
    transação do caso (1 commit) — existe ANTES do background do kit, que é
    agendado para rodar depois e encontrá-la."""
    from app.models.fee_proposal import FeeProposal
    from app.routers import cases as cases_router
    from app.schemas.case import CaseCreate

    cu = _user(UserRole.advogado, "u1")
    payload = CaseCreate(
        titulo="Guarda dos Filhos", area="familia", client_id="cli1",
        proxima_acao="Definir estratégia de guarda",
        honorarios={"valor_contratual": 12000.0, "percentual_exito": 25.0,
                    "forma_pagamento": "3x", "observacoes": "obs"},
    )
    # execute #1 cliente; #2 advisory lock; #3 numero_interno; então o seed:
    # #4 proposta_aprovada_vigente (idempotência → None); #5 max(versao) → None.
    db = _FakeDB([_cli(), None, None, None, None])
    bg = _FakeBackground()

    await cases_router.criar(payload=payload, background=bg, db=db, cu=cu)

    props = [o for o in db.added if isinstance(o, FeeProposal)]
    assert len(props) == 1
    p = props[0]
    assert p.status == "aprovada" and p.versao == 1
    assert p.faixas["recomendado"]["valor"] == 12000.0
    assert p.exito_percentual == 25.0
    assert p.parcelamento == {"descricao": "3x"}
    assert p.justificativa == "obs"
    # Atômico: uma única transação (caso + proposta) commitada antes do kit.
    assert db.commits == 1
    assert any(t[0] is cases_router.gerar_documentos_iniciais_auto for t in bg.tasks)


async def test_criar_caso_sem_honorarios_nao_semeia_proposta():
    """(c) Sem `honorarios`, criar() não semeia proposta (nenhum execute extra) —
    o contrato do kit seguirá com placeholders, como hoje."""
    from app.models.fee_proposal import FeeProposal
    from app.routers import cases as cases_router
    from app.schemas.case import CaseCreate

    cu = _user(UserRole.advogado, "u1")
    payload = CaseCreate(titulo="Guarda", area="familia", client_id="cli1",
                         proxima_acao="Aguardar documentos do cliente")
    db = _FakeDB([_cli(), None, None])   # exatamente os 3 executes legados
    bg = _FakeBackground()

    await cases_router.criar(payload=payload, background=bg, db=db, cu=cu)

    assert [o for o in db.added if isinstance(o, FeeProposal)] == []
    assert db._resultados == []          # nenhum execute a mais consumido
    assert db.commits == 1
