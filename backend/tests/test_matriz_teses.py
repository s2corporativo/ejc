"""FASE 3 do Orquestrador Jurídico — Matriz de Teses estruturada.

Sem Postgres real (padrão test_case_intelligence.py): service e handlers com
fake de sessão. Cobre: parse tolerante da decomposição (IA + AILog), score
`forca` determinístico (com/sem precedente verificado), AuthorityRecord nunca
inventado (RAG vazio ⇒ zero records), aprovação HITL + auditoria (403/404/409),
flag PECAS_PESQUISA_QUESTOES_ENABLED OFF = pipeline inalterado e rotas montadas.
"""
from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from app.models.ai_log import AILog
from app.models.audit_log import AuditLog
from app.models.matriz_teses import (
    AuthorityRecord, LegalIssue, ThesisCandidate,
)
from app.models.tese import Tese, TeseStatus, TeseTipo
from app.models.user import User, UserRole
from app.services import matriz_teses_service as mts


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
        self.rollbacks = 0

    async def execute(self, *a, **k):
        return _Res(self._resultados.pop(0))

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _user(role: UserRole, uid: str = "u1") -> User:
    return User(id=uid, role=role)


class _Resp:
    def __init__(self, texto):
        self.texto = texto
        self.modelo = "m"
        self.provedor = "p"


class _Cfg:
    AI_ENABLED = True


def _issue(**kw) -> LegalIssue:
    base = dict(id="i1", case_id="case1", questao="Há prescrição quinquenal?",
                area="trabalhista", prioridade=1, origem="ia",
                criado_por="u1", criado_em=None)
    base.update(kw)
    return LegalIssue(**base)


def _cand(**kw) -> ThesisCandidate:
    base = dict(id="t1", case_id="case1", issue_id=None, tese="Tese X",
                fundamento="art. 7º CF", fatos_relacionados=[], provas=[],
                precedentes=[], vulnerabilidades=[], forca=0,
                status="candidata", criado_por=None, criado_em=None,
                aprovado_por=None, aprovado_em=None)
    base.update(kw)
    return ThesisCandidate(**base)


# ── Rotas montadas ────────────────────────────────────────────────────────────

def test_rotas_montadas_em_main():
    from app.main import app
    paths = {getattr(r, "path", "") for r in app.routes}
    assert any(p.endswith("/cases/{case_id}/matriz-teses/montar") for p in paths)
    assert any(p.endswith("/cases/{case_id}/matriz-teses") for p in paths)
    assert any(p.endswith("/cases/{case_id}/matriz-teses/teses/{tese_id}/aprovar")
               for p in paths)
    assert any(p.endswith("/cases/{case_id}/matriz-teses/teses/{tese_id}/descartar")
               for p in paths)


def test_origem_matriz_teses_no_snapshot():
    """Mudança ADITIVA na tupla de origens do snapshot (Fase 1)."""
    from app.models.case_intelligence import ORIGENS_SNAPSHOT
    assert "matriz_teses" in ORIGENS_SNAPSHOT
    # origens preexistentes preservadas (aditivo)
    assert {"triagem", "intake", "raio_x", "motor_peca", "manual"} <= set(ORIGENS_SNAPSHOT)


# ── Decomposição: parse tolerante ────────────────────────────────────────────

def test_parse_questoes_json_limpo():
    out = mts._parse_questoes(json.dumps({
        "questoes": [{"questao": "Competência da JT?", "prioridade": 1},
                     {"questao": "Prescrição?", "prioridade": 2}],
        "teses_sugeridas": [{"tese": "Vínculo empregatício",
                             "fundamento": "art. 3º CLT"}],
    }))
    assert [q["questao"] for q in out["questoes"]] == ["Competência da JT?", "Prescrição?"]
    assert out["teses_sugeridas"][0]["fundamento"] == "art. 3º CLT"


def test_parse_questoes_tolerante_cercas_e_ruido():
    bruto = "Claro! Segue:\n```json\n{\"questoes\": [\"Legitimidade passiva?\"]}\n```"
    out = mts._parse_questoes(bruto)
    assert out["questoes"] == [{"questao": "Legitimidade passiva?", "prioridade": 3}]
    assert out["teses_sugeridas"] == []


