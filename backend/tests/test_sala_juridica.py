"""Sala Jurídica Conversacional — contratos de payload e invariantes (V1).

Sem chamadas de IA nem banco: valida os schemas Pydantic (barreira 422 antes
do gateway) e as invariantes do service (mapeamento modo→task_type completo,
congelamento pós-conversão).
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.models.legal_chat import CHAT_MODOS, SESSION_STATUS
from app.schemas.legal_chat import (
    MAX_MENSAGEM_CHARS,
    ConverterRequest,
    EstadoUpdate,
    MensagemCreate,
    SaidaAlternativaRequest,
    SessaoUpdate,
)
from app.services.legal_chat_service import MODO_INSTRUCAO, MODO_TASK_TYPE


# ── mensagens ────────────────────────────────────────────────────────────────

def test_mensagem_modo_invalido_422():
    with pytest.raises(ValidationError):
        MensagemCreate(conteudo="analise", modo="modo_inexistente")


def test_mensagem_acima_do_teto_422():
    with pytest.raises(ValidationError):
        MensagemCreate(conteudo="x" * (MAX_MENSAGEM_CHARS + 1))


def test_mensagem_vazia_422():
    with pytest.raises(ValidationError):
        MensagemCreate(conteudo="")


def test_todos_os_modos_roteiam_para_task_type():
    # Nenhum modo do seletor pode ficar sem rota no gateway (KeyError em prod).
    assert set(MODO_TASK_TYPE) == CHAT_MODOS
    assert set(MODO_INSTRUCAO) == CHAT_MODOS


# ── estado jurídico ──────────────────────────────────────────────────────────

def test_estado_chave_desconhecida_422():
    with pytest.raises(ValidationError):
        EstadoUpdate(estado={"achismos": []})


def test_estado_valor_nao_lista_422():
    with pytest.raises(ValidationError):
        EstadoUpdate(estado={"fatos": "não é lista"})


def test_estado_valido_passa():
    e = EstadoUpdate(estado={"fatos": [{"texto": "x", "classificacao": "alegado"}]})
    assert e.estado["fatos"][0]["classificacao"] == "alegado"


# ── sessão ───────────────────────────────────────────────────────────────────

def test_sessao_status_invalido_422():
    with pytest.raises(ValidationError):
        SessaoUpdate(status="status_inexistente")


def test_sessao_status_validos_aceitos():
    for status in SESSION_STATUS:
        assert SessaoUpdate(status=status).status == status


# ── conversão em caso ────────────────────────────────────────────────────────

def test_converter_exige_confirmacoes_explicitas():
    with pytest.raises(ValidationError):
        ConverterRequest(
            novo_cliente_nome="Fulano", area="civel", titulo_caso="Caso X",
            advogado_responsavel_id="u1",
            confirmo_conflito_verificado=False,
            confirmo_dados_revisados=True,
        )


def test_congelamento_bloqueia_escrita():
    from datetime import datetime, timezone
    from app.models.legal_chat import LegalChatSession
    from app.services.legal_chat_service import exigir_nao_congelada

    sessao = LegalChatSession(id="s1", titulo="t", created_by="u1")
    exigir_nao_congelada(sessao)  # sem congelamento: passa
    sessao.frozen_at = datetime.now(timezone.utc)
    with pytest.raises(HTTPException) as exc:
        exigir_nao_congelada(sessao)
    assert exc.value.status_code == 409


# ── saídas alternativas ──────────────────────────────────────────────────────

def test_descartar_sem_justificativa_422():
    with pytest.raises(ValidationError):
        SaidaAlternativaRequest(acao="descartar", justificativa="  ")


def test_arquivar_sem_justificativa_ok():
    assert SaidaAlternativaRequest(acao="arquivar").acao == "arquivar"


# ── extração automática de estado (V2) ───────────────────────────────────────

async def _rodar_extracao(monkeypatch, conteudo_llm: str):
    from app.services import legal_chat_service as svc

    async def fake_run_ai_task(**kwargs):
        return {"conteudo": conteudo_llm}

    import app.services.ai.core.orchestrator as orch
    monkeypatch.setattr(orch, "run_ai_task", fake_run_ai_task)
    return await svc._extrair_estado_automatico(
        None, None, estado_atual={"fontes": []},
        pergunta="p", resposta="r",
    )


@pytest.mark.anyio
async def test_extracao_estado_json_valido(monkeypatch):
    saida = await _rodar_extracao(
        monkeypatch,
        '{"fatos": [{"texto": "x", "classificacao": "alegado"}], "_resumo": "ok"}',
    )
    assert saida is not None
    assert saida["fatos"][0]["classificacao"] == "alegado"
    assert saida["_resumo"] == "ok"


@pytest.mark.anyio
async def test_extracao_estado_json_invalido_fail_soft(monkeypatch):
    assert await _rodar_extracao(monkeypatch, "não sei responder em JSON") is None


@pytest.mark.anyio
async def test_extracao_estado_chave_desconhecida_fail_soft(monkeypatch):
    assert await _rodar_extracao(monkeypatch, '{"achismos": []}') is None
