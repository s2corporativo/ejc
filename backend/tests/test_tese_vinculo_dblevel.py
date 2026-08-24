"""Ponte Classe A (plano-mestre, Issue #1272, migration 149) — aprovar uma
ThesisCandidate originada do Banco de Teses materializa o vínculo em
`tese_caso_links`, o dado que faltava para `routers/conversao_caso.py`
(lê `TeseCasoLink`) e `services/legal_case_orchestrator.py` (lê
`ThesisCandidate.status`) pararem de responder `tese_aprovada` de forma
disjunta para o mesmo caso.

Postgres OBRIGATÓRIO (mesmo padrão dos demais *_dblevel.py). Sem
RUN_DB_TESTS=1, pula.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from app.models.matriz_teses import ThesisCandidate
from app.models.tese import Tese, TeseCasoLink, TeseStatus, TeseTipo

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


async def _criar_user(db, role: str = "advogado") -> str:
    uid = str(uuid4())
    await db.execute(
        text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
             "VALUES (:id, :email, 'x', 'Vinculo Teste', :role, true)"),
        {"id": uid, "email": f"vinc-{uid[:8]}@teste.local", "role": role},
    )
    return uid


async def _criar_cliente(db) -> str:
    cid = str(uuid4())
    await db.execute(
        text("INSERT INTO clients (id, tipo, nome, email, status) "
             "VALUES (:id, 'PF', 'Cliente Vinculo', :email, 'ativo')"),
        {"id": cid, "email": f"{cid[:8]}@teste.local"},
    )
    return cid


async def _criar_caso(db, client_id: str, resp_id: str) -> str:
    case_id = str(uuid4())
    await db.execute(
        text("INSERT INTO cases (id, titulo, area, status, client_id, "
             "advogado_responsavel_id, proxima_acao) VALUES "
             "(:id, 'Caso Vinculo', 'civil', 'em_instrucao', :cid, :resp, 'Providenciar X')"),
        {"id": case_id, "cid": client_id, "resp": resp_id},
    )
    return case_id


async def _limpar(db, *, case_ids=(), tese_ids=(), user_ids=(), client_ids=()):
    for cid in case_ids:
        await db.execute(text("DELETE FROM thesis_candidates WHERE case_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM tese_caso_links WHERE case_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": cid})
    for tid in tese_ids:
        await db.execute(text("DELETE FROM teses WHERE id = :id"), {"id": tid})
    for uid in user_ids:
        await db.execute(text("SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'"))
        await db.execute(text("DELETE FROM audit_logs WHERE user_id = :id"), {"id": uid})
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": uid})
    for cid in client_ids:
        await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": cid})
    await db.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


async def _carregar_user(db, uid: str):
    from app.models.user import User
    return (await db.execute(select(User).where(User.id == uid))).scalar_one()


async def test_aprovar_candidata_do_banco_cria_vinculo_e_atualiza_contadores():
    from app.core.database import AsyncSessionLocal
    from app.services.matriz_teses_service import aprovar_tese

    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db)
        cli = await _criar_cliente(db)
        caso = await _criar_caso(db, cli, adv)
        tese = Tese(id=str(uuid4()), titulo="Capitalização mensal abusiva",
                    descricao="Capitalização mensal sem pactuação expressa",
                    area_juridica="bancario", tipo=TeseTipo.escritorio,
                    status=TeseStatus.ativa)
        db.add(tese)
        await db.commit()

        cand = ThesisCandidate(
            id=str(uuid4()), case_id=caso, tese_banco_id=tese.id,
            tese="Capitalização mensal sem pactuação expressa",
            status="candidata",
        )
        db.add(cand)
        await db.commit()

        try:
            cu = await _carregar_user(db, adv)
            out = await aprovar_tese(db, cand.id, cu, decisao="aprovada",
                                     case_id=caso)
            assert out.status == "aprovada"

            links = (await db.execute(
                select(TeseCasoLink).where(TeseCasoLink.case_id == caso)
            )).scalars().all()
            assert len(links) == 1
            assert links[0].tese_id == tese.id
            assert links[0].resultado == "pendente"

            t = (await db.execute(
                select(Tese).where(Tese.id == tese.id)
            )).scalar_one()
            assert t.vezes_usada == 1
            # "pendente" não é vitória nem derrota -- contador não incrementa.
            assert t.vezes_venceu == 0
            assert t.vezes_perdeu == 0
        finally:
            await _limpar(db, case_ids=[caso], tese_ids=[tese.id],
                          user_ids=[adv], client_ids=[cli])


async def test_aprovar_candidata_do_banco_unifica_os_dois_leitores_disjuntos():
    """A regressão exata que motivou a Classe A: antes desta ponte,
    conversao_caso.py (TeseCasoLink) e legal_case_orchestrator.py
    (ThesisCandidate.status) respondiam 'tese aprovada' de forma diferente
    para o MESMO caso. Depois de aprovar uma candidata do Banco, os dois
    concordam."""
    from app.core.database import AsyncSessionLocal
    from app.services.matriz_teses_service import aprovar_tese

    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db)
        cli = await _criar_cliente(db)
        caso = await _criar_caso(db, cli, adv)
        tese = Tese(id=str(uuid4()), titulo="Tese X", descricao="Tese X",
                    area_juridica="civel", tipo=TeseTipo.escritorio,
                    status=TeseStatus.ativa)
        db.add(tese)
        await db.commit()
        cand = ThesisCandidate(id=str(uuid4()), case_id=caso,
                               tese_banco_id=tese.id, tese="Tese X",
                               status="candidata")
        db.add(cand)
        await db.commit()

        try:
            cu = await _carregar_user(db, adv)

            # ANTES da aprovação: os dois leitores concordam em "não aprovada".
            n_links_antes = (await db.execute(
                select(func.count()).select_from(TeseCasoLink)
                .where(TeseCasoLink.case_id == caso)
            )).scalar_one()
            assert n_links_antes == 0

            await aprovar_tese(db, cand.id, cu, decisao="aprovada", case_id=caso)

            # DEPOIS: leitor 1 (conversao_caso.py, via TeseCasoLink) concorda
            # com leitor 2 (legal_case_orchestrator.py, via ThesisCandidate).
            n_links_depois = (await db.execute(
                select(func.count()).select_from(TeseCasoLink)
                .where(TeseCasoLink.case_id == caso)
            )).scalar_one()
            candidatas_aprovadas = (await db.execute(
                select(ThesisCandidate).where(
                    ThesisCandidate.case_id == caso,
                    ThesisCandidate.status == "aprovada",
                )
            )).scalars().all()
            assert n_links_depois == 1
            assert len(candidatas_aprovadas) == 1
        finally:
            await _limpar(db, case_ids=[caso], tese_ids=[tese.id],
                          user_ids=[adv], client_ids=[cli])


async def test_aprovar_candidata_sugerida_pela_ia_nao_cria_vinculo():
    """Sem tese_banco_id (candidata sugerida pela IA, sem tese catalogada
    correspondente) não há o que vincular -- aprova na matriz, sem virar
    vínculo institucional automático. Comportamento esperado, não um bug."""
    from app.core.database import AsyncSessionLocal
    from app.services.matriz_teses_service import aprovar_tese

    async with AsyncSessionLocal() as db:
        adv = await _criar_user(db)
        cli = await _criar_cliente(db)
        caso = await _criar_caso(db, cli, adv)
        cand = ThesisCandidate(id=str(uuid4()), case_id=caso,
                               tese_banco_id=None,
                               tese="Tese sugerida pela IA, sem catálogo",
                               status="candidata")
        db.add(cand)
        await db.commit()

        try:
            cu = await _carregar_user(db, adv)
            out = await aprovar_tese(db, cand.id, cu, decisao="aprovada",
                                     case_id=caso)
            assert out.status == "aprovada"

            n_links = (await db.execute(
                select(func.count()).select_from(TeseCasoLink)
                .where(TeseCasoLink.case_id == caso)
            )).scalar_one()
            assert n_links == 0
        finally:
            await _limpar(db, case_ids=[caso], user_ids=[adv], client_ids=[cli])