def test_parse_questoes_lista_crua_e_prioridade_clampada():
    out = mts._parse_questoes('[{"questao": "Dano moral?", "prioridade": 99}]')
    assert out["questoes"] == [{"questao": "Dano moral?", "prioridade": 5}]


def test_parse_questoes_invalido_devolve_vazio():
    assert mts._parse_questoes("nada de json aqui") == {
        "questoes": [], "teses_sugeridas": []}
    assert mts._parse_questoes("") == {"questoes": [], "teses_sugeridas": []}


async def test_decompor_grava_issues_ia_e_ailog(monkeypatch):
    monkeypatch.setattr(mts, "get_settings", lambda: _Cfg())

    async def _fake_chat(**kw):
        assert kw["task_type"] == "estrategia"
        return _Resp(json.dumps({
            "questoes": [{"questao": "Prescrição?", "prioridade": 1}],
            "teses_sugeridas": [{"tese": "Tese IA", "fundamento": "art. 7º XXIX CF"}],
        }))
    monkeypatch.setattr(mts, "gw_chat", _fake_chat)

    db = _FakeDB([])
    out = await mts.decompor_questoes(db, "u1", "case1", "trabalhista",
                                      "Fatos sanitizados suficientes para análise.")
    issues = [o for o in db.added if isinstance(o, LegalIssue)]
    logs = [o for o in db.added if isinstance(o, AILog)]
    assert len(issues) == 1 and issues[0].origem == "ia"
    assert issues[0].questao == "Prescrição?" and issues[0].prioridade == 1
    assert len(logs) == 1 and logs[0].user_id == "u1" and logs[0].case_id == "case1"
    assert out["teses_sugeridas"][0]["tese"] == "Tese IA"
    assert out["ai_log_id"] == logs[0].id
    assert db.commits == 1


async def test_decompor_sem_ia_nao_inventa(monkeypatch):
    cfg = _Cfg()
    cfg.AI_ENABLED = False
    monkeypatch.setattr(mts, "get_settings", lambda: cfg)
    db = _FakeDB([])
    out = await mts.decompor_questoes(db, "u1", "case1", None, "fatos longos o bastante")
    assert out == {"issues": [], "teses_sugeridas": [], "ai_log_id": None,
                   "avisos": []}
    assert db.added == [] and db.commits == 0


async def test_decompor_parse_falho_nao_e_silencioso(monkeypatch):
    """Item 10: resposta NÃO vazia sem nada extraível → aviso obrigatório."""
    monkeypatch.setattr(mts, "get_settings", lambda: _Cfg())

    async def _fake_chat(**kw):
        return _Resp("Desculpe, não posso responder em JSON hoje.")
    monkeypatch.setattr(mts, "gw_chat", _fake_chat)

    db = _FakeDB([])
    out = await mts.decompor_questoes(db, "u1", "case1", "trabalhista",
                                      "Fatos sanitizados suficientes para análise.")
    assert out["issues"] == [] and out["teses_sugeridas"] == []
    assert out["avisos"] == [mts.AVISO_FALHA_PARSE]
    # O AILog da chamada continua registrado (rastreabilidade).
    assert [o for o in db.added if isinstance(o, AILog)]


# ── Força: score determinístico (nunca LLM) ──────────────────────────────────

def test_forca_com_precedente_verificado_favoravel():
    tese = {
        "fundamento": "art. 7º XXIX CF",
        "fatos_relacionados": ["fato1", "fato2"],
        "provas": ["p1"],
        "precedentes": [{"status_verificacao": "verificada", "favoravel": True}],
        "vulnerabilidades": ["contra-argumento"],
    }
    # 15 (fundamento) + 10 (verificado) + 10 (2 fatos) + 5 (1 prova)
    # + 10 (saldo 1 verificado favorável) − 5 (1 vulnerabilidade) = 45
    assert mts.calcular_forca(tese) == 45
    assert mts.calcular_forca(tese) == 45  # determinístico: mesmo input, mesmo score


