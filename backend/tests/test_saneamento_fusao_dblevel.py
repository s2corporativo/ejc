"""Fusão real de casos duplicados (app/services/saneamento/fusao.py) contra
Postgres real — sem isso `aplicar_duplicata` só marcava `aplicado=true` sem
fundir nada (achado de revisão de código, Codex, e Issue #1319, item 2).

Contrato coberto:
  - Tabela 1:N normal (documents): toda linha do absorvido passa a apontar
    pro principal.
  - Tabela com UNIQUE(case_id) real (fichas_triagem): se o principal já tem
    linha, a do absorvido é descartada (nunca viola a constraint).
  - `processes` com o mesmo numero_cnj sob o mesmo case_id após a fusão:
    colapsa em um só (archived_at nos demais, nunca DELETE).
  - Caso absorvido vira status=arquivado + archived_at/archive_reason
    (mesmos campos de POST /cases/{id}/arquivar) — nunca DROP/DELETE.
  - Idempotente: rodar de novo sobre um absorvido já arquivado não faz nada.

Sem RUN_DB_TESTS=1, pula (mesmo padrão dos demais *_dblevel.py).
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text

_pg = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)

NUM_CNJ_OFICIAL = "00008323520184013202"


async def _criar_cliente(db) -> str:
    cid = str(uuid4())
    await db.execute(
        text("INSERT INTO clients (id, tipo, nome, email, status) "
             "VALUES (:id, 'PF', 'Cliente Fusão Saneamento Teste', :email, 'ativo')"),
        {"id": cid, "email": f"{cid[:8]}@teste.local"},
    )
    return cid


async def _criar_caso(db, client_id: str) -> str:
    case_id = str(uuid4())
    await db.execute(
        text("INSERT INTO cases (id, titulo, area, status, client_id) "
             "VALUES (:id, 'Caso fusão teste', 'civil', 'em_instrucao', :cid)"),
        {"id": case_id, "cid": client_id},
    )
    return case_id


async def _criar_processo(db, case_id: str, numero_cnj: str) -> None:
    await db.execute(
        text("INSERT INTO processes (case_id, numero_cnj) VALUES (:cid, :cnj)"),
        {"cid": case_id, "cnj": numero_cnj},
    )


async def _criar_documento(db, case_id: str, titulo: str) -> str:
    doc_id = str(uuid4())
    await db.execute(
        text("INSERT INTO documents (id, titulo, filename, filepath, case_id) "
             "VALUES (:id, :t, 'arquivo.pdf', '/tmp/x.pdf', :cid)"),
        {"id": doc_id, "t": titulo, "cid": case_id},
    )
    return doc_id


async def _criar_ficha_triagem(db, case_id: str) -> str:
    ficha_id = str(uuid4())
    await db.execute(
        text("INSERT INTO fichas_triagem (id, case_id) VALUES (:id, :cid)"),
        {"id": ficha_id, "cid": case_id},
    )
    return ficha_id


async def _limpar(db, *, case_ids=()):
    for cid in case_ids:
        await db.execute(text("DELETE FROM documents WHERE case_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM fichas_triagem WHERE case_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM case_movimentos WHERE case_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM processes WHERE case_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": cid})
    await db.commit()


@_pg
async def test_fusao_reatribui_tabela_1n_normal():
    from app.core.database import AsyncSessionLocal
    from app.services.saneamento.fusao import fundir_casos

    async with AsyncSessionLocal() as db:
        cli = await _criar_cliente(db)
        principal = await _criar_caso(db, cli)
        absorvido = await _criar_caso(db, cli)
        doc_id = await _criar_documento(db, absorvido, "Petição inicial")
        await db.commit()

    try:
        async with AsyncSessionLocal() as db:
            relatorio = await fundir_casos(
                db, principal_id=principal, absorvido_id=absorvido,
                numero_cnj_gatilho=NUM_CNJ_OFICIAL, ator_id="tester",
            )
            await db.commit()
        assert relatorio.reatribuidas.get("documents.case_id") == 1

        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                text("SELECT case_id FROM documents WHERE id = :id"), {"id": doc_id},
            )).mappings().one()
        assert row["case_id"] == principal
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db, case_ids=[principal, absorvido])


@_pg
async def test_fusao_descarta_linha_do_absorvido_em_tabela_um_por_caso():
    """fichas_triagem tem UNIQUE(case_id) real — reatribuir cegamente
    violaria a constraint. Quando o principal já tem ficha, a do absorvido
    é descartada (nunca mesclada campo a campo)."""
    from app.core.database import AsyncSessionLocal
    from app.services.saneamento.fusao import fundir_casos

    async with AsyncSessionLocal() as db:
        cli = await _criar_cliente(db)
        principal = await _criar_caso(db, cli)
        absorvido = await _criar_caso(db, cli)
        await _criar_ficha_triagem(db, principal)
        await _criar_ficha_triagem(db, absorvido)
        await db.commit()

    try:
        async with AsyncSessionLocal() as db:
            relatorio = await fundir_casos(
                db, principal_id=principal, absorvido_id=absorvido,
                numero_cnj_gatilho=NUM_CNJ_OFICIAL, ator_id="tester",
            )
            await db.commit()  # não pode levantar IntegrityError
        assert relatorio.descartadas.get("fichas_triagem.case_id") == 1

        async with AsyncSessionLocal() as db:
            total_principal = (await db.execute(
                text("SELECT count(*) FROM fichas_triagem WHERE case_id = :id"), {"id": principal},
            )).scalar_one()
            total_absorvido = (await db.execute(
                text("SELECT count(*) FROM fichas_triagem WHERE case_id = :id"), {"id": absorvido},
            )).scalar_one()
        assert total_principal == 1
        assert total_absorvido == 0
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db, case_ids=[principal, absorvido])


@_pg
async def test_fusao_reatribui_quando_so_absorvido_tem_linha_um_por_caso():
    from app.core.database import AsyncSessionLocal
    from app.services.saneamento.fusao import fundir_casos

    async with AsyncSessionLocal() as db:
        cli = await _criar_cliente(db)
        principal = await _criar_caso(db, cli)
        absorvido = await _criar_caso(db, cli)
        ficha_id = await _criar_ficha_triagem(db, absorvido)
        await db.commit()

    try:
        async with AsyncSessionLocal() as db:
            relatorio = await fundir_casos(
                db, principal_id=principal, absorvido_id=absorvido,
                numero_cnj_gatilho=NUM_CNJ_OFICIAL, ator_id="tester",
            )
            await db.commit()
        assert relatorio.reatribuidas.get("fichas_triagem.case_id") == 1

        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                text("SELECT case_id FROM fichas_triagem WHERE id = :id"), {"id": ficha_id},
            )).mappings().one()
        assert row["case_id"] == principal
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db, case_ids=[principal, absorvido])


@_pg
async def test_fusao_colapsa_processos_com_mesmo_numero_cnj():
    """Depois de reatribuir processes, o principal fica com DOIS Process
    com o mesmo numero_cnj (o próprio motivo da fusão) — deve colapsar em
    um só, arquivando o outro (nunca DELETE)."""
    from app.core.database import AsyncSessionLocal
    from app.services.saneamento.fusao import fundir_casos

    async with AsyncSessionLocal() as db:
        cli = await _criar_cliente(db)
        principal = await _criar_caso(db, cli)
        absorvido = await _criar_caso(db, cli)
        await _criar_processo(db, principal, NUM_CNJ_OFICIAL)
        await _criar_processo(db, absorvido, NUM_CNJ_OFICIAL)
        await db.commit()

    try:
        async with AsyncSessionLocal() as db:
            relatorio = await fundir_casos(
                db, principal_id=principal, absorvido_id=absorvido,
                numero_cnj_gatilho=NUM_CNJ_OFICIAL, ator_id="tester",
            )
            await db.commit()
        assert relatorio.processos_colapsados == 1

        async with AsyncSessionLocal() as db:
            ativos = (await db.execute(
                text("SELECT count(*) FROM processes WHERE case_id = :id AND archived_at IS NULL"),
                {"id": principal},
            )).scalar_one()
            arquivados = (await db.execute(
                text("SELECT count(*) FROM processes WHERE case_id = :id AND archived_at IS NOT NULL"),
                {"id": principal},
            )).scalar_one()
        assert ativos == 1
        assert arquivados == 1
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db, case_ids=[principal, absorvido])


@_pg
async def test_fusao_arquiva_caso_absorvido_sem_deletar():
    from app.core.database import AsyncSessionLocal
    from app.services.saneamento.fusao import fundir_casos

    async with AsyncSessionLocal() as db:
        cli = await _criar_cliente(db)
        principal = await _criar_caso(db, cli)
        absorvido = await _criar_caso(db, cli)
        await db.commit()

    try:
        async with AsyncSessionLocal() as db:
            await fundir_casos(
                db, principal_id=principal, absorvido_id=absorvido,
                numero_cnj_gatilho=NUM_CNJ_OFICIAL, ator_id="tester-fusor",
            )
            await db.commit()

        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                text("SELECT status, archived_at, archive_reason, deleted_at FROM cases WHERE id = :id"),
                {"id": absorvido},
            )).mappings().one()
        assert row["status"] == "arquivado"
        assert row["archived_at"] is not None
        assert principal in row["archive_reason"]
        assert row["deleted_at"] is None  # arquivado, não excluído — nunca DROP/DELETE

        async with AsyncSessionLocal() as db:
            movimento = (await db.execute(
                text("SELECT tipo FROM case_movimentos WHERE case_id = :id AND tipo = 'saneamento'"),
                {"id": principal},
            )).mappings().one_or_none()
        assert movimento is not None
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db, case_ids=[principal, absorvido])


@_pg
async def test_fusao_e_idempotente_sobre_absorvido_ja_arquivado():
    from app.core.database import AsyncSessionLocal
    from app.services.saneamento.fusao import fundir_casos

    async with AsyncSessionLocal() as db:
        cli = await _criar_cliente(db)
        principal = await _criar_caso(db, cli)
        absorvido = await _criar_caso(db, cli)
        await db.commit()

    try:
        async with AsyncSessionLocal() as db:
            await fundir_casos(
                db, principal_id=principal, absorvido_id=absorvido,
                numero_cnj_gatilho=NUM_CNJ_OFICIAL, ator_id="tester",
            )
            await db.commit()

        async with AsyncSessionLocal() as db:
            relatorio = await fundir_casos(
                db, principal_id=principal, absorvido_id=absorvido,
                numero_cnj_gatilho=NUM_CNJ_OFICIAL, ator_id="tester",
            )
            await db.commit()
        assert relatorio.absorvido_ja_arquivado is True
        assert relatorio.reatribuidas == {}
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db, case_ids=[principal, absorvido])
