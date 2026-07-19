"""Ficha de Triagem pré-peça — gate de qualidade da geração de peças.

Padrão dos testes de IA do projeto (sem Postgres real): handlers/serviços
chamados diretamente com fake de sessão; gateway de IA monkeypatched.
Cobre: pré-preenchimento retorna os 12 campos + confiança; salvar/confirmar
muda status; UPSERT; helper ficha_confirmada; gate 409 na geração de peça sem
ficha confirmada (FICHA_TRIAGEM_OBRIGATORIA=True) e passagem com ficha
confirmada; geração AVULSA (sem case_id) não é gateada; resumo_para_prompt
não vaza metadados sensíveis.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from app.models.ai_log import AILog
from app.models.audit_log import AuditLog
from app.models.case import Case
from app.models.ficha_triagem import FichaTriagem
from app.models.prova import Prova
from app.models.user import User, UserRole
from app.services import ficha_triagem_service as svc


# ── Fakes (sem banco) ─────────────────────────────────────────────────────────

class _Res:
    def __init__(self, val):
        self._val = val

    def scalar_one_or_none(self):
        return self._val

    def scalars(self):
        return list(self._val) if isinstance(self._val, list) else []


class _FakeDB:
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
    return User(id=uid, role=role)


def _case(**kw) -> Case:
    base = dict(id="case1", titulo="Ação de Cobrança", client_id="cli1",
                area="civil", numero_processo=None, numero_interno="DPT-2026-0001",
                tese_principal="Inadimplemento contratual",
                tipo_acao_prescricao="Ação de cobrança",
                advogado_responsavel_id=None, advogado_auxiliar_id=None,
                deleted_at=None)
    base.update(kw)
    return Case(**base)


def _prova(**kw) -> Prova:
    base = dict(id="p1", case_id="case1", tipo="documental",
                titulo="Contrato assinado", descricao=None, document_id=None,
                tese_id=None, fato_probando="Existência do vínculo", ordem=0,
                deleted_at=None, created_at=None)
    base.update(kw)
    return Prova(**base)


def _gw_resp(texto: str) -> SimpleNamespace:
    return SimpleNamespace(texto=texto, modelo="claude-x", provedor="anthropic",
                           input_tokens=100, output_tokens=50)


async def _entidades_vazias(db, case_id):
    return {}


_JSON_IA = (
    '{"competencia": {"valor": "Justiça Comum Estadual", "confianca": 80},'
    ' "rito": {"valor": "Procedimento comum", "confianca": 75},'
    ' "legitimidade_ativa": {"valor": "Credor", "confianca": 70},'
    ' "legitimidade_passiva": {"valor": "Devedor", "confianca": 70},'
    ' "prescricao_decadencia": {"valor": "5 anos (art. 206 CC)", "confianca": 60},'
    ' "tutela_urgencia": {"valor": false, "confianca": 65},'
    ' "tutela_fundamento": {"valor": null, "confianca": 30},'
    ' "provas_faltantes": {"valor": "Notificação extrajudicial", "confianca": 55},'
    ' "valor_causa": {"valor": "R$ 10.000", "confianca": 50},'
    ' "risco_processual": {"valor": "medio", "confianca": 60},'
    ' "pedidos_principais": {"valor": "Condenação ao pagamento", "confianca": 72}}'
)


# ── Rotas montadas ────────────────────────────────────────────────────────────

def test_rotas_ficha_montadas_em_main():
    from app.main import app
    paths = {getattr(r, "path", "") for r in app.routes}
    assert any(p.endswith("/triagem/ficha/pre-preencher") for p in paths)
    assert any(p.endswith("/triagem/ficha") for p in paths)


# ── pre_preencher: 12 campos + confiança ──────────────────────────────────────

async def test_pre_preencher_retorna_12_campos_e_confianca(monkeypatch):
    from app.services import ai_gateway
    from app.services.ai import entidades_caso

    async def _fake_chat(messages, **kw):
        assert kw.get("task_type") == "triagem"
        return _gw_resp(_JSON_IA)

    monkeypatch.setattr(ai_gateway, "chat", _fake_chat)
    monkeypatch.setattr(entidades_caso, "entidades_do_caso", _entidades_vazias)

    db = _FakeDB([_case(), [_prova()]])
    out = await svc.pre_preencher(db, "case1", user_id="u1", user_role="advogado")

    assert set(out["campos"]) == set(svc.CAMPOS_TRIAGEM)
    assert len(out["campos"]) == 12
    assert set(out["confianca"]) == set(svc.CAMPOS_TRIAGEM)
    assert out["status"] == "rascunho"
    assert out["parse_ok"] is True
    # provas_disponiveis é DETERMINÍSTICO (acervo), confiança 100.
    assert "Contrato assinado" in out["campos"]["provas_disponiveis"]
    assert out["confianca"]["provas_disponiveis"] == 100
    # risco normalizado ao domínio.
    assert out["campos"]["risco_processual"] == "medio"
    assert out["campos"]["tutela_urgencia"] is False
    # AILog registrado (HITL) e persistido; nada de ficha criada aqui.
    assert any(isinstance(o, AILog) for o in db.added)
    assert not any(isinstance(o, FichaTriagem) for o in db.added)
    assert db.commits == 1


async def test_pre_preencher_ia_lixo_degrada_para_campos_nulos(monkeypatch):
    from app.services import ai_gateway
    from app.services.ai import entidades_caso

    async def _fake_chat(messages, **kw):
        return _gw_resp("Desculpe, não consegui montar o JSON.")

    monkeypatch.setattr(ai_gateway, "chat", _fake_chat)
    monkeypatch.setattr(entidades_caso, "entidades_do_caso", _entidades_vazias)

    db = _FakeDB([_case(), []])
    out = await svc.pre_preencher(db, "case1", user_id="u1", user_role="advogado")
    assert out["parse_ok"] is False
    assert len(out["campos"]) == 12
    assert out["campos"]["competencia"] is None
    assert out["campos"]["provas_disponiveis"] is None  # sem provas no acervo


async def test_pre_preencher_ia_desabilitada_503(monkeypatch):
    monkeypatch.setattr(svc.settings, "AI_ENABLED", False)
    db = _FakeDB([])
    with pytest.raises(HTTPException) as exc:
        await svc.pre_preencher(db, "case1", user_id="u1", user_role="advogado")
    assert exc.value.status_code == 503


# ── salvar / confirmar / upsert ───────────────────────────────────────────────

async def test_salvar_rascunho_cria_ficha():
    db = _FakeDB([None])  # obter → None (nova ficha)
    ficha = await svc.salvar(db, "case1",
                             {"competencia": "JEC", "risco_processual": "medio"},
                             confirmar=False, user_id="u1", user_role="advogado")
    assert ficha.status == "rascunho"
    assert ficha.competencia == "JEC"
    assert ficha.risco_processual == "medio"
    assert any(isinstance(o, FichaTriagem) for o in db.added)
    assert any(isinstance(o, AuditLog) and o.acao == "FICHA_TRIAGEM_SALVA"
               for o in db.added)
    assert db.commits == 1


async def test_confirmar_muda_status_para_confirmada():
    db = _FakeDB([None])
    ficha = await svc.salvar(db, "case1", {"competencia": "JEC"},
                             confirmar=True, user_id="u1", user_role="advogado")
    assert ficha.status == "confirmada"
    assert any(isinstance(o, AuditLog) and o.acao == "FICHA_TRIAGEM_CONFIRMADA"
               for o in db.added)


async def test_salvar_upsert_atualiza_ficha_existente():
    existente = FichaTriagem(id="f1", case_id="case1", status="rascunho",
                             competencia="antigo", created_by="u1")
    db = _FakeDB([existente])  # obter → ficha existente
    ficha = await svc.salvar(db, "case1", {"competencia": "novo"},
                             confirmar=True, user_id="u1", user_role="advogado")
    assert ficha is existente  # mesma linha (uma ficha por caso)
    assert ficha.competencia == "novo"
    assert ficha.status == "confirmada"
    # Nenhuma NOVA ficha adicionada no upsert.
    assert not any(isinstance(o, FichaTriagem) for o in db.added)


async def test_salvar_risco_invalido_vira_none():
    db = _FakeDB([None])
    ficha = await svc.salvar(db, "case1", {"risco_processual": "altíssimo"},
                             confirmar=False, user_id="u1", user_role="advogado")
    assert ficha.risco_processual is None


# ── ficha_confirmada (helper do gate) ─────────────────────────────────────────

async def test_ficha_confirmada_so_retorna_confirmada():
    conf = FichaTriagem(id="f1", case_id="case1", status="confirmada")
    assert (await svc.ficha_confirmada(_FakeDB([conf]), "case1")) is conf

    rasc = FichaTriagem(id="f2", case_id="case1", status="rascunho")
    assert (await svc.ficha_confirmada(_FakeDB([rasc]), "case1")) is None

    assert (await svc.ficha_confirmada(_FakeDB([None]), "case1")) is None


# ── resumo_para_prompt não vaza metadados sensíveis ───────────────────────────

def test_resumo_para_prompt_conteudo_e_sem_vazamento():
    ficha = FichaTriagem(
        id="ID-SECRETO-123", case_id="case1", status="confirmada",
        created_by="USER-SECRETO-999",
        competencia="Justiça Comum", rito="Comum",
        pedidos_principais="Condenação ao pagamento",
        tutela_urgencia=True, tutela_fundamento="Fumus + periculum",
        risco_processual="alto", risco_nota="Prova frágil",
        confianca={"competencia": 77},
    )
    txt = svc.resumo_para_prompt(ficha)
    # Conteúdo substantivo presente.
    assert "Justiça Comum" in txt
    assert "Condenação ao pagamento" in txt
    assert "Tutela de urgência: SIM" in txt
    assert "alto" in txt
    # Metadados internos NUNCA aparecem.
    assert "ID-SECRETO-123" not in txt
    assert "USER-SECRETO-999" not in txt
    assert "77" not in txt          # dict de confiança não vaza
    assert "created_by" not in txt


def test_resumo_para_prompt_ficha_vazia_retorna_string_vazia():
    assert svc.resumo_para_prompt(FichaTriagem(id="f", case_id="c",
                                               status="confirmada")) == ""


# ── Gate na geração de peça ───────────────────────────────────────────────────

def _req_peca(case_id):
    from app.routers.peca_geracao import GerarPecaRequest
    return GerarPecaRequest(
        tipo_peca="peticao_inicial", area_direito="civil",
        descricao_fatos="x" * 60, pedidos="Pagamento de valores em atraso.",
        case_id=case_id,
    )


async def _prep_gate(monkeypatch, ficha_confirmada_ret):
    """Neutraliza ownership + escopo do caso e injeta o retorno de
    ficha_confirmada; devolve o handler pronto p/ chamar."""
    from app.routers import peca_geracao as mod
    from app.services import ai_service
    from app.services import ficha_triagem_service as fts

    async def _acesso_ok(db, cu, case_id):
        return _case()

    async def _escopo(db, case_id):
        return None

    async def _ficha(db, case_id):
        return ficha_confirmada_ret

    monkeypatch.setattr(mod, "verificar_acesso_caso", _acesso_ok)
    monkeypatch.setattr(ai_service, "_escopo_cliente_do_caso", _escopo)
    monkeypatch.setattr(fts, "ficha_confirmada", _ficha)
    return mod


async def test_gate_409_sem_ficha_confirmada(monkeypatch):
    mod = await _prep_gate(monkeypatch, None)
    assert mod.get_settings().FICHA_TRIAGEM_OBRIGATORIA is True
    with pytest.raises(HTTPException) as exc:
        await mod.gerar_peca(_req_peca("case1"), db=_FakeDB([]), cu=_user())
    assert exc.value.status_code == 409
    assert exc.value.detail["need_ficha_triagem"] is True
    assert exc.value.detail["case_id"] == "case1"


async def test_gate_passa_com_ficha_confirmada(monkeypatch):
    ficha = FichaTriagem(id="f1", case_id="case1", status="confirmada",
                         competencia="JEC", pedidos_principais="Pagamento")
    mod = await _prep_gate(monkeypatch, ficha)
    resp = await mod.gerar_peca(_req_peca("case1"), db=_FakeDB([]), cu=_user())
    # Sem 409: retorna o stream SSE (não consumido aqui).
    assert isinstance(resp, StreamingResponse)


async def test_gate_desligado_nao_bloqueia(monkeypatch):
    mod = await _prep_gate(monkeypatch, None)
    monkeypatch.setattr(mod.get_settings(), "FICHA_TRIAGEM_OBRIGATORIA", False)
    resp = await mod.gerar_peca(_req_peca("case1"), db=_FakeDB([]), cu=_user())
    assert isinstance(resp, StreamingResponse)


async def test_geracao_avulsa_sem_case_id_nao_gateia(monkeypatch):
    # Sem case_id: nenhum acesso a caso, nenhum gate — stream direto.
    from app.routers import peca_geracao as mod
    resp = await mod.gerar_peca(_req_peca(None), db=_FakeDB([]), cu=_user())
    assert isinstance(resp, StreamingResponse)