def test_forca_sem_precedente_verificado():
    tese = {
        "fundamento": "art. 7º XXIX CF",
        "fatos_relacionados": ["fato1", "fato2"],
        "provas": ["p1"],
        "precedentes": [{"status_verificacao": "nao_verificada", "favoravel": True}],
        "vulnerabilidades": ["contra-argumento"],
    }
    # precedente NÃO verificado não pontua: 15 + 10 + 5 − 5 = 25
    assert mts.calcular_forca(tese) == 25


def test_forca_saldo_negativo_vira_zero_e_clamp():
    contras = [{"status_verificacao": "verificada", "favoravel": False}] * 3
    assert mts.calcular_forca({"fundamento": "", "precedentes": contras,
                               "vulnerabilidades": ["v"] * 10}) == 0
    cheia = {
        "fundamento": "x", "fatos_relacionados": ["f"] * 10, "provas": ["p"] * 10,
        "precedentes": [{"status_verificacao": "verificada", "favoravel": True}] * 10,
        "vulnerabilidades": [],
    }
    # 15 + 10 + 15 (máx fatos) + 15 (máx provas) + 30 (máx saldo) = 85 (≤100)
    assert mts.calcular_forca(cheia) == 85


def test_forca_aceita_objeto_thesis_candidate():
    cand = _cand(fundamento="art. 5º", fatos_relacionados=["f1"], provas=[],
                 precedentes=[], vulnerabilidades=[])
    assert mts.calcular_forca(cand) == 20  # 15 + 5


# ── Authority NUNCA inventada ────────────────────────────────────────────────

async def test_rag_vazio_gera_zero_authority_records(monkeypatch):
    async def _rag_vazio(*a, **k):
        return []
    monkeypatch.setattr(mts, "buscar_contexto_rag", _rag_vazio)
    db = _FakeDB([])
    out = await mts.pesquisar_por_questao(db, "case1", _issue())
    assert out == []
    assert db.added == []   # nada inventado


async def test_authority_nasce_de_retorno_real_com_trecho(monkeypatch):
    async def _rag(*a, **k):
        return [{"conteudo": "Recurso a que se nega provimento. Súmula 331 TST.",
                 "titulo": "Julgado interno", "categoria": "jurisprudencia"}]
    monkeypatch.setattr(mts, "buscar_contexto_rag", _rag)

    async def _verificador(db, texto):
        return {"citacoes": [{
            "tipo": "sumula", "status": "verificada", "citacao": "Súmula 331 TST",
            "numero": "331", "tribunal": "TST", "orgao": None, "data": None,
            "fonte_verificacao": "base oficial interna/RAG",
            "fonte": "base oficial interna/RAG",
        }]}
    monkeypatch.setattr(mts, "verificar_jurisprudencia", _verificador)

    db = _FakeDB([])
    out = await mts.pesquisar_por_questao(db, "case1", _issue())
    assert len(out) == 1
    r = out[0]
    assert isinstance(r, AuthorityRecord)
    assert r.status_verificacao == "verificada"
    assert r.fonte_oficial == "base oficial interna/RAG"  # obrigatória qdo verificada
    assert r.trecho.startswith("Recurso a que se nega provimento")
    assert r.tribunal == "TST" and r.processo_ref == "331"
    assert r.favoravel is False  # "nega provimento" → contrário (determinístico)
    assert r.tema == _issue().questao


async def test_authority_verificador_indisponivel_fica_nao_verificada(monkeypatch):
    async def _rag(*a, **k):
        return [{"conteudo": "Pedido julgado procedente na origem.",
                 "titulo": "Doc RAG", "categoria": "jurisprudencia"}]
    monkeypatch.setattr(mts, "buscar_contexto_rag", _rag)

    async def _boom(db, texto):
        raise RuntimeError("grounding fora")
    monkeypatch.setattr(mts, "verificar_jurisprudencia", _boom)

    db = _FakeDB([])
    out = await mts.pesquisar_por_questao(db, "case1", _issue())
    assert len(out) == 1
    assert out[0].status_verificacao == "nao_verificada"
    assert out[0].fonte_oficial is None
    assert out[0].favoravel is True  # "procedente" → favorável


