"""Token de download assinado dos PDFs Visual Law (DOC-086/DOC-087).

O UUID sozinho autorizava o download a qualquer usuário autenticado que
conhecesse o id. O token (HMAC-SHA256 sobre SECRET_KEY) amarra o artefato ao
usuário que o gerou (e, quando aplicável, ao cliente/caso), com expiração
curta. Testes puros — sem DB/rede."""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services import visual_law_files as vlf

_AID = "11111111-2222-4333-8444-555555555555"


def _cu(uid: str):
    return SimpleNamespace(id=uid)


def test_token_roundtrip_valido():
    tok = vlf.emitir_token(_AID, user_id="u1")
    payload = vlf.validar_token(tok, _AID, _cu("u1"))
    assert payload["a"] == _AID and payload["u"] == "u1"


def test_token_de_outro_usuario_rejeitado():
    tok = vlf.emitir_token(_AID, user_id="u1")
    with pytest.raises(HTTPException) as ei:
        vlf.validar_token(tok, _AID, _cu("u2"))
    assert ei.value.status_code == 403


def test_token_para_outro_arquivo_rejeitado():
    outro = "99999999-2222-4333-8444-555555555555"
    tok = vlf.emitir_token(_AID, user_id="u1")
    with pytest.raises(HTTPException) as ei:
        vlf.validar_token(tok, outro, _cu("u1"))
    assert ei.value.status_code == 403


def test_token_ausente_rejeitado():
    with pytest.raises(HTTPException) as ei:
        vlf.validar_token("", _AID, _cu("u1"))
    assert ei.value.status_code == 403


def test_token_adulterado_rejeitado():
    tok = vlf.emitir_token(_AID, user_id="u1")
    corpo, _, _sig = tok.partition(".")
    forjado = f"{corpo}.QUALQUERASSINATURAFALSA"
    with pytest.raises(HTTPException) as ei:
        vlf.validar_token(forjado, _AID, _cu("u1"))
    assert ei.value.status_code == 403


def test_token_expirado_rejeitado():
    tok = vlf.emitir_token(_AID, user_id="u1", ttl=-1)  # já expirado
    with pytest.raises(HTTPException) as ei:
        vlf.validar_token(tok, _AID, _cu("u1"))
    assert ei.value.status_code == 403
    assert "expirad" in ei.value.detail.lower()


def test_token_binding_cliente_ripd():
    # DOC-087: o RIPD amarra também o client_id; download reavalia o vínculo.
    tok = vlf.emitir_token(_AID, user_id="u1", client_id="cli-1")
    assert vlf.validar_token(tok, _AID, _cu("u1"), client_id="cli-1")["c"] == "cli-1"
    with pytest.raises(HTTPException) as ei:
        vlf.validar_token(tok, _AID, _cu("u1"), client_id="cli-OUTRO")
    assert ei.value.status_code == 403


def test_token_binding_caso_provas():
    tok = vlf.emitir_token(_AID, user_id="u1", caso_id="caso-1")
    assert vlf.validar_token(tok, _AID, _cu("u1"), caso_id="caso-1")
    with pytest.raises(HTTPException) as ei:
        vlf.validar_token(tok, _AID, _cu("u1"), caso_id="caso-OUTRO")
    assert ei.value.status_code == 403


def test_emitir_token_valida_uuid():
    with pytest.raises(HTTPException):
        vlf.emitir_token("nao-e-uuid", user_id="u1")
