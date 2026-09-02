"""Regressões unitárias da auditoria ponta a ponta de Clientes — 01/09/2026.

Sem banco/serviços externos: cobre os contratos de segurança que não podem
regredir mesmo quando a suíte de integração com Postgres estiver desabilitada.
"""
import inspect
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError


def test_client_response_nao_serializa_documento_em_claro():
    from app.schemas.client import ClientResponse

    resposta = ClientResponse.model_validate({
        "id": "cliente-1",
        "tipo": "PF",
        "nome": "Cliente Teste",
        "cpf": "11144477735",
        "status": "ativo",
        "created_at": datetime.now(timezone.utc),
    }).model_dump()

    assert "cpf" not in resposta
    assert "cnpj" not in resposta
    assert resposta["documento_exibicao"] == "***.444.777-**"


def test_client_response_mascara_cnpj_sem_expor_chave_bruta():
    from app.schemas.client import ClientResponse

    resposta = ClientResponse.model_validate({
        "id": "cliente-2",
        "tipo": "PJ",
        "razao_social": "Empresa Teste Ltda",
        "cnpj": "12345678000195",
        "status": "ativo",
        "created_at": datetime.now(timezone.utc),
    }).model_dump()

    assert "cpf" not in resposta
    assert "cnpj" not in resposta
    assert resposta["documento_exibicao"] == "**.345.678/****-**"


def test_client_response_preserva_alerta_de_documento_indecifravel():
    from app.models.client import PII_INDECIFRAVEL
    from app.schemas.client import ClientResponse

    resposta = ClientResponse.model_validate({
        "id": "cliente-3",
        "tipo": "PF",
        "nome": "Cliente Teste",
        "cpf": PII_INDECIFRAVEL,
        "status": "ativo",
        "created_at": datetime.now(timezone.utc),
    }).model_dump()

    assert "cpf" not in resposta
    assert "cnpj" not in resposta
    assert resposta["documento_exibicao"] == PII_INDECIFRAVEL


def test_client_response_openapi_nao_anuncia_documento_bruto():
    from app.schemas.client import ClientResponse

    schema = ClientResponse.model_json_schema(mode="serialization")
    propriedades = schema.get("properties", {})

    assert "cpf" not in propriedades
    assert "cnpj" not in propriedades
    assert "documento_exibicao" in propriedades


def test_criar_acesso_portal_respeita_minimo_canonico_de_senha():
    from app.routers.clients import CriarAcessoReq
    from app.services.security_service import SENHA_MIN_LEN

    assert SENHA_MIN_LEN == 10
    with pytest.raises(ValidationError):
        CriarAcessoReq(email="cliente@example.com", senha_inicial="Ab1!5678")


def test_gate_advogado_bloqueia_secretaria_para_ia_estrategica():
    from app.core.security import requer_advogado

    secretaria = SimpleNamespace(role="secretaria")
    with pytest.raises(HTTPException) as exc:
        requer_advogado(
            secretaria,
            detail="Análise estratégica de cliente restrita a advogados",
        )
    assert exc.value.status_code == 403


def test_gate_advogado_permite_advogado():
    from app.core.security import requer_advogado

    advogado = SimpleNamespace(role="advogado")
    requer_advogado(advogado)


def test_ia_cliente_usa_orquestrador_sem_rag_forcado_e_hitl_canonico():
    from app.routers.clients import ia_analise_cliente

    fonte = inspect.getsource(ia_analise_cliente)
    assert "orchestrator.run" in fonte
    assert "ai_gateway.processar_demanda" not in fonte
    assert 'task_type="resumo"' in fonte
    assert 'usar_rag=False' in fonte
    assert '"requer_revisao"' in fonte
    assert '"status_hitl"' in fonte
    assert '"aviso_hitl"' in fonte
    assert "Total de casos não excluídos" in fonte
    assert "Casos ativos no cadastro" not in fonte


def test_anonimizacao_audita_codigo_controlado_sem_texto_livre():
    from app.services.client_anonimizacao import anonimizar_cliente

    fonte = inspect.getsource(anonimizar_cliente)
    assert "sanitizar_pii" not in fonte
    assert '"codigo_justificativa"' in fonte
    assert "OVERRIDE_REPRESENTACAO_ATIVA" in fonte
    assert "Justificativa obrigatória" in fonte
    assert "justificativa_sanitizada" not in fonte