def test_favorabilidade_deterministica_contrario_tem_precedencia():
    assert mts._classificar_favorabilidade("pedido improcedente") is False
    assert mts._classificar_favorabilidade("sentença desfavorável ao autor") is False
    assert mts._classificar_favorabilidade("recurso provido") is True
    assert mts._classificar_favorabilidade("texto neutro sem marcador") is None


def test_favorabilidade_marcadores_contrarios_ampliados():
    """Item 3: formas de negativa de provimento casam ANTES de 'provimento'."""
    for txt in ("nego provimento ao recurso", "nega provimento ao apelo",
                "recurso improvido", "apelação improvida",
                "recurso a que se nega provimento", "recurso desprovido",
                "voto pelo desprovimento do recurso"):
        assert mts._classificar_favorabilidade(txt) is False, txt
    # Favoráveis seguem funcionando (precedência não virou falso-negativo).
    assert mts._classificar_favorabilidade("dá provimento ao recurso") is True


# ── Montagem: teses do banco viram candidatas + snapshot matriz_teses ────────

async def test_montar_matriz_candidatas_e_snapshot(monkeypatch):
    monkeypatch.setattr(mts, "get_settings", lambda: _Cfg())

    async def _fake_chat(**kw):
        return _Resp(json.dumps({
            "questoes": [{"questao": "Prescrição?", "prioridade": 1}],
            "teses_sugeridas": [{"tese": "Tese IA", "fundamento": "art. 7º CF"}],
        }))
    monkeypatch.setattr(mts, "gw_chat", _fake_chat)

    async def _rag_vazio(*a, **k):
        return []
    monkeypatch.setattr(mts, "buscar_contexto_rag", _rag_vazio)

    capturado = {}

    async def _fake_snapshot(db, **kw):
        capturado.update(kw)
        return None
    from app.services import case_intelligence_service as cis
    monkeypatch.setattr(cis, "gravar_snapshot_seguro", _fake_snapshot)

    tese_banco = Tese(id="tb1", titulo="Tese banco", descricao="Descrição da tese",
                      fundamentacao="Súmula 331 TST", contra_argumento="risco X",
                      area_juridica="trabalhista", tipo=TeseTipo.escritorio,
                      status=TeseStatus.ativa, vezes_usada=0, vezes_venceu=0,
                      vezes_perdeu=0, deleted_at=None)
    # fila: select Tese → select Prova (decomposição/RAG não usam execute)
    db = _FakeDB([[tese_banco], []])

    matriz = await mts.montar_matriz(db, "u1", "case1", "trabalhista",
                                     "Fatos sanitizados suficientes para análise.")
    cands = [o for o in db.added if isinstance(o, ThesisCandidate)]
    assert len(cands) == 2                       # banco + sugerida pela IA
    assert all(c.status == "candidata" for c in cands)   # HITL: tudo rascunho
    assert all(c.aprovado_por is None for c in cands)
    assert {c.tese for c in cands} == {"Descrição da tese", "Tese IA"}
    banco = next(c for c in cands if c.tese == "Descrição da tese")
    assert banco.vulnerabilidades == ["risco X"]
    assert banco.forca == mts.calcular_forca(banco)      # score determinístico

    assert matriz["status"] == "rascunho"
    assert len(matriz["teses"]) == 2 and len(matriz["questoes"]) == 1
    assert matriz["precedentes"] == []           # RAG vazio → nada inventado
    assert matriz["avisos"] == []                # parse OK → sem avisos

    assert capturado["origem"] == "matriz_teses"
    assert capturado["case_id"] == "case1"
    assert capturado["payload"]["precedentes"]["total"] == 0
    assert capturado["payload"]["avisos"] == []


