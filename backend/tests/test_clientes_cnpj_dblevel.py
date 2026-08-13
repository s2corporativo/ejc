"""FIX-002 — Clientes PJ: CNPJ matematicamente válido DEVE ser aceito.

Regressão do teste de usabilidade de 13/08/2026: CNPJs válidos
(11.222.333/0001-81 e 10.433.218/1960-71) foram rejeitados com
"CPF inválido (dígito verificador)", mensagem confusa para quem cadastrava
uma pessoa jurídica.

Contrato coberto (POST /clients/ e PATCH /clients/:id):
  - PJ + CNPJ válido (com ou sem máscara) => 201/200.
  - PJ + CNPJ inválido => 422 com rótulo "CNPJ inválido..." (nunca "CPF").
  - PF + CPF válido => 201; PF + CPF inválido => 422 "CPF inválido...".
  - CNPJ 11 dígitos ou CPF 14 dígitos => rejeitado pelo lado certo.

Postgres é OBRIGATÓRIO (mesmo padrão dos *_dblevel.py). Sem
RUN_DB_TESTS=1, pula.
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)

from app.routers import clients as clients_router  # noqa: E402
from app.schemas.client import ClientResponse as _CR

def _to_dict(obj):
    return _CR.model_validate(obj).model_dump()


async def _criar_user(db, role: str = "advogado") -> str:
    uid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, "
            "is_active, must_change_password) "
            "VALUES (:id, :email, 'x', 'Clientes FIX-002', :role, true, false)"
        ),
        {"id": uid, "email": f"clf-{uid[:8]}@clientetesteejc.com", "role": role},
    )
    await db.commit()
    return uid


def _payload(**kw):
    from app.schemas.client import ClientCreate

    base = {
        "tipo": kw.get("tipo", "PJ"),
        "nome": kw.get("nome"),
        "razao_social": kw.get("razao_social"),
        "cpf": kw.get("cpf"),
        "cnpj": kw.get("cnpj"),
        "email": kw.get("email", f"{str(uuid4())[:8]}@clientetesteejc.com"),
        "telefone": kw.get("telefone"),
        "cidade": kw.get("cidade"),
        "estado": kw.get("estado"),
        "status": kw.get("status", "ativo"),
    }
    return ClientCreate(**{k: v for k, v in base.items() if v is not None})


@pytest.fixture(autouse=True)
async def _limpar_dados_de_teste():
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await db.execute(
            text("DELETE FROM clients WHERE nome LIKE 'Empresa Fictícia Teste%' "
                 "OR razao_social LIKE 'Empresa%'")
        )
        await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
        await db.execute(
            text("DELETE FROM audit_logs WHERE user_id IN "
                 "(SELECT id FROM users WHERE email LIKE 'clf-%@clientetesteejc.com')")
        )
        await db.execute(
            text("DELETE FROM users WHERE email LIKE 'clf-%@clientetesteejc.com'")
        )
        await db.commit()
    yield


async def test_pj_com_cnpj_valido_e_aceito():
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db)
        cu = SimpleNamespace(id=uid, role=SimpleNamespace(value="advogado"))

        req = _payload(razao_social="Empresa Fictícia Teste Ltda",
                       cnpj="11.222.333/0001-81")
        # chama o handler da rota (sem TestClient — padrão dblevel)
        resp = await clients_router.criar(req, db=db, cu=cu)
        assert resp is not None

        out = _to_dict(resp)
        assert out.get("tipo") == "PJ"
        assert (out.get("cnpj") or "").replace(".","").replace("/","").replace("-","") == "11222333000181"


async def test_pj_com_cnpj_invalido_e_rejeitado():
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db)
        cu = SimpleNamespace(id=uid, role=SimpleNamespace(value="advogado"))

        req = _payload(razao_social="Empresa Inválida Ltda",
                       cnpj="11.222.333/0001-00")  # DV errado
        with pytest.raises(HTTPException) as raised:
            await clients_router.criar(req, db=db, cu=cu)
        assert raised.value.status_code == 422
        assert "CNPJ" in str(raised.value.detail)


async def test_pf_com_cpf_invalido_retorna_rotulo_correto():
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db)
        cu = SimpleNamespace(id=uid, role=SimpleNamespace(value="advogado"))

        req = _payload(tipo="PF", nome="Pessoa Inválida", cpf="123.456.789-00")  # DV errado
        with pytest.raises(HTTPException) as raised:
            await clients_router.criar(req, db=db, cu=cu)
        assert raised.value.status_code == 422
        assert "CPF" in str(raised.value.detail)
        assert "CNPJ" not in str(raised.value.detail)
