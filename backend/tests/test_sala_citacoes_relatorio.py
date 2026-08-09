"""Regressão: relatório do citation gate não pode virar lista de chaves."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.models.legal_chat import (
    LegalChatAttachment,
    LegalChatMessage,
    LegalChatSession,
    LegalChatStateVersion,
)
from app.schemas.legal_chat import MensagemCreate


class _Result:
    def __init__(self, itens):
        self._itens = list(itens)

    def scalars(self):
        return self

    def all(self):
        return self._itens

    def scalar_one_or_none(self):
        return self._itens[0] if self._itens else None


class _FakeDB:
    def __init__(self, sessao):
        self.sessao = sessao
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def execute(self, stmt, params=None):
        descr = getattr(stmt, "column_descriptions", None)
        if not descr:
            return _Result([])
        entity = descr[0]["entity"]
        if entity is LegalChatMessage:
            return _Result([])
        if entity is LegalChatAttachment:
            return _Result([])
        if entity is LegalChatStateVersion:
            return _Result([])
        if entity is LegalChatSession:
            return _Result([self.sessao])
        return _Result([])


@pytest.mark.anyio
async def test_enviar_mensagem_persiste_e_serializa_somente_lista_interna_de_citacoes(
    monkeypatch,
):
    from app.core.config import get_settings
    from app.services import legal_chat_service as svc
    import app.services.ai.core.orchestrator as orch

    sessao = LegalChatSession(id="s-cit", titulo="Teste", created_by="u1")
    db = _FakeDB(sessao)
    citacao = {"trecho": "art. 5º", "status": "verificada"}

    async def fake_run_ai_task(**kwargs):
        return {
            "conteudo": "Resposta fundamentada",
            "custo_estimado_brl": 0,
            "skills_nativas": ["pesquisa"],
            "fontes": [{"titulo": "Fonte", "fonte": "oficial"}],
            "alertas": [],
            "citacoes": {
                "total": 1,
                "confirmadas": 1,
                "nao_encontradas": 0,
                "citacoes": [citacao],
            },
        }

    monkeypatch.setattr(orch, "run_ai_task", fake_run_ai_task)
    monkeypatch.setattr(get_settings(), "SALA_JURIDICA_AUTO_ESTADO", False)

    resposta = await svc.enviar_mensagem(
        db,
        sessao,
        MensagemCreate(conteudo="analise"),
        SimpleNamespace(id="u1", role="advogado"),
    )

    mensagens_ia = [
        item
        for item in db.added
        if isinstance(item, LegalChatMessage) and item.autor == "ia"
    ]
    assert len(mensagens_ia) == 1
    assert mensagens_ia[0].citacoes == [citacao]
    assert resposta["mensagem_ia"]["citacoes"] == [citacao]
    assert "total" not in resposta["mensagem_ia"]["citacoes"]
    assert "confirmadas" not in resposta["mensagem_ia"]["citacoes"]