async def test_montar_matriz_precedentes_por_questao_sem_boost_indevido(monkeypatch):
    """Item 2: o pool de AuthorityRecords NÃO é anexado a todas as teses —
    tese sem questão vinculada (banco e sugerida) fica com precedentes=[] e
    a forca não ganha boost de precedente."""
    monkeypatch.setattr(mts, "get_settings", lambda: _Cfg())

    async def _fake_chat(**kw):
        return _Resp(json.dumps({
            "questoes": [{"questao": "Prescrição?", "prioridade": 1}],
            "teses_sugeridas": [{"tese": "Tese IA", "fundamento": "art. 7º CF"}],
        }))
    monkeypatch.setattr(mts, "gw_chat", _fake_chat)

    async def _rag(*a, **k):
        return [{"conteudo": "Recurso provido. Súmula 331 TST.",
                 "titulo": "Julgado", "categoria": "jurisprudencia"}]
    monkeypatch.setattr(mts, "buscar_contexto_rag", _rag)

    async def _verificador(db, texto):
        return {"citacoes": [{
            "tipo": "sumula", "status": "verificada", "citacao": "Súmula 331 TST",
            "numero": "331", "tribunal": "TST", "orgao": None, "data": None,
            "fonte_verificacao": "base oficial interna/RAG",
            "fonte": "base oficial interna/RAG",
        }]}
    monkeypatch.setattr(mts, "verificar_jurisprudencia", _verificador)

    async def _fake_snapshot(db, **kw):
        return None
    from app.services import case_intelligence_service as cis
    monkeypatch.setattr(cis, "gravar_snapshot_seguro", _fake_snapshot)

    tese_banco = Tese(id="tb1", titulo="Tese banco", descricao="Descrição da tese",
                      fundamentacao="Súmula 331 TST", contra_argumento=None,
                      area_juridica="trabalhista", tipo=TeseTipo.escritorio,
                      status=TeseStatus.ativa, vezes_usada=0, vezes_venceu=0,
                      vezes_perdeu=0, deleted_at=None)
    db = _FakeDB([[tese_banco], []])   # fila: select Tese → select Prova

    matriz = await mts.montar_matriz(db, "u1", "case1", "trabalhista",
                                     "Fatos sanitizados suficientes para análise.")
    # O RAG produziu 1 AuthorityRecord verificado, mas NENHUMA tese sem vínculo
    # de questão o recebe (sem boost indevido de +10/+10 na forca).
    assert len(matriz["precedentes"]) == 1
    assert all(t["precedentes"] == [] for t in matriz["teses"])
    cands = [o for o in db.added if isinstance(o, ThesisCandidate)]
    assert cands and all(c.precedentes == [] for c in cands)
    # Só o fundamento pontua (15): sem boost de precedente verificado (+10)
    # nem de saldo favorável (+10) — o score agora discrimina de verdade.
    assert all(c.forca == 15 for c in cands)


