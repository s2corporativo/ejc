"""FASE 5 — LegalCaseOrchestrator (máquina de estados jurídicos).

Sem Postgres real (padrão test_fee_proposal.py): services chamados diretamente
com fake de sessão. Cobre: derivação de estado por ARTEFATOS reais (10
cenários), proximo_passo com pendências bloqueantes, avancar com whitelist
(422 ação desconhecida; 403 role baixa; atos jurídicos recusados com
instrução do endpoint humano), auditoria + snapshot por transição executada,
jornada com rótulos/status e rotas montadas no main.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.models.audit_log import AuditLog
from app.models.case import Case
from app.models.case_intelligence import (
    CaseIntelligenceSnapshot, ORIGENS_SNAPSHOT,
)
from app.models.deadline import Deadline, DeadlineStatus
from app.models.fee_proposal import FeeProposal
from app.models.legal_doc import LegalDoc, PecaStatus, PecaTipo
from app.models.matriz_teses import ThesisCandidate
from app.models.user import User, UserRole
from app.services import legal_case_orchestrator as lco


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


def _user(role: UserRole = UserRole.advogado, uid: str = "u1") -> User:
    return User(id=uid, role=role, full_name="Dra. Fulana")


def _case(**kw) -> Case:
    base = dict(id="case1", titulo="Guarda dos Filhos", client_id="cli1",
                area="familia", descricao_fatos=None,
                advogado_responsavel_id=None, advogado_auxiliar_id=None,
                deleted_at=None)
    base.update(kw)
    return Case(**base)


def _snap(versao=1, origem="intake", payload=None, congelado=False, **kw):
    base = dict(id=f"snap{versao}", case_id="case1", versao=versao,
                origem=origem, payload=payload or {"area": "familia"},
                resumo=f"snapshot v{versao}", ai_log_ids=[],
                criado_por="u1", criado_em=datetime.now(timezone.utc),
                congelado=congelado)
    base.update(kw)
    return CaseIntelligenceSnapshot(**base)


def _tese(status="candidata", tid="tese1"):
    return ThesisCandidate(id=tid, case_id="case1", tese="tese X",
                           status=status, forca=50)


def _proposta(status="rascunho", pid="prop1", versao=1):
    return FeeProposal(id=pid, case_id="case1", versao=versao, status=status,
                       faixas={}, criado_por="u1")


def _doc(tipo=PecaTipo.contestacao, status=PecaStatus.rascunho,
         titulo="Contestacao - Caso", ai=True, protocolo=None, did="doc1"):
    return LegalDoc(id=did, titulo=titulo, tipo_peca=tipo, status=status,
                    conteudo="x", case_id="case1", ai_generated=ai,
                    numero_protocolo=protocolo)


def _kit_docs():
    return [
        _doc(PecaTipo.procuracao, titulo="Procuracao - Caso", did="d-proc"),
        _doc(PecaTipo.contrato, titulo="Contrato de Honorarios - Caso", did="d-cont"),
        _doc(PecaTipo.outro, titulo="Checklist Documental Inicial - Caso", did="d-chk"),
    ]


def _deadline(confirmado=True, status=DeadlineStatus.pendente,
              origem="motor_peca", deleted_at=None):
    # origem default "motor_peca": só prazo nascido dos gates do motor/agente
    # conta como confirmado para a máquina de estados (auditoria item 11).
    return Deadline(id="dl1", titulo="Prazo — Contestação", case_id="case1",
                    confirmado=confirmado, status=status, origem=origem,
                    deleted_at=deleted_at)


def _db_artefatos(snaps=(), teses=(), propostas=(), docs=(), deadlines=(),
                  n_ocr=0, n_validacoes=0, extra=()):
    """Fila na ordem FIXA de coletar_artefatos (case passado pelo chamador):
    snapshots → teses → propostas → legal_docs → deadlines → count OCR →
    count validações de peça (esta última SÓ quando há peça de produção —
    mesma condição do service, CR-15)."""
    fila = [list(snaps), list(teses), list(propostas), list(docs),
            list(deadlines), n_ocr]
    if any(lco._eh_peca_producao(d) for d in docs):
        fila.append(n_validacoes)
    return _FakeDB(fila + list(extra))


async def _estado(db) -> str:
    return await lco.estado_atual(db, "case1", case=_case())


# ── Modelo/rotas ─────────────────────────────────────────────────────────────

def test_origem_orquestrador_registrada_em_origens_snapshot():
    assert "orquestrador" in ORIGENS_SNAPSHOT


def test_rotas_orquestrador_montadas_em_main():
    from app.main import app
    paths = {getattr(r, "path", "") for r in app.routes}
    assert any(p.endswith("/cases/{case_id}/orquestrador") for p in paths)
    assert any(p.endswith("/cases/{case_id}/orquestrador/avancar") for p in paths)


# ── Derivação de estado por artefatos (10 cenários) ──────────────────────────

async def test_estado_entrada_sem_artefatos():
    assert await _estado(_db_artefatos()) == "entrada"


async def test_estado_compreensao_com_snapshot_intake():
    assert await _estado(_db_artefatos(snaps=[_snap()])) == "compreensao"


async def test_estado_classificacao_snapshot_aprovado():
    db = _db_artefatos(snaps=[_snap(congelado=True)])
    assert await _estado(db) == "classificacao"


async def test_estado_validacao_processual_snapshot_motor_peca():
    db = _db_artefatos(snaps=[
        _snap(versao=2, origem="motor_peca",
              payload={"area": "civil", "peca_sugerida": "contestacao"}),
        _snap(versao=1, congelado=True),
    ])
    assert await _estado(db) == "validacao_processual"


async def test_estado_estrategia_matriz_montada():
    db = _db_artefatos(snaps=[_snap(origem="matriz_teses")], teses=[_tese()])
    assert await _estado(db) == "estrategia"


async def test_estado_contratacao_proposta_aprovada_e_kit():
    db = _db_artefatos(snaps=[_snap()], teses=[_tese("aprovada")],
                       propostas=[_proposta("aprovada")], docs=_kit_docs())
    assert await _estado(db) == "contratacao"


async def test_estado_producao_peca_rascunho():
    db = _db_artefatos(docs=_kit_docs() + [_doc()],
                       propostas=[_proposta("aprovada")])
    assert await _estado(db) == "producao"


async def test_estado_revisao_peca_em_revisao():
    db = _db_artefatos(docs=[_doc(status=PecaStatus.em_revisao)])
    assert await _estado(db) == "revisao"


async def test_estado_protocolo_peca_aprovada_com_deadline_confirmado():
    db = _db_artefatos(docs=[_doc(status=PecaStatus.aprovada)],
                       deadlines=[_deadline()])
    assert await _estado(db) == "protocolo"


async def test_estado_acompanhamento_peca_protocolada():
    db = _db_artefatos(docs=[_doc(status=PecaStatus.protocolada,
                                  protocolo="123456")])
    assert await _estado(db) == "acompanhamento"


async def test_documentos_do_kit_nao_contam_como_peca_de_producao():
    # Só procuração/contrato/checklist (rascunho) NÃO é produção de peça.
    assert await _estado(_db_artefatos(docs=_kit_docs())) == "entrada"


async def test_peca_aprovada_sem_deadline_confirmado_fica_em_revisao():
    db = _db_artefatos(docs=[_doc(status=PecaStatus.aprovada)],
                       deadlines=[_deadline(confirmado=False)])
    assert await _estado(db) == "revisao"


async def test_deadline_origem_manual_nao_empurra_para_protocolo():
    """Item 11: prazo antigo manual/datajud (sem relação com a peça) NÃO conta
    como 'prazo confirmado' — o caso fica em revisão, não em protocolo."""
    for origem in ("manual", "datajud", "importacao_ia", None):
        db = _db_artefatos(docs=[_doc(status=PecaStatus.aprovada)],
                           deadlines=[_deadline(origem=origem)])
        assert await _estado(db) == "revisao", origem


async def test_deadline_soft_deletado_ou_cancelado_nao_conta():
    from datetime import datetime, timezone
    db = _db_artefatos(docs=[_doc(status=PecaStatus.aprovada)],
                       deadlines=[_deadline(
                           deleted_at=datetime.now(timezone.utc))])
    assert await _estado(db) == "revisao"
    db = _db_artefatos(docs=[_doc(status=PecaStatus.aprovada)],
                       deadlines=[_deadline(status=DeadlineStatus.cancelado)])
    assert await _estado(db) == "revisao"


async def test_deadline_origem_agente_juridico_conta():
    db = _db_artefatos(docs=[_doc(status=PecaStatus.aprovada)],
                       deadlines=[_deadline(origem="agente_juridico")])
    assert await _estado(db) == "protocolo"


# ── proximo_passo — pendências bloqueantes ───────────────────────────────────

async def test_proximo_passo_entrada_sem_base_fatica_bloqueia():
    out = await lco.proximo_passo(_db_artefatos(), "case1", case=_case())
    assert out["estado"] == "entrada"
    assert any(p["tipo"] == "base_fatica" for p in out["pendencias_bloqueantes"])
    acoes = {a["acao"] for a in out["acoes_disponiveis"]}
    assert "analisar_caso" in acoes
    ep = [a for a in out["acoes_disponiveis"] if a["acao"] == "analisar_caso"][0]
    assert ep["endpoint"] == "/intake/casos/case1/analise-completa"


async def test_proximo_passo_compreensao_exige_aprovacao_humana():
    out = await lco.proximo_passo(_db_artefatos(snaps=[_snap()]), "case1",
                                  case=_case())
    assert out["estado"] == "compreensao"
    pend = out["pendencias_bloqueantes"]
    assert any(p["tipo"] == "aprovacao_humana" for p in pend)
    # A aprovação NÃO é executável via orquestrador
    aprov = [a for a in out["acoes_disponiveis"] if a["acao"] == "aprovar_snapshot"]
    assert aprov and aprov[0]["executavel_via_orquestrador"] is False


async def test_proximo_passo_contratacao_checklist_bloqueante_e_termo():
    snap_motor = _snap(
        versao=2, origem="motor_peca",
        payload={"area": "civil",
                 "checklist": {"itens": [{"key": "procuracao_vigente",
                                          "ok": False}], "pronto": False}})
    db = _db_artefatos(snaps=[snap_motor, _snap(versao=1)],
                       propostas=[_proposta("aprovada")], docs=_kit_docs())
    out = await lco.proximo_passo(db, "case1", case=_case())
    assert out["estado"] == "contratacao"
    tipos = [p["tipo"] for p in out["pendencias_bloqueantes"]]
    assert "checklist" in tipos            # checklist do motor não pronto
    assert "aprovacao_humana" in tipos     # termo inicial = confirmação humana
    acoes = {a["acao"] for a in out["acoes_disponiveis"]}
    assert "gerar_peca" in acoes


# ── avancar — whitelist, roles, atos jurídicos, auditoria ────────────────────

async def test_avancar_acao_desconhecida_422():
    with pytest.raises(HTTPException) as exc:
        await lco.avancar(_FakeDB([]), "case1", _user(), "hackear_sistema", {})
    assert exc.value.status_code == 422
    assert "acoes_validas" in exc.value.detail


async def test_avancar_role_baixa_403():
    for role in (UserRole.estagiario, UserRole.secretaria,
                 UserRole.cliente_externo):
        with pytest.raises(HTTPException) as exc:
            await lco.avancar(_FakeDB([]), "case1", _user(role),
                              "montar_matriz", {})
        assert exc.value.status_code == 403


async def test_avancar_recusa_atos_juridicos_com_instrucao():
    """Aprovações/confirmação de termo NUNCA são executadas pelo avancar."""
    for acao in ("aprovar_snapshot", "aprovar_tese", "aprovar_estrategia",
                 "aprovar_proposta", "aprovar_peca", "confirmar_termo_inicial"):
        db = _FakeDB([])
        out = await lco.avancar(db, "case1", _user(), acao, {})
        assert out["executado"] is False
        assert out["requer_aprovacao_humana"] is True
        assert out["instrucao"] and out["endpoint_humano"]
        # Nada tocou o banco: nenhuma escrita, nenhum commit
        assert db.added == [] and db.commits == 0


async def test_avancar_executa_transicao_com_auditoria_e_snapshot(monkeypatch):
    executado = {}

    async def _stub(db, case, user, params):
        executado["params"] = params
        return {"ok": True}

    monkeypatch.setitem(lco.ACOES_EXECUTAVEIS, "montar_matriz", _stub)
    # Fila: 6 (estado antes) + 6 (estado depois) + 1 (max versao do snapshot)
    db = _FakeDB([[], [], [], [], [], 0,
                  [], [], [], [], [], 0,
                  0])
    out = await lco.avancar(db, "case1", _user(), "montar_matriz",
                            {"area": "familia"}, case=_case())
    assert out["executado"] is True
    assert executado["params"] == {"area": "familia"}
    assert out["estado_anterior"] == "entrada" and out["estado"] == "entrada"
    # Auditoria da transição (criar_audit_log) + snapshot origem=orquestrador
    audits = [a for a in db.added if isinstance(a, AuditLog)]
    assert audits and audits[0].acao == "ORQUESTRADOR_AVANCAR"
    assert "montar_matriz" in (audits[0].detalhes or "")
    snaps = [s for s in db.added if isinstance(s, CaseIntelligenceSnapshot)]
    assert snaps and snaps[0].origem == "orquestrador"
    assert snaps[0].payload["acao"] == "montar_matriz"
    assert snaps[0].payload["estado_orquestrador"] == "entrada"
    assert db.commits >= 2


async def test_avancar_consome_rate_limit_do_fluxo_original(monkeypatch):
    """Item 12: avançar via orquestrador consome a MESMA cota da rota original
    (anti-bypass) — nome/limite espelham as dependencies dos routers."""
    consumos: list[tuple] = []

    async def _spy(nome, chave, limite):
        consumos.append((nome, chave, limite))

    monkeypatch.setattr(lco, "consumir", _spy)

    async def _stub(db, case, user, params):
        return {"ok": True}

    monkeypatch.setitem(lco.ACOES_EXECUTAVEIS, "montar_matriz", _stub)
    db = _FakeDB([[], [], [], [], [], 0,
                  [], [], [], [], [], 0,
                  0])
    await lco.avancar(db, "case1", _user(), "montar_matriz", {}, case=_case())
    assert consumos == [("matriz-teses-montar", "user:u1", 5)]
    # Mapa completo espelha os limites das rotas originais.
    assert lco._RATE_LIMIT_ACAO["gerar_peca"] == ("motor-peca-gerar", 3)
    assert lco._RATE_LIMIT_ACAO["gerar_kit"] == ("kit-documental", 5)
    assert lco._RATE_LIMIT_ACAO["criar_proposta"] == ("proposta-honorarios", 15)
    assert set(lco._RATE_LIMIT_ACAO) == set(lco.ACOES_EXECUTAVEIS)


async def test_avancar_429_propaga_sem_executar(monkeypatch):
    async def _429(nome, chave, limite):
        raise HTTPException(status_code=429, detail="limite excedido")

    monkeypatch.setattr(lco, "consumir", _429)
    executado = {"n": 0}

    async def _stub(db, case, user, params):
        executado["n"] += 1
        return {}

    monkeypatch.setitem(lco.ACOES_EXECUTAVEIS, "gerar_peca", _stub)
    db = _FakeDB([])
    with pytest.raises(HTTPException) as exc:
        await lco.avancar(db, "case1", _user(), "gerar_peca", {}, case=_case())
    assert exc.value.status_code == 429
    assert executado["n"] == 0 and db.added == [] and db.commits == 0


async def test_avancar_params_invalidos_viram_422_estruturado(monkeypatch):
    """Item 13: ValidationError dos params do fluxo original vira 422 com a
    lista campo/erro — nunca 500."""
    async def _ok(nome, chave, limite):
        return None

    monkeypatch.setattr(lco, "consumir", _ok)
    db = _FakeDB([[], [], [], [], [], 0])   # só o estado ANTES é coletado
    with pytest.raises(HTTPException) as exc:
        await lco.avancar(db, "case1", _user(), "criar_proposta",
                          {"exito_percentual": 200}, case=_case())
    assert exc.value.status_code == 422
    detail = exc.value.detail
    assert "criar_proposta" in detail["mensagem"]
    assert detail["erros"] and any("exito_percentual" in e["campo"]
                                   for e in detail["erros"])
    assert db.commits == 0   # nada executado/auditado


async def test_avancar_falha_do_service_nao_corrompe_estado(monkeypatch):
    """Erro no service propaga (nada de estado mutável fica para trás — o
    estado é derivado de artefatos, e nenhum snapshot/auditoria é gravado)."""
    async def _boom(db, case, user, params):
        raise RuntimeError("falha do service")

    monkeypatch.setitem(lco.ACOES_EXECUTAVEIS, "gerar_kit", _boom)
    db = _FakeDB([[], [], [], [], [], 0])  # só o estado ANTES é coletado
    with pytest.raises(RuntimeError):
        await lco.avancar(db, "case1", _user(), "gerar_kit", {}, case=_case())
    assert db.added == [] and db.commits == 0


# ── avancar (router) — guarda de status do caso (review PR #483) ─────────────

async def test_avancar_router_caso_encerrado_ou_arquivado_409(monkeypatch):
    """Caso encerrado/arquivado → 409 no router, SEM executar nenhuma ação
    (o backend não confiava só na UI; agora a guarda existe nas duas pontas)."""
    from app.routers import orquestrador as router_mod

    chamadas = {"n": 0}

    async def _nunca(*a, **k):
        chamadas["n"] += 1

    monkeypatch.setattr(router_mod.lco, "avancar", _nunca)
    for status in ("encerrado", "arquivado"):
        async def _acesso(db, cu, case_id, _s=status):
            return _case(status=_s)

        monkeypatch.setattr(router_mod, "verificar_acesso_caso", _acesso)
        with pytest.raises(HTTPException) as exc:
            await router_mod.avancar(
                "case1", router_mod.AvancarIn(acao="montar_matriz"),
                db=_FakeDB([]), cu=_user())
        assert exc.value.status_code == 409
        assert "reabra o caso" in str(exc.value.detail).lower()
    assert chamadas["n"] == 0


async def test_avancar_router_caso_ativo_passa_pela_guarda(monkeypatch):
    from app.routers import orquestrador as router_mod

    async def _acesso(db, cu, case_id):
        return _case(status="em_producao")

    async def _stub(db, case_id, cu, acao, params, case=None):
        return {"executado": True}

    monkeypatch.setattr(router_mod, "verificar_acesso_caso", _acesso)
    monkeypatch.setattr(router_mod.lco, "avancar", _stub)
    out = await router_mod.avancar(
        "case1", router_mod.AvancarIn(acao="montar_matriz"),
        db=_FakeDB([]), cu=_user())
    assert out == {"executado": True}


# ── Jornada resumida (UI) ────────────────────────────────────────────────────

async def test_jornada_rotulos_e_status():
    db = _db_artefatos(snaps=[_snap()], n_ocr=2)
    art = await lco.coletar_artefatos(db, "case1", case=_case())
    jornada = lco.montar_jornada(art)

    por_etapa = {j["etapa"]: j for j in jornada}
    assert por_etapa["documentos_lidos"]["rotulo"] == "Documentos lidos"
    assert por_etapa["documentos_lidos"]["status"] == "concluida"
    assert por_etapa["area_sugerida"]["rotulo"] == "Área sugerida"
    assert por_etapa["area_sugerida"]["status"] == "concluida"
    # Primeira etapa não concluída depende de aprovação humana → bloqueada
    assert por_etapa["area_confirmada"]["status"] == "bloqueada"
    # Demais seguem pendentes
    assert por_etapa["teses_pesquisadas"]["status"] == "pendente"
    assert por_etapa["peca_protocolada"]["status"] == "pendente"
    # Rótulos humanos do plano (§16)
    rotulos = {j["rotulo"] for j in jornada}
    for esperado in ("Prazo calculado", "Checklist criado", "Teses pesquisadas",
                     "Honorários sugeridos", "Procuração gerada",
                     "Contrato gerado", "Peça redigida", "Citações verificadas",
                     "Aguardando aprovação do advogado"):
        assert esperado in rotulos


async def test_jornada_caso_avancado_conclui_etapas():
    db = _db_artefatos(
        snaps=[_snap(versao=2, origem="motor_peca",
                     payload={"area": "civil",
                              "checklist": {"itens": [], "pronto": True}}),
               _snap(versao=1, congelado=True)],
        teses=[_tese("aprovada")],
        propostas=[_proposta("aprovada")],
        docs=_kit_docs() + [_doc(status=PecaStatus.protocolada, protocolo="1")],
        deadlines=[_deadline()], n_ocr=3, n_validacoes=1)
    art = await lco.coletar_artefatos(db, "case1", case=_case())
    jornada = lco.montar_jornada(art)
    assert all(j["status"] == "concluida" for j in jornada), jornada


async def test_citacoes_verificadas_exige_validacao_registrada():
    """CR-15: peça ai_generated SEM validação jurídica registrada NÃO conclui
    'Citações verificadas' (antes o mero ai_generated concluía a etapa)."""
    db = _db_artefatos(docs=[_doc()], n_validacoes=0)
    art = await lco.coletar_artefatos(db, "case1", case=_case())
    assert art["peca_ia"] is True and art["peca_validada"] is False
    por_etapa = {j["etapa"]: j for j in lco.montar_jornada(art)}
    assert por_etapa["citacoes_verificadas"]["status"] != "concluida"


async def test_citacoes_verificadas_conclui_com_validacao_registrada():
    """CR-15: com AILog de validação da peça (sinal de _ultima_validacao_peca)
    a etapa conclui — mesmo para peça não-IA (validação humana registrada)."""
    db = _db_artefatos(docs=[_doc(ai=False)], n_validacoes=2)
    art = await lco.coletar_artefatos(db, "case1", case=_case())
    assert art["peca_validada"] is True
    por_etapa = {j["etapa"]: j for j in lco.montar_jornada(art)}
    assert por_etapa["citacoes_verificadas"]["status"] == "concluida"


async def test_sem_peca_de_producao_nao_consulta_validacoes():
    """Sem peça de produção a consulta (7) NÃO roda (fila de 6 resultados) e
    peca_validada é False — kit documental sozinho não conta."""
    db = _db_artefatos(docs=_kit_docs())
    art = await lco.coletar_artefatos(db, "case1", case=_case())
    assert art["peca_validada"] is False
    assert db._resultados == []   # fila consumida por inteiro (sem query 7)


# ── Linha do tempo e visão consolidada ───────────────────────────────────────

async def test_visao_orquestrador_com_linha_do_tempo():
    snaps = [
        _snap(versao=3, origem="orquestrador",
              payload={"estado_orquestrador": "estrategia",
                       "acao": "montar_matriz"}),
        _snap(versao=2, origem="matriz_teses"),
        _snap(versao=1, origem="intake"),
    ]
    db = _db_artefatos(snaps=snaps, teses=[_tese()])
    out = await lco.visao_orquestrador(db, "case1", case=_case())
    assert out["estado"] == "estrategia"
    assert out["estados"] == list(lco.ESTADOS)
    assert [e["versao"] for e in out["linha_do_tempo"]] == [1, 2, 3]
    assert out["linha_do_tempo"][0]["estado"] == "compreensao"
    assert out["linha_do_tempo"][1]["estado"] == "estrategia"
    assert out["linha_do_tempo"][2]["estado"] == "estrategia"  # do payload
    assert out["proximo_passo"]["pendencias_bloqueantes"]
    assert isinstance(out["jornada"], list) and len(out["jornada"]) >= 10
