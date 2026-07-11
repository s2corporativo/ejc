"""Provas FALTANTES sugeridas por IA — POST /casos/{case_id}/provas/sugerir-faltantes.

Padrão test_provas.py (sem Postgres real): handler chamado diretamente com fake
de sessão; gateway de IA monkeypatched. Cobre: parser/validador defensivo do
JSON da IA (cerca markdown, criticidade inválida, dedupe contra existentes,
itens malformados), gate de role (piso advogado+), ownership, AILog registrado
e degradação graciosa quando o provider falha (lista vazia + aviso, nunca 500).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.ai_log import AILog
from app.models.case import Case
from app.models.prova import Prova
from app.models.user import User, UserRole


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


def _user(role: UserRole, uid: str = "u1") -> User:
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
    base = dict(id="p1", case_id="case1", tipo="documental", titulo="Contrato assinado",
                descricao=None, document_id=None, tese_id=None,
                fato_probando="Existência do vínculo", ordem=0,
                deleted_at=None, created_at=None)
    base.update(kw)
    return Prova(**base)


def _gw_resp(texto: str) -> SimpleNamespace:
    return SimpleNamespace(texto=texto, modelo="claude-x", provedor="anthropic",
                           input_tokens=100, output_tokens=50)


async def _entidades_vazias(db, case_id):
    return {}


# ── Rota montada ──────────────────────────────────────────────────────────────

def test_rota_sugerir_faltantes_montada_em_main():
    from app.main import app
    paths = {getattr(r, "path", "") for r in app.routes}
    assert any(p.endswith("/casos/{case_id}/provas/sugerir-faltantes") for p in paths)


# ── Parser/validador defensivo ────────────────────────────────────────────────

def test_parser_json_puro_valido():
    from app.routers.provas import _parse_sugestoes
    texto = ('[{"titulo": "Laudo pericial", "por_que_importa": "Comprova o dano", '
             '"como_obter": "Perícia judicial", "criticidade": "alta"}]')
    out = _parse_sugestoes(texto, [])
    assert len(out) == 1
    assert out[0]["titulo"] == "Laudo pericial"
    assert out[0]["criticidade"] == "alta"
    assert out[0]["como_obter"] == "Perícia judicial"


def test_parser_extrai_json_de_cerca_markdown_com_prosa():
    from app.routers.provas import _parse_sugestoes
    texto = ("Claro! Aqui estão as sugestões:\n```json\n"
             '[{"titulo": "Ata Notarial", "por_que_importa": "Prova do fato", '
             '"como_obter": "Cartório", "criticidade": "media"}]\n```\nEspero ter ajudado.')
    out = _parse_sugestoes(texto, [])
    assert [s["titulo"] for s in out] == ["Ata Notarial"]


def test_parser_aceita_objeto_com_lista_interna():
    from app.routers.provas import _parse_sugestoes
    texto = '{"sugestoes": [{"titulo": "Extrato bancário", "criticidade": "baixa"}]}'
    out = _parse_sugestoes(texto, [])
    assert out[0]["titulo"] == "Extrato bancário"
    assert out[0]["criticidade"] == "baixa"
    assert out[0]["por_que_importa"] == ""  # campo ausente degrada p/ vazio


def test_parser_texto_sem_json_retorna_vazio():
    from app.routers.provas import _parse_sugestoes
    assert _parse_sugestoes("Não consegui gerar sugestões.", []) == []
    assert _parse_sugestoes("", []) == []
    assert _parse_sugestoes("[]", []) == []


def test_parser_criticidade_invalida_vira_media_e_acento_normalizado():
    from app.routers.provas import _parse_sugestoes
    texto = ('[{"titulo": "Orçamento", "criticidade": "URGENTÍSSIMA"},'
             ' {"titulo": "Laudo", "criticidade": "Média"}]')
    out = _parse_sugestoes(texto, [])
    assert [s["criticidade"] for s in out] == ["media", "media"]


def test_parser_descarta_itens_malformados_sem_derrubar_o_lote():
    from app.routers.provas import _parse_sugestoes
    texto = ('["string solta", {"por_que_importa": "sem título"}, '
             '{"titulo": "   "}, {"titulo": "Orçamento", "criticidade": "alta"}]')
    out = _parse_sugestoes(texto, [])
    assert [s["titulo"] for s in out] == ["Orçamento"]


def test_parser_deduplica_contra_existentes_e_entre_si():
    from app.routers.provas import _parse_sugestoes
    texto = ('[{"titulo": "Contrato Assinado"},'   # já existe (caixa diferente)
             ' {"titulo": "Ata  notarial"},'
             ' {"titulo": "ATA NOTARIAL"},'        # repetida entre si
             ' {"titulo": "Orçamento"}]')
    out = _parse_sugestoes(texto, ["Contrato assinado"])
    assert [s["titulo"] for s in out] == ["Ata  notarial", "Orçamento"]


def test_parser_limita_quantidade_de_sugestoes():
    import json as _json
    from app.routers.provas import _MAX_SUGESTOES, _parse_sugestoes
    itens = [{"titulo": f"Prova {i}"} for i in range(30)]
    out = _parse_sugestoes(_json.dumps(itens), [])
    assert len(out) == _MAX_SUGESTOES


# ── Gate de role (piso advogado+) ─────────────────────────────────────────────

@pytest.mark.parametrize("role", [UserRole.advogado_auxiliar, UserRole.estagiario,
                                  UserRole.secretaria, UserRole.financeiro])
async def test_gate_role_abaixo_de_advogado_403(role):
    from app.routers.provas import sugerir_provas_faltantes
    db = _FakeDB([])  # 403 ANTES de qualquer query (nem toca o banco)
    with pytest.raises(HTTPException) as exc:
        await sugerir_provas_faltantes(case_id="case1", db=db, cu=_user(role))
    assert exc.value.status_code == 403


async def test_advogado_sem_acesso_ao_caso_403(monkeypatch):
    from app.routers.provas import sugerir_provas_faltantes
    db = _FakeDB([_case(advogado_responsavel_id="outro",
                        advogado_auxiliar_id="outro2")])
    with pytest.raises(HTTPException) as exc:
        await sugerir_provas_faltantes(case_id="case1", db=db,
                                       cu=_user(UserRole.advogado, "u1"))
    assert exc.value.status_code == 403


# ── Fluxo feliz + AILog + degradação graciosa ─────────────────────────────────

async def test_sucesso_filtra_existentes_e_registra_ailog(monkeypatch):
    from app.routers import provas as mod
    from app.services import ai_gateway
    from app.services.ai import entidades_caso

    async def _fake_chat(messages, **kw):
        # Contexto determinístico chega no user message.
        assert kw.get("task_type") == "analise_juridica"
        assert "Provas JÁ EXISTENTES" in messages[1]["content"]
        assert "Contrato assinado" in messages[1]["content"]
        return _gw_resp('[{"titulo": "Contrato assinado", "criticidade": "alta"},'
                        ' {"titulo": "Extrato bancário", "por_que_importa": '
                        '"Comprova os pagamentos", "como_obter": "Banco/cliente", '
                        '"criticidade": "alta"}]')

    monkeypatch.setattr(ai_gateway, "chat", _fake_chat)
    monkeypatch.setattr(entidades_caso, "entidades_do_caso", _entidades_vazias)

    db = _FakeDB([_case(advogado_responsavel_id="u1"), [_prova()]])
    out = await mod.sugerir_provas_faltantes(case_id="case1", db=db,
                                             cu=_user(UserRole.advogado, "u1"))
    # A prova que JÁ existe foi filtrada; só a faltante volta.
    assert [s["titulo"] for s in out["data"]] == ["Extrato bancário"]
    assert out["total"] == 1
    assert out["aviso"] is None
    assert out["provedor"] == "anthropic"
    # AILog registrado (HITL) e persistido.
    logs = [o for o in db.added if isinstance(o, AILog)]
    assert len(logs) == 1
    assert logs[0].case_id == "case1"
    assert "PROVAS_FALTANTES" in logs[0].prompt_sanitizado
    assert db.commits == 1
    # Nenhuma Prova é criada automaticamente (são SUGESTÕES).
    assert [o for o in db.added if isinstance(o, Prova)] == []


async def test_resposta_invalida_da_ia_degrada_para_lista_vazia_com_aviso(monkeypatch):
    from app.routers import provas as mod
    from app.services import ai_gateway
    from app.services.ai import entidades_caso

    async def _fake_chat(messages, **kw):
        return _gw_resp("Desculpe, não consegui montar o JSON pedido.")

    monkeypatch.setattr(ai_gateway, "chat", _fake_chat)
    monkeypatch.setattr(entidades_caso, "entidades_do_caso", _entidades_vazias)

    db = _FakeDB([_case(advogado_responsavel_id="u1"), []])
    out = await mod.sugerir_provas_faltantes(case_id="case1", db=db,
                                             cu=_user(UserRole.advogado, "u1"))
    assert out["data"] == [] and out["total"] == 0
    assert out["aviso"]  # aviso presente
    # Mesmo sem sugestões o uso de IA é logado (houve chamada real).
    assert any(isinstance(o, AILog) for o in db.added)


async def test_provider_indisponivel_nunca_500(monkeypatch):
    from app.routers import provas as mod
    from app.services import ai_gateway
    from app.services.ai import entidades_caso

    async def _boom(messages, **kw):
        raise RuntimeError("provider down")

    monkeypatch.setattr(ai_gateway, "chat", _boom)
    monkeypatch.setattr(entidades_caso, "entidades_do_caso", _entidades_vazias)

    db = _FakeDB([_case(advogado_responsavel_id="u1"), []])
    out = await mod.sugerir_provas_faltantes(case_id="case1", db=db,
                                             cu=_user(UserRole.advogado, "u1"))
    assert out["data"] == [] and "indisponível" in out["aviso"]
    assert db.commits == 0  # nada persistido quando a IA nem respondeu