async def test_montar_matriz_vincula_tese_a_questao_e_precedentes_pontuam(monkeypatch):
    """M-B3: tese vinculada à questão de origem (questao_ref da decomposição ou
    vínculo lexical determinístico) recebe os AuthorityRecords daquela questão
    via refs_por_questao — e os pesos PESO_FUNDAMENTO_VERIFICADO/
    PESO_POR_SALDO_PRECEDENTE passam a ser alcançáveis."""
    monkeypatch.setattr(mts, "get_settings", lambda: _Cfg())

    async def _fake_chat(**kw):
        return _Resp(json.dumps({
            "questoes": [{"questao": "Prescrição quinquenal?", "prioridade": 1}],
            "teses_sugeridas": [
                # Vínculo explícito da própria decomposição (questao_ref).
                {"tese": "Tese IA", "fundamento": "art. 7º CF", "questao_ref": 1},
            ],
        }))
    monkeypatch.setattr(mts, "gw_chat", _fake_chat)

    async def _rag(*a, **k):
        return [{"conteudo": "Recurso provido quanto à prescrição. Súmula 331 TST.",
                 "titulo": "Julgado", "categoria": "jurisprudencia"}]
    monkeypatch.setattr(mts, "buscar_contexto_rag", _rag)

    async def _verificador(db, texto):
        return {"citacoes": [{
            "tipo": "sumula", "status": "verificada", "citacao": "Súmula 331 TST",
            "numero": "331", "tribunal": "TST", "orgao": None, "data": None,
            "fonte_verificacao": "base oficial interna/RAG",
            "fonte": "base oficial interna/RAG",
        }]}
    monkeypatch.setattr(mts, "verificar_jurisprudencia", _verificador)

    async def _fake_snapshot(db, **kw):
        return None
    from app.services import case_intelligence_service as cis
    monkeypatch.setattr(cis, "gravar_snapshot_seguro", _fake_snapshot)

    # Tese do Banco cujo texto compartilha token relevante com a questão →
    # vínculo LEXICAL determinístico.
    tese_banco = Tese(id="tb1", titulo="Prescrição quinquenal trabalhista",
                      descricao="Aplica-se a prescrição quinquenal",
                      fundamentacao="art. 7º XXIX CF", contra_argumento=None,
                      area_juridica="trabalhista", tipo=TeseTipo.escritorio,
                      status=TeseStatus.ativa, vezes_usada=0, vezes_venceu=0,
                      vezes_perdeu=0, deleted_at=None)
    db = _FakeDB([[tese_banco], []])   # fila: select Tese → select Prova

    matriz = await mts.montar_matriz(db, "u1", "case1", "trabalhista",
                                     "Fatos sanitizados suficientes para análise.")
    cands = [o for o in db.added if isinstance(o, ThesisCandidate)]
    assert len(cands) == 2
    issue_id = matriz["questoes"][0]["id"]
    # AMBAS as teses vinculadas à questão de origem, com o precedente dela.
    for c in cands:
        assert c.issue_id == issue_id, c.tese
        assert len(c.precedentes) == 1
        assert c.precedentes[0]["status_verificacao"] == "verificada"
        assert c.precedentes[0]["favoravel"] is True
        # 15 (fundamento) + 10 (verificado) + 10 (saldo +1) = 35
        assert c.forca == 35, c.tese
    assert all(t["issue_id"] == issue_id for t in matriz["teses"])


def test_parse_questoes_extrai_questao_ref_e_descarta_fora_do_intervalo():
    out = mts._parse_questoes(json.dumps({
        "questoes": [{"questao": "Prescrição?", "prioridade": 1}],
        "teses_sugeridas": [
            {"tese": "Com ref válida", "fundamento": "art. 1º", "questao_ref": 1},
            {"tese": "Ref fora do intervalo", "questao_ref": 9},
            {"tese": "Ref inválida", "questao_ref": "banana"},
            {"tese": "Sem ref"},
        ],
    }))
    refs = [t["questao_ref"] for t in out["teses_sugeridas"]]
    assert refs == [1, None, None, None]


def test_vincular_questao_lexical_deterministico():
    i1 = _issue(id="i1", questao="Há prescrição quinquenal?")
    i2 = _issue(id="i2", questao="Nulidade da citação editalícia?")
    # Sobreposição relevante → melhor questão; sem sobreposição → None.
    assert mts._vincular_questao("prescrição do crédito", [i1, i2]) == "i1"
    assert mts._vincular_questao("vício na citação por edital",
                                 [i1, i2]) == "i2"
    assert mts._vincular_questao("tese sem relação alguma", [i1, i2]) is None
    assert mts._vincular_questao("", [i1, i2]) is None


async def test_montar_matriz_parse_falho_carrega_aviso(monkeypatch):
    """Item 10: falha de parse da decomposição aparece nos avisos da matriz e
    do snapshot (nunca silenciosa)."""
    monkeypatch.setattr(mts, "get_settings", lambda: _Cfg())

    async def _fake_chat(**kw):
        return _Resp("resposta sem json nenhum")
    monkeypatch.setattr(mts, "gw_chat", _fake_chat)

    async def _rag_vazio(*a, **k):
        return []
    monkeypatch.setattr(mts, "buscar_contexto_rag", _rag_vazio)

    capturado = {}

    async def _fake_snapshot(db, **kw):
        capturado.update(kw)
        return None
    from app.services import case_intelligence_service as cis
    monkeypatch.setattr(cis, "gravar_snapshot_seguro", _fake_snapshot)

    db = _FakeDB([[], []])   # fila: select Tese → select Prova
    matriz = await mts.montar_matriz(db, "u1", "case1", "trabalhista",
                                     "Fatos sanitizados suficientes para análise.")
    assert matriz["avisos"] == [mts.AVISO_FALHA_PARSE]
    assert capturado["payload"]["avisos"] == [mts.AVISO_FALHA_PARSE]


