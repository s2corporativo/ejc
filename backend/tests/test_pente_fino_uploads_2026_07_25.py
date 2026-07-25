"""Pente fino 2026-07-25 — guardas de upload e gate de carteira.

Cobre sem Postgres (padrão test_avatar_upload):
- rag.ingerir_pdf: teto de tamanho no app + magic bytes antes do OCR;
- bank_analysis.upload: client_id do form passa pelo gate de carteira
  (contrato por inspeção de fonte, mesmo padrão do test_sala_frontend_contract)
  e o gate devolve 404 uniforme para cliente inexistente/invisível.
"""
from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException

from app.routers.rag import _validar_pdf_upload


def test_pdf_acima_do_teto_rejeitado_413():
    raw = b"%PDF-" + b"x" * (1 * 1024 * 1024 + 1)
    with pytest.raises(HTTPException) as exc:
        _validar_pdf_upload(raw, max_mb=1)
    assert exc.value.status_code == 413


def test_conteudo_sem_assinatura_pdf_rejeitado_422():
    with pytest.raises(HTTPException) as exc:
        _validar_pdf_upload(b"MZ\x90\x00 executavel disfarcado", max_mb=50)
    assert exc.value.status_code == 422


def test_pdf_valido_dentro_do_teto_passa():
    assert _validar_pdf_upload(b"%PDF-1.7 conteudo", max_mb=50) is None


def test_upload_bancario_exige_gate_de_carteira_no_client_id():
    # Contrato: o handler deve invocar obter_cliente_autorizado quando o form
    # traz client_id. Regressão do achado MÉDIO do pente fino (vínculo de dado
    # financeiro a cliente fora da carteira).
    from app.routers.bank_analysis import upload

    fonte = inspect.getsource(upload)
    assert "obter_cliente_autorizado" in fonte
    assert fonte.index("obter_cliente_autorizado") < fonte.index("BankAnalysis(")


async def test_gate_devolve_404_uniforme_para_cliente_inexistente():
    from app.core.client_ownership import obter_cliente_autorizado

    class _Res:
        def scalar_one_or_none(self):
            return None

    class _Db:
        async def execute(self, *_a, **_k):
            return _Res()

    class _User:
        id = "u1"
        role = "advogado"

    with pytest.raises(HTTPException) as exc:
        await obter_cliente_autorizado(_Db(), _User(), "uuid-de-outra-carteira")
    assert exc.value.status_code == 404
    assert exc.value.detail == "Cliente não encontrado"

    # client_id vazio também é 404 (nunca 422 que revele semântica interna).
    with pytest.raises(HTTPException) as exc2:
        await obter_cliente_autorizado(_Db(), _User(), None)
    assert exc2.value.status_code == 404
