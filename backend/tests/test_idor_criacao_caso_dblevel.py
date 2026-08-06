"""IDOR CRÍTICO da criação de caso — row-level, com Postgres real.

`POST /api/cases/` validava o `client_id` do corpo apenas quanto à EXISTÊNCIA.
Como `advogado_responsavel_id` cai em `cu.id` quando omitido, criar um caso com
o UUID de um cliente de OUTRA carteira fabricava exatamente o vínculo que faz
`core/client_ownership.pode_ver_cliente` liberar aquele cliente — de forma
permanente. Não é escrita indevida: é ESCALONAMENTO DE PRIVILÉGIO.

Os testes de handler (test_idor_criacao_carteira.py) cobrem o contrato com o
gate monkeypatchado. Aqui a prova é com dados REAIS: clientes e casos no banco,
`pode_ver_cliente` de verdade. Além de travar a correção, o arquivo DOCUMENTA o
vetor — `test_vinculo_fabricado_concederia_acesso` demonstra, sem passar pelo
handler, por que a ausência do gate era grave.

Postgres OBRIGATÓRIO (padrão dos demais *_dblevel.py). Sem RUN_DB_TESTS=1, pula.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


# ── Helpers (SQL cru, como nos demais *_dblevel.py) ──────────────────────────

async def _criar_user(db, role: str = "advogado") -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'IDOR Criacao', :role, true)"),
        {"id": uid, "email": f"idorc-{uid[:8]}@teste.local", "role": role},
    )
    return uid


async def _criar_cliente(db, nome: str, responsavel_id: str | None = None) -> str:
    cid = str(uuid4())
    await db.execute(
        text("INSERT INTO clients (id, tipo, nome, email, status, responsavel_id) "
             "VALUES (:id, 'PF', :nome, :email, 'ativo', :resp)"),
        {"id": cid, "nome": nome, "email": f"{cid[:8]}@teste.local",
         "resp": responsavel_id},
    )
    return cid


async def _carregar_user(db, uid: str):
    from app.models.user import User
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def _limpar(db, *, case_ids=(), user_ids=(), client_ids=()):
    """Ordem importa: casos → clientes → usuários.

    Diferente dos demais *_dblevel.py, aqui os clientes têm `responsavel_id`
    preenchido (é o que dá titularidade de carteira e faz o teste ter sentido),
    e essa coluna referencia `users` — apagar o usuário antes viola a FK.
    """
    await db.rollback()  # a transação pode vir suja do 404/erro sob teste
    for cid in case_ids:
        # `criar` grava satélites junto com o caso (movimento de abertura,
        # áreas): removê-los antes evita violação de FK na limpeza.
        for tabela in ("case_movimentos", "caso_areas"):
            await db.execute(
                text(f"DELETE FROM {tabela} WHERE case_id = :id"), {"id": cid}
            )
        await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": cid})
    for cid in client_ids:
        await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": cid})
    for uid in user_ids:
        # A criação de caso deixa trilha de auditoria referenciando o autor.
        await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
        await db.execute(
            text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": uid}
        )
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    await db.commit()


async def _casos_do_cliente(db, client_id: str) -> list[str]:
    rows = (await db.execute(
        text("SELECT id FROM cases WHERE client_id = :cid AND deleted_at IS NULL"),
        {"cid": client_id},
    )).all()
    return [r[0] for r in rows]


class _BgFake:
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *a, **k):
        self.tasks.append((fn, a, k))


def _payload(client_id: str, titulo: str):
    from app.schemas.case import CaseCreate
    return CaseCreate(
        titulo=titulo, client_id=client_id, area="civil",
        proxima_acao="Analisar documentos iniciais",
    )


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


# ── O bloqueio ───────────────────────────────────────────────────────────────

async def test_advogado_nao_cria_caso_para_cliente_de_outra_carteira():
    """O núcleo da correção: 404 uniforme e NENHUM caso gravado."""
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import criar

    tok = uuid4().hex[:6]
    async with AsyncSessionLocal() as db:
        adv_a = await _criar_user(db, "advogado")   # atacante
        adv_b = await _criar_user(db, "advogado")   # dono da carteira
        cli_b = await _criar_cliente(db, f"Cliente de B {tok}", responsavel_id=adv_b)
        await db.commit()
        try:
            with pytest.raises(HTTPException) as exc:
                await criar(
                    payload=_payload(cli_b, f"Caso forjado {tok}"),
                    background=_BgFake(), db=db,
                    cu=await _carregar_user(db, adv_a),
                )
            # 404 (não 403): não confirma que o UUID existe em outra carteira.
            assert exc.value.status_code == 404
            await db.rollback()
            # E o mais importante: nada foi gravado.
            assert await _casos_do_cliente(db, cli_b) == []
        finally:
            await _limpar(db, user_ids=[adv_a, adv_b], client_ids=[cli_b])


async def test_dono_da_carteira_cria_normalmente():
    """A correção não pode quebrar o caminho legítimo."""
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import criar

    tok = uuid4().hex[:6]
    async with AsyncSessionLocal() as db:
        adv_b = await _criar_user(db, "advogado")
        cli_b = await _criar_cliente(db, f"Cliente proprio {tok}", responsavel_id=adv_b)
        await db.commit()
        casos = []
        try:
            out = await criar(
                payload=_payload(cli_b, f"Caso legitimo {tok}"),
                background=_BgFake(), db=db,
                cu=await _carregar_user(db, adv_b),
            )
            casos = await _casos_do_cliente(db, cli_b)
            assert len(casos) == 1
            assert getattr(out, "titulo", None) == f"Caso legitimo {tok}"
        finally:
            await _limpar(db, case_ids=casos, user_ids=[adv_b], client_ids=[cli_b])


async def test_gestao_cria_para_qualquer_carteira():
    """Sócio tem visão total por desenho — o gate não pode barrá-lo."""
    from app.core.database import AsyncSessionLocal
    from app.routers.cases import criar

    tok = uuid4().hex[:6]
    async with AsyncSessionLocal() as db:
        socio = await _criar_user(db, "socio")
        adv_b = await _criar_user(db, "advogado")
        cli_b = await _criar_cliente(db, f"Cliente de B {tok}", responsavel_id=adv_b)
        await db.commit()
        casos = []
        try:
            await criar(
                payload=_payload(cli_b, f"Caso da gestao {tok}"),
                background=_BgFake(), db=db,
                cu=await _carregar_user(db, socio),
            )
            casos = await _casos_do_cliente(db, cli_b)
            assert len(casos) == 1
        finally:
            await _limpar(db, case_ids=casos, user_ids=[socio, adv_b],
                          client_ids=[cli_b])


# ── O vetor que a correção fecha (documentação executável) ───────────────────

async def test_vinculo_fabricado_concederia_acesso_permanente():
    """Demonstra POR QUE a ausência do gate era crítica, sem passar pelo handler.

    `pode_ver_cliente` concede acesso a quem é responsável por um caso do
    cliente. Logo, bastava o caso existir — e era o próprio POST /cases que o
    criava. Antes: False → (caso forjado) → True, para sempre."""
    from app.core.client_ownership import pode_ver_cliente
    from app.core.database import AsyncSessionLocal
    from app.models.client import Client

    tok = uuid4().hex[:6]
    async with AsyncSessionLocal() as db:
        adv_a = await _criar_user(db, "advogado")
        adv_b = await _criar_user(db, "advogado")
        cli_b = await _criar_cliente(db, f"Cliente de B {tok}", responsavel_id=adv_b)
        await db.commit()
        caso_forjado = str(uuid4())
        try:
            user_a = await _carregar_user(db, adv_a)
            cliente = (await db.execute(
                select(Client).where(Client.id == cli_b)
            )).scalar_one()

            # Antes do vínculo: A não enxerga o cliente de B.
            assert await pode_ver_cliente(db, user_a, cliente) is False

            # Simula o que o POST /cases fazia sem gate: caso do cliente de B
            # com A como responsável.
            await db.execute(
                text("INSERT INTO cases (id, titulo, area, status, client_id, "
                     "advogado_responsavel_id) VALUES "
                     "(:id, :t, 'civil', 'em_instrucao', :cid, :resp)"),
                {"id": caso_forjado, "t": f"Forjado {tok}", "cid": cli_b,
                 "resp": adv_a},
            )
            await db.commit()

            # Depois: acesso concedido — dossiê, CPF/CNPJ, procurações, data room.
            assert await pode_ver_cliente(db, user_a, cliente) is True
        finally:
            await _limpar(db, case_ids=[caso_forjado],
                          user_ids=[adv_a, adv_b], client_ids=[cli_b])
