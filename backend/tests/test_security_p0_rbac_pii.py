from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers.clients import _req_clientes_leitura
from app.routers.documents import _verificar_acesso_documento
from app.routers.fees import _req_financeiro_mutacao, _ve_financeiro_total
from app.routers.search import _mascarar_documento


def user(role: str, user_id: str = "user-1", client_id: str | None = None):
    return SimpleNamespace(
        id=user_id,
        role=SimpleNamespace(value=role),
        client_id=client_id,
    )


def document(
    *,
    case_id=None,
    client_id=None,
    uploaded_by="other",
    confidentiality="normal",
):
    return SimpleNamespace(
        case_id=case_id,
        client_id=client_id,
        uploaded_by=uploaded_by,
        confidencialidade=SimpleNamespace(value=confidentiality),
    )


@pytest.mark.parametrize("role", ["superadmin", "admin", "socio", "financeiro"])
def test_perfis_fiduciarios_veem_e_mutam_financeiro(role):
    current = user(role)
    assert _ve_financeiro_total(current) is True
    assert _req_financeiro_mutacao(current) is current


@pytest.mark.parametrize(
    "role",
    ["advogado", "advogado_auxiliar", "secretaria", "estagiario", "cliente_externo"],
)
def test_perfis_nao_fiduciarios_nao_mutam_financeiro(role):
    current = user(role)
    assert _ve_financeiro_total(current) is False
    with pytest.raises(HTTPException) as exc:
        _req_financeiro_mutacao(current)
    assert exc.value.status_code == 403


@pytest.mark.parametrize(
    "role", ["superadmin", "admin", "socio", "advogado", "secretaria"]
)
def test_matriz_crm_permite_leitura_integral_apenas_a_perfis_definidos(role):
    current = user(role)
    assert _req_clientes_leitura(current) is current


@pytest.mark.parametrize(
    "role", ["financeiro", "advogado_auxiliar", "estagiario", "cliente_externo"]
)
def test_matriz_crm_bloqueia_perfis_fora_do_escopo(role):
    with pytest.raises(HTTPException) as exc:
        _req_clientes_leitura(user(role))
    assert exc.value.status_code == 403


def test_mascara_cpf_cnpj_sem_retornar_documento_completo():
    cpf = _mascarar_documento("123.456.789-09")
    cnpj = _mascarar_documento("12.345.678/0001-90")
    assert cpf == "***.456.789-**"
    assert cnpj == "**.345.678/****-**"
    assert "12345678909" not in cpf.replace(".", "").replace("-", "")
    assert "12345678000190" not in (
        cnpj.replace(".", "").replace("/", "").replace("-", "")
    )


def test_mascara_documento_nulo_sem_erro_ou_exposicao():
    assert _mascarar_documento(None) == ""


@pytest.mark.asyncio
async def test_gestao_acessa_documento_avulso_sem_consulta_adicional():
    await _verificar_acesso_documento(
        None,
        user("socio", user_id="s1"),
        document(client_id="client-1", uploaded_by="u2"),
    )


@pytest.mark.asyncio
async def test_uploader_acessa_documento_avulso_proprio():
    current = user("advogado", user_id="u1")
    doc = document(uploaded_by="u1")
    await _verificar_acesso_documento(None, current, doc)


@pytest.mark.asyncio
async def test_cliente_externo_acessa_somente_documento_normal_do_proprio_cliente():
    current = user("cliente_externo", client_id="client-1")
    await _verificar_acesso_documento(
        None,
        current,
        document(client_id="client-1", confidentiality="normal"),
    )
    with pytest.raises(HTTPException) as exc:
        await _verificar_acesso_documento(
            None,
            current,
            document(client_id="client-1", confidentiality="interno"),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_documento_orfao_de_outro_usuario_e_bloqueado():
    with pytest.raises(HTTPException) as exc:
        await _verificar_acesso_documento(
            None,
            user("advogado", user_id="u1"),
            document(uploaded_by="u2"),
        )
    assert exc.value.status_code == 403