# ── Aprovação HITL + auditoria ───────────────────────────────────────────────

async def test_aprovar_tese_audita_e_marca():
    cand = _cand()
    db = _FakeDB([cand])
    out = await mts.aprovar_tese(db, "t1", _user(UserRole.advogado),
                                 decisao="aprovada")
    assert out.status == "aprovada"
    assert out.aprovado_por == "u1" and out.aprovado_em is not None
    logs = [o for o in db.added if isinstance(o, AuditLog)]
    assert len(logs) == 1
    assert logs[0].entidade == "thesis_candidates" and logs[0].registro_id == "t1"
    assert db.commits == 1


async def test_descartar_tese_tambem_audita():
    cand = _cand()
    db = _FakeDB([cand])
    out = await mts.aprovar_tese(db, "t1", _user(UserRole.socio),
                                 decisao="descartada")
    assert out.status == "descartada"
    assert [o for o in db.added if isinstance(o, AuditLog)]


async def test_aprovar_409_se_ja_decidida():
    db = _FakeDB([_cand(status="aprovada")])
    with pytest.raises(HTTPException) as exc:
        await mts.aprovar_tese(db, "t1", _user(UserRole.advogado))
    assert exc.value.status_code == 409
    assert db.commits == 0


async def test_aprovar_404_se_inexistente():
    with pytest.raises(HTTPException) as exc:
        await mts.aprovar_tese(_FakeDB([None]), "tX", _user(UserRole.advogado))
    assert exc.value.status_code == 404


async def test_aprovar_decisao_invalida_rejeitada():
    with pytest.raises(ValueError):
        await mts.aprovar_tese(_FakeDB([]), "t1", _user(UserRole.advogado),
                               decisao="chute")


async def test_endpoint_aprovar_403_para_estagiario():
    from app.routers.matriz_teses import aprovar
    with pytest.raises(HTTPException) as exc:
        await aprovar(case_id="case1", tese_id="t1",
                      db=_FakeDB([]), cu=_user(UserRole.estagiario))
    assert exc.value.status_code == 403


async def test_endpoint_montar_403_para_estagiario():
    from app.routers.matriz_teses import montar
    with pytest.raises(HTTPException) as exc:
        await montar(case_id="case1", body=None, db=_FakeDB([]),
                     cu=_user(UserRole.estagiario))
    assert exc.value.status_code == 403


# ── Endpoint /montar: schema Pydantic + área canônica (itens 6/16) ───────────

def test_montar_matriz_in_limites_do_schema():
    from pydantic import ValidationError
    from app.routers.matriz_teses import MontarMatrizIn

    MontarMatrizIn(area="trabalhista", fatos="x" * 30000)  # dentro dos limites
    with pytest.raises(ValidationError):
        MontarMatrizIn(area="x" * 61)
    with pytest.raises(ValidationError):
        MontarMatrizIn(fatos="x" * 30001)


async def test_endpoint_montar_area_fora_do_canonico_422(monkeypatch):
    from app.routers import matriz_teses as rt

    async def _acesso(db, cu, case_id):
        return type("C", (), {"area": None, "descricao_fatos": "x" * 40})()
    monkeypatch.setattr(rt, "verificar_acesso_caso", _acesso)

    with pytest.raises(HTTPException) as exc:
        await rt.montar(case_id="case1",
                        body=rt.MontarMatrizIn(area="banana jurídica"),
                        db=_FakeDB([]), cu=_user(UserRole.advogado))
    assert exc.value.status_code == 422
    assert exc.value.detail["areas_validas"]   # lista das áreas canônicas


