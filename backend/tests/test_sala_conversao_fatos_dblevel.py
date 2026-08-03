"""Conversão Sala Jurídica → Caso: os fatos da sessão não podem sumir no ato.

`ConverterRequest.descricao` é OPCIONAL (schemas/legal_chat.py:107). Sem
fallback, converter sem preenchê-la criava um `Case` com `descricao_fatos`
NULO — enquanto a sessão que originou a conversão continha o relato na área de
trabalho. O prejuízo não é cosmético: `motor_peca_service._texto_base` e
`case_intel` leem `descricao_fatos` como fonte dos fatos, então o caso nascia
sem matéria-prima para gerar peça e para a triagem automática.

Nível de banco de propósito: o defeito é o valor PERSISTIDO na coluna, e um
fake de sessão não prova persistência. Padrão dos demais *_dblevel.py —
handler/serviço chamado direto com AsyncSessionLocal, SQL cru para a massa,
RUN_DB_TESTS obrigatório.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import select, text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)

FATOS_DA_SESSAO = "Cliente teve o nome negativado sem notificação prévia."


async def _criar_advogado(db) -> str:
    uid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, full_name, role, "
            "is_active) VALUES (:id, :email, 'x', 'Adv Teste', 'advogado', true)"
        ),
        {"id": uid, "email": f"adv-{uid[:8]}@conversao.local"},
    )
    return uid


async def _criar_sessao(db, criador_id: str, *, workspace: str | None) -> str:
    sid = str(uuid4())
    await db.execute(
        text(
            "INSERT INTO legal_chat_sessions "
            "(id, titulo, status, favorita, workspace_texto, workspace_versao, "
            " created_by, custo_ia_total) "
            "VALUES (:id, :tit, 'em_analise', false, :ws, 1, :cb, 0)"
        ),
        {"id": sid, "tit": f"Sessão {sid[:6]}", "ws": workspace, "cb": criador_id},
    )
    return sid


async def _limpar(db, *, session_ids=(), user_ids=(), case_ids=(), client_ids=()):
    for sid in session_ids:
        await db.execute(
            text("UPDATE legal_chat_sessions SET convertido_case_id = NULL WHERE id = :id"),
            {"id": sid},
        )
        await db.execute(text("DELETE FROM legal_chat_messages WHERE session_id = :id"), {"id": sid})
        await db.execute(text("DELETE FROM legal_chat_sessions WHERE id = :id"), {"id": sid})
    for cid in case_ids:
        # A conversão não cria só o Case: grava movimento na timeline e o
        # snapshot de inteligência preliminar (paridade Raio-X). Apagar só
        # `cases` esbarra na FK dos dois.
        await db.execute(text("DELETE FROM case_movimentos WHERE case_id = :id"), {"id": cid})
        await db.execute(
            text("DELETE FROM case_intelligence_snapshots WHERE case_id = :id"), {"id": cid}
        )
        await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": cid})
    for cid in client_ids:
        await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": cid})
    for uid in user_ids:
        await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": uid})
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine

    await engine.dispose()


async def _converter(db, sessao_id: str, advogado_id: str, *, descricao: str | None):
    from app.models.legal_chat import LegalChatSession
    from app.models.user import User
    from app.schemas.legal_chat import ConverterRequest
    from app.services.legal_chat_service import converter_em_caso

    sessao = (
        await db.execute(select(LegalChatSession).where(LegalChatSession.id == sessao_id))
    ).scalar_one()
    user = (await db.execute(select(User).where(User.id == advogado_id))).scalar_one()
    payload = ConverterRequest(
        novo_cliente_nome=f"Cliente {sessao_id[:6]}",
        area="civil",
        titulo_caso=f"Caso {sessao_id[:6]}",
        descricao=descricao,
        advogado_responsavel_id=advogado_id,
        confirmo_conflito_verificado=True,
        confirmo_dados_revisados=True,
        transferir_anexos=False,
    )
    return await converter_em_caso(db, sessao, payload, user)


async def _fatos_do_caso(db, case_id: str) -> str | None:
    from app.models.case import Case

    caso = (await db.execute(select(Case).where(Case.id == case_id))).scalar_one()
    return caso.descricao_fatos


async def test_conversao_sem_descricao_herda_os_fatos_da_sessao():
    """Regressão: `descricao` omitida NÃO pode zerar os fatos do caso quando a
    sessão os contém. Antes da correção, `descricao_fatos` ficava NULO aqui."""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        adv = await _criar_advogado(db)
        sid = await _criar_sessao(db, adv, workspace=FATOS_DA_SESSAO)
        await db.commit()
        resultado = None
        try:
            resultado = await _converter(db, sid, adv, descricao=None)
            assert await _fatos_do_caso(db, resultado["case_id"]) == FATOS_DA_SESSAO
        finally:
            await _limpar(
                db,
                session_ids=[sid],
                case_ids=[resultado["case_id"]] if resultado else [],
                client_ids=[resultado["client_id"]] if resultado and resultado.get("client_id") else [],
                user_ids=[adv],
            )


async def test_descricao_informada_prevalece_sobre_a_area_de_trabalho():
    """O fallback é fallback: quem preencheu o campo mandou nele. Sem este
    assert, "herdar sempre da sessão" passaria igual e sobrescreveria o texto
    revisado pelo advogado na hora de converter."""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        adv = await _criar_advogado(db)
        sid = await _criar_sessao(db, adv, workspace=FATOS_DA_SESSAO)
        await db.commit()
        revisado = "Relato revisado pelo advogado no ato da conversão."
        resultado = None
        try:
            resultado = await _converter(db, sid, adv, descricao=revisado)
            assert await _fatos_do_caso(db, resultado["case_id"]) == revisado
        finally:
            await _limpar(
                db,
                session_ids=[sid],
                case_ids=[resultado["case_id"]] if resultado else [],
                client_ids=[resultado["client_id"]] if resultado and resultado.get("client_id") else [],
                user_ids=[adv],
            )


async def test_sessao_sem_fatos_continua_gerando_caso_sem_forjar_texto():
    """Área de trabalho vazia não vira string vazia nem placeholder: o campo
    fica NULO, honestamente, e a conversão não quebra."""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        adv = await _criar_advogado(db)
        sid = await _criar_sessao(db, adv, workspace="   ")
        await db.commit()
        resultado = None
        try:
            resultado = await _converter(db, sid, adv, descricao=None)
            assert await _fatos_do_caso(db, resultado["case_id"]) is None
        finally:
            await _limpar(
                db,
                session_ids=[sid],
                case_ids=[resultado["case_id"]] if resultado else [],
                client_ids=[resultado["client_id"]] if resultado and resultado.get("client_id") else [],
                user_ids=[adv],
            )
