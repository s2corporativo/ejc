from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services import case_integrity_service as integrity


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _DB:
    def __init__(self, *values):
        self.values = list(values)
        self.execute_calls = 0

    async def execute(self, _stmt, *_args, **_kwargs):
        self.execute_calls += 1
        value = self.values.pop(0) if self.values else None
        return _Result(value)


def _user(user_id: str, role: str, *, ativo=True):
    return SimpleNamespace(id=user_id, role=role, is_active=ativo)


async def test_intake_nao_assume_responsabilidade_juridica_por_fallback():
    db = _DB()
    with pytest.raises(HTTPException) as exc:
        await integrity.resolver_responsavel_juridico(db, _user("sec-1", "secretaria"), None)
    assert exc.value.status_code == 422
    assert db.execute_calls == 0


async def test_advogado_autenticado_pode_assumir_sem_query_redundante():
    db = _DB()
    resolved = await integrity.resolver_responsavel_juridico(
        db, _user("adv-1", "advogado"), None
    )
    assert resolved == "adv-1"
    assert db.execute_calls == 0


async def test_responsavel_explicito_precisa_ter_papel_juridico():
    db = _DB(_user("fin-1", "financeiro"))
    with pytest.raises(HTTPException) as exc:
        await integrity.resolver_responsavel_juridico(
            db, _user("soc-1", "socio"), "fin-1"
        )
    assert exc.value.status_code == 422


async def test_limpar_numero_sincroniza_processo_principal(monkeypatch):
    capturado = {}

    async def _principal(case_id, db):
        return {"id": "proc-1"}

    async def _atualizar(process_id, payload, db):
        capturado.update(payload.model_dump(exclude_unset=True))
        return {"id": process_id, **capturado}

    monkeypatch.setattr(integrity, "processo_principal", _principal)
    monkeypatch.setattr(integrity, "atualizar_processo", _atualizar)

    await integrity.sincronizar_processo_principal_do_caso(
        _DB(), case_id="case-1", numero_processo=None
    )
    assert capturado.get("numero_cnj") is None


async def test_sem_dado_material_nao_fabrica_processo_vazio(monkeypatch):
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
