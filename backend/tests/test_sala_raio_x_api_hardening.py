"""Contratos de hardening das superfícies Sala Jurídica e Raio-X."""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import legal_chat, raio_x


def _user(role: str):
    return SimpleNamespace(role=SimpleNamespace(value=role))


@pytest.mark.parametrize(
    "role",
    ["superadmin", "admin", "socio", "advogado", "advogado_auxiliar", "estagiario"],
)
def test_raio_x_aceita_exatamente_equipe_juridica(role):
    raio_x._exigir_acesso_raio_x(_user(role))


@pytest.mark.parametrize("role", ["financeiro", "secretaria", "cliente_externo"])
def test_raio_x_recusa_perfis_fora_da_equipe_juridica(role):
    with pytest.raises(HTTPException) as exc:
        raio_x._exigir_acesso_raio_x(_user(role))
    assert exc.value.status_code == 403


@pytest.mark.parametrize(
    ("role", "esperado"),
    [
        ("superadmin", True),
        ("admin", True),
        ("socio", True),
        ("advogado", True),
        ("advogado_auxiliar", True),
        ("estagiario", False),
        ("financeiro", False),
    ],
)
def test_raio_x_ia_cara_preserva_gate_mais_restritivo(role, esperado):
    assert raio_x._permitido_ia_advogado(_user(role)) is esperado


@pytest.mark.anyio
async def test_sala_adapter_usa_gate_juridico_central():
    permitido = _user("estagiario")
    assert await legal_chat.exigir_equipe_juridica(permitido) is permitido

    with pytest.raises(HTTPException) as exc:
        await legal_chat.exigir_equipe_juridica(_user("financeiro"))
    assert exc.value.status_code == 403


def test_sala_nao_persiste_excecao_bruta_da_extracao():
    source = inspect.getsource(legal_chat.anexar_documentos)
    assert 'resultado = {"ok": False, "erro": str(exc)' not in source
    assert "exception_type=%s" in source
    assert "O arquivo foi preservado para revisão manual" in source


def test_raio_x_download_nao_grava_filename_no_audit_log():
    source = inspect.getsource(raio_x.download)
    assert "detalhes=doc.nome_original" not in source
    assert "Download de documento preliminar do Raio-X" in source


def test_raio_x_listagem_impoe_limites_nos_filtros_textuais():
    assinatura = inspect.signature(raio_x.listar)
    assert assinatura.parameters["search"].default.max_length == 200
    assert assinatura.parameters["status"].default.max_length == 40
    assert assinatura.parameters["area"].default.max_length == 50
    assert assinatura.parameters["risco"].default.max_length == 30
