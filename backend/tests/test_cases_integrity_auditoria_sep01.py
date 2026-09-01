"""Regressões da auditoria do módulo Casos — 01/09/2026.

Testes unitários sem banco real para as novas regras de integridade. O objetivo
é falhar antes de qualquer acesso externo e travar os contratos de domínio que
motivaram a correção.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.case import CaseCreate, CaseUpdate
from app.services import case_integrity_service as integrity


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _DB:
    def __init__(self, value=None):
        self.value = value
        self.execute_calls = 0

    async def execute(self, _stmt, *_args, **_kwargs):
        self.execute_calls += 1
        return _Result(self.value)


def _user(user_id: str, role: str):
    return SimpleNamespace(id=user_id, role=role)


async def test_intake_sem_advogado_nao_vira_responsavel_automaticamente():
    db = _DB()
    secretaria = _user("sec-1", "secretaria")

    with pytest.raises(HTTPException) as exc:
        await integrity.resolver_responsavel_juridico(db, secretaria, None)

    assert exc.value.status_code == 422
    assert "advogado responsável" in str(exc.value.detail).lower()
    assert db.execute_calls == 0


async def test_estagiario_pode_indicar_advogado_mas_nao_assumir_o_caso():
    advogado = _user("adv-1", "advogado")
    db = _DB(advogado)
    estagiario = _user("est-1", "estagiario")

    resolved = await integrity.resolver_responsavel_juridico(
        db, estagiario, advogado.id
    )

    assert resolved == "adv-1"
    assert db.execute_calls == 1


async def test_financeiro_nao_pode_ser_responsavel_juridico():
    financeiro = _user("fin-1", "financeiro")
    db = _DB(financeiro)
    socio = _user("soc-1", "socio")

    with pytest.raises(HTTPException) as exc:
        await integrity.resolver_responsavel_juridico(db, socio, financeiro.id)

    assert exc.value.status_code == 422
    assert "papel jurídico" in str(exc.value.detail).lower()


async def test_limpando_numero_atualiza_processo_principal(monkeypatch):
    capturado = {}

    async def _principal(case_id, db):
        assert case_id == "case-1"
        return {"id": "proc-1"}

    async def _atualizar(process_id, payload, db):
        assert process_id == "proc-1"
        capturado.update(payload.model_dump(exclude_unset=True))
        return {"id": process_id, **capturado}

    monkeypatch.setattr(integrity, "processo_principal", _principal)
    monkeypatch.setattr(integrity, "atualizar_processo", _atualizar)

    await integrity.sincronizar_processo_principal_do_caso(
        _DB(), case_id="case-1", numero_processo=None
    )

    assert "numero_cnj" in capturado
    assert capturado["numero_cnj"] is None


async def test_sem_processo_nao_fabrica_registro_vazio(monkeypatch):
    criado = False

    async def _principal(case_id, db):
        return None

    async def _criar(*args, **kwargs):
        nonlocal criado
        criado = True
        return {}

    monkeypatch.setattr(integrity, "processo_principal", _principal)
    monkeypatch.setattr(integrity, "criar_processo", _criar)

    result = await integrity.sincronizar_processo_principal_do_caso(
        _DB(), case_id="case-1", numero_processo=None
    )

    assert result is None
    assert criado is False


def _case_payload(**overrides):
    base = {
        "titulo": "Caso de teste",
        "area": "civil",
        "client_id": "00000000-0000-0000-0000-000000000001",
        "proxima_acao": "Revisar documentos",
    }
    base.update(overrides)
    return base


def test_case_type_invalido_falha_no_schema():
    with pytest.raises(ValidationError):
        CaseCreate(**_case_payload(case_type="qualquer-coisa"))


def test_case_update_case_type_invalido_falha_no_schema():
    with pytest.raises(ValidationError):
        CaseUpdate(case_type="qualquer-coisa")


def test_titulo_maior_que_coluna_falha_antes_do_banco():
    with pytest.raises(ValidationError):
        CaseCreate(**_case_payload(titulo="x" * 256))


def test_campos_varchar_maiores_que_model_falham_no_schema():
    with pytest.raises(ValidationError):
        CaseUpdate(tribunal="T" * 21)
    with pytest.raises(ValidationError):
        CaseUpdate(comarca="C" * 101)
    with pytest.raises(ValidationError):
        CaseUpdate(vara="V" * 101)