async def test_endpoint_montar_area_normalizada_nunca_crua_no_prompt(monkeypatch):
    from app.routers import matriz_teses as rt

    async def _acesso(db, cu, case_id):
        return type("C", (), {"area": None, "descricao_fatos": None})()
    monkeypatch.setattr(rt, "verificar_acesso_caso", _acesso)

    capturado = {}

    async def _fake_montar(db, uid, cid, area, fatos):
        capturado["area"] = area
        return {"ok": True}
    monkeypatch.setattr(rt.mts, "montar_matriz", _fake_montar)

    await rt.montar(case_id="case1",
                    body=rt.MontarMatrizIn(area="Direito do Trabalho",
                                           fatos="Fatos suficientes para a matriz."),
                    db=_FakeDB([]), cu=_user(UserRole.advogado))
    assert capturado["area"] == "trabalhista"   # canônico, nunca o texto cru


def test_endpoints_decidir_com_rate_limit():
    """Item 16: aprovar/descartar têm rate limit próprio na rota."""
    from app.main import app
    rotas = {getattr(r, "path", ""): r for r in app.routes}
    for sufixo in ("/aprovar", "/descartar"):
        rota = next(r for p, r in rotas.items()
                    if p.endswith(f"/matriz-teses/teses/{{tese_id}}{sufixo}"))
        assert rota.dependencies   # Depends(rate_limit("matriz-teses-decidir", 15))


# ── Flag OFF = pipeline de peças BYTE-IDÊNTICO ───────────────────────────────

async def test_flag_off_bloco_vazio_sem_tocar_no_banco(monkeypatch):
    from app.services import peca_service

    class _CfgOff:
        PECAS_PESQUISA_QUESTOES_ENABLED = False
    monkeypatch.setattr(peca_service, "get_settings", lambda: _CfgOff())
    # _FakeDB SEM fila: qualquer execute levantaria IndexError — flag OFF não
    # pode nem consultar o banco (pipeline inalterado byte a byte).
    out = await peca_service._bloco_questoes_estruturado(_FakeDB([]), "case1")
    assert out == ""


async def test_flag_on_sem_matriz_bloco_vazio(monkeypatch):
    from app.services import peca_service

    class _CfgOn:
        PECAS_PESQUISA_QUESTOES_ENABLED = True
    monkeypatch.setattr(peca_service, "get_settings", lambda: _CfgOn())
    db = _FakeDB([[]])  # caso sem LegalIssues → matriz não montada → ""
    out = await peca_service._bloco_questoes_estruturado(db, "case1")
    assert out == ""


async def test_flag_on_com_matriz_gera_bloco_por_questao(monkeypatch):
    from app.services import peca_service

    class _CfgOn:
        PECAS_PESQUISA_QUESTOES_ENABLED = True
    monkeypatch.setattr(peca_service, "get_settings", lambda: _CfgOn())

    issue = _issue()
    rec = AuthorityRecord(
        id="a1", case_id="case1", tribunal="TST", processo_ref="331",
        orgao=None, data_julgamento=None, tema=issue.questao,
        trecho="Verbete aplicável à terceirização.",
        fonte_oficial="base oficial interna/RAG",
        status_verificacao="verificada", favoravel=True)
    db = _FakeDB([[issue], [rec]])
    out = await peca_service._bloco_questoes_estruturado(db, "case1")
    assert "PESQUISA JURISPRUDENCIAL POR QUESTÃO" in out
    assert issue.questao in out
    assert "TST 331" in out and "base oficial interna/RAG" in out


async def test_flag_on_erro_no_service_degrada_para_vazio(monkeypatch):
    from app.services import peca_service

    class _CfgOn:
        PECAS_PESQUISA_QUESTOES_ENABLED = True
    monkeypatch.setattr(peca_service, "get_settings", lambda: _CfgOn())
    # fila vazia → execute levanta IndexError → helper degrada para "" (fail-safe)
    out = await peca_service._bloco_questoes_estruturado(_FakeDB([]), "case1")
    assert out == ""
