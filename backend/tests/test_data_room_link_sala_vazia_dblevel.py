"""FIX-001 — Data Room: sala SEM documentos nunca gera link externo.

Cobre a correção de 13/08/2026 (teste de usabilidade):
- Sala vazia: POST /data-rooms/{id}/links => 422 com mensagem orientativa
  (antes, o frontend recebia resposta inesperada e quebrava a aba inteira
  "Compartilhamento seguro").
- Sala com documento + papel autorizado: 201 com token e URL.
- Papel não autorizado (cliente_externo): 403 — permanece negado.

Postgres é OBRIGATÓRIO (mesmo padrão dos *_dblevel.py: chama o handler
direto com AsyncSessionLocal e SQL cru). Sem RUN_DB_TESTS=1, pula.
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)

from fastapi import HTTPException  # noqa: E402

from app.routers import data_room as dr  # noqa: E402


async def _criar_user(db, role: str = "advogado") -> str:
    uid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, "
            "is_active, must_change_password) "
            "VALUES (:id, :email, 'x', 'DataRoom FIX-001', :role, true, false)"
        ),
        {"id": uid, "email": f"drfix-{uid[:8]}@teste.local", "role": role},
    )
    await db.commit()
    return uid


async def _criar_sala(db, room_id: str, uid: str) -> None:
    await db.execute(
        text(
            "INSERT INTO data_rooms (id, nome, created_by) "
            "VALUES (:id, :nome, :uid)"
        ),
        {"id": room_id, "nome": "Sala FIX-001", "uid": uid},
    )
    await db.commit()


async def _adicionar_documento_e_linkar(db, room_id: str, uid: str) -> None:
    doc_id = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO documents (id, titulo, filename, filepath, versao, "
            "confidencialidade) "
            "VALUES (:id, 'Doc FIX-001', 'doc.pdf', '/tmp/doc.pdf', 1, "
            "'confidencial')"
        ),
        {"id": doc_id},
    )
    await db.execute(
        text(
            "INSERT INTO data_room_arquivos (id, data_room_id, document_id, "
            "adicionado_por, publicado_externamente) "
            "VALUES (:id, :room, :doc, :uid, false)"
        ),
        {"id": str(uuid4()), "room": room_id, "doc": doc_id, "uid": uid},
    )
    await db.commit()


def _req(expira_horas: int = 72):
    req = SimpleNamespace()
    req.descricao = None
    req.expira_horas = expira_horas
    req.max_acessos = None
    return req


@pytest.fixture(autouse=True)
async def _limpar_dados_de_teste():
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM data_room_links"))
        await db.execute(text("DELETE FROM data_room_arquivos"))
        await db.execute(text("DELETE FROM data_rooms"))
        await db.execute(
            text("DELETE FROM users WHERE email LIKE 'drfix-%@teste.local'")
        )
        await db.commit()
    yield


async def test_gerar_link_rejeita_sala_sem_documentos():
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db, "advogado")
        sala = str(uuid4())
        await _criar_sala(db, sala, uid)

        cu = SimpleNamespace(id=uid, role=SimpleNamespace(value="advogado"))
        with pytest.raises(HTTPException) as raised:
            await dr.gerar_link(sala, _req(), db=db, cu=cu)
        assert raised.value.status_code == 422
        assert "sem documentos" in str(raised.value.detail)


async def test_gerar_link_aceita_sala_com_documento():
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db, "advogado")
        sala = str(uuid4())
        await _criar_sala(db, sala, uid)
        await _adicionar_documento_e_linkar(db, sala, uid)

        cu = SimpleNamespace(id=uid, role=SimpleNamespace(value="advogado"))
        out = await dr.gerar_link(sala, _req(), db=db, cu=cu)
        assert "url_acesso" in out
        assert out.get("token")  # retornado apenas no 1º acesso (hash depois)


async def test_gerar_link_recusa_papel_nao_autorizado():
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        uid = await _criar_user(db, "cliente_externo")
        sala = str(uuid4())
        await _criar_sala(db, sala, uid)
        await _adicionar_documento_e_linkar(db, sala, uid)

        cu = SimpleNamespace(
            id=uid, role=SimpleNamespace(value="cliente_externo")
        )
        with pytest.raises(HTTPException) as raised:
            await dr.gerar_link(sala, _req(), db=db, cu=cu)
        assert raised.value.status_code == 403
