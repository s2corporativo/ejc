"""Produtor do módulo de saneamento (app/services/saneamento/produtor.py)
contra Postgres real — sem isso as tabelas de saneamento ficam vazias para
sempre (achado de revisão de código do PR #1318, Issue #1319).

Contrato coberto:
  - executar_varredura_dedup: Case+Process → RegistroProcesso → deduplicar()
    → PlanoDedup/ExcecaoNumero persistidos; idempotente (não empilha a cada
    execução); Execucao registra resultado, não só "rodou".
  - executar_varredura_datajud: no-op gracioso sem DATAJUD_ENABLED/API_KEY;
    com DataJud mockado (zero rede, mesmo padrão de
    test_saneamento_datajud_bridge.py), grava DatajudSnapshot +
    IndicativoEncerramento + Divergencia.

Sem RUN_DB_TESTS=1, pula (mesmo padrão dos demais *_dblevel.py).
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.services import datajud_service

_pg = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)

NUM_CNJ_OFICIAL = "00008323520184013202"  # TRF1 — mesmo número usado no resto do módulo
NUM_CNJ_OUTRO = "00009995220184013202"


async def _criar_cliente(db) -> str:
    cid = str(uuid4())
    await db.execute(
        text("INSERT INTO clients (id, tipo, nome, email, status) "
             "VALUES (:id, 'PF', 'Cliente Produtor Saneamento Teste', :email, 'ativo')"),
        {"id": cid, "email": f"{cid[:8]}@teste.local"},
    )
    return cid


async def _criar_caso(db, client_id: str, numero_processo: str | None) -> str:
    case_id = str(uuid4())
    mascarado = None
    if numero_processo is not None:
        mascarado = (
            f"{numero_processo[0:7]}-{numero_processo[7:9]}.{numero_processo[9:13]}."
            f"{numero_processo[13:14]}.{numero_processo[14:16]}.{numero_processo[16:20]}"
        )
    await db.execute(
        text("INSERT INTO cases (id, titulo, area, status, client_id, numero_processo) "
             "VALUES (:id, 'Caso produtor saneamento teste', 'civil', 'em_instrucao', :cid, :np)"),
        {"id": case_id, "cid": client_id, "np": mascarado},
    )
    return case_id


async def _criar_processo(db, case_id: str, numero_cnj: str, instancia: str | None = None) -> None:
    await db.execute(
        text("INSERT INTO processes (case_id, numero_cnj, instancia) VALUES (:cid, :cnj, :inst)"),
        {"cid": case_id, "cnj": numero_cnj, "inst": instancia},
    )


async def _limpar(db, *, case_ids=(), client_ids=()):
    for numero in (NUM_CNJ_OFICIAL, NUM_CNJ_OUTRO):
        await db.execute(text("DELETE FROM saneamento_indicativo_encerramento WHERE numero_cnj = :n"), {"n": numero})
        await db.execute(text("DELETE FROM saneamento_plano_dedup WHERE numero_cnj = :n"), {"n": numero})
        await db.execute(text("DELETE FROM saneamento_divergencia WHERE numero_cnj = :n"), {"n": numero})
        await db.execute(text("DELETE FROM saneamento_datajud_snapshot WHERE numero_cnj = :n"), {"n": numero})
    for cid in case_ids:
        await db.execute(text("DELETE FROM saneamento_excecao_numero WHERE id_interno = :id"), {"id": cid})
        await db.execute(text("DELETE FROM processes WHERE case_id = :id"), {"id": cid})
        await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": cid})
    for cid in client_ids:
        await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": cid})
    await db.execute(text("DELETE FROM saneamento_execucao"))
    await db.commit()


@pytest.fixture(autouse=True)
def _limpar_estado_rate_limit():
    datajud_service._ULTIMA_CONCESSAO = 0.0
    yield
    datajud_service._ULTIMA_CONCESSAO = 0.0


# ── executar_varredura_dedup ─────────────────────────────────────────────────

@_pg
async def test_varredura_dedup_persiste_plano_duplicata():
    from app.core.database import AsyncSessionLocal
    from app.services.saneamento.produtor import executar_varredura_dedup

    async with AsyncSessionLocal() as db:
        cli = await _criar_cliente(db)
        caso_a = await _criar_caso(db, cli, None)
        caso_b = await _criar_caso(db, cli, None)
        await _criar_processo(db, caso_a, NUM_CNJ_OFICIAL)
        await _criar_processo(db, caso_b, NUM_CNJ_OFICIAL)
        await db.commit()

    try:
        async with AsyncSessionLocal() as db:
            execucao = await executar_varredura_dedup(db)
        assert execucao.status == "sucesso"
        assert execucao.processados >= 2

        async with AsyncSessionLocal() as db:
            plano = (await db.execute(
                text("SELECT id_interno_principal, ids_absorvidos, tipo, aplicado "
                     "FROM saneamento_plano_dedup WHERE numero_cnj = :n"),
                {"n": NUM_CNJ_OFICIAL},
            )).mappings().one()
        assert plano["tipo"] == "duplicata"
        assert plano["aplicado"] is False
        assert {plano["id_interno_principal"], *plano["ids_absorvidos"]} == {caso_a, caso_b}
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db, case_ids=[caso_a, caso_b], client_ids=[cli])


@_pg
async def test_varredura_dedup_e_idempotente_nao_empilha_plano():
    """Rodar duas vezes não cria dois PlanoDedup pendentes para o mesmo par."""
    from app.core.database import AsyncSessionLocal
    from app.services.saneamento.produtor import executar_varredura_dedup

    async with AsyncSessionLocal() as db:
        cli = await _criar_cliente(db)
        caso_a = await _criar_caso(db, cli, None)
        caso_b = await _criar_caso(db, cli, None)
        await _criar_processo(db, caso_a, NUM_CNJ_OFICIAL)
        await _criar_processo(db, caso_b, NUM_CNJ_OFICIAL)
        await db.commit()

    try:
        async with AsyncSessionLocal() as db:
            await executar_varredura_dedup(db)
        async with AsyncSessionLocal() as db:
            await executar_varredura_dedup(db)

        async with AsyncSessionLocal() as db:
            total = (await db.execute(
                text("SELECT count(*) FROM saneamento_plano_dedup WHERE numero_cnj = :n"),
                {"n": NUM_CNJ_OFICIAL},
            )).scalar_one()
        assert total == 1
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db, case_ids=[caso_a, caso_b], client_ids=[cli])


@_pg
async def test_varredura_dedup_numero_invalido_vai_para_excecao():
    from app.core.database import AsyncSessionLocal
    from app.services.saneamento.produtor import executar_varredura_dedup

    async with AsyncSessionLocal() as db:
        cli = await _criar_cliente(db)
        caso = await _criar_caso(db, cli, None)
        # 19 dígitos — falha o DV/tamanho, é erro de digitação.
        await _criar_processo(db, caso, "0000832352018401320")
        await db.commit()

    try:
        async with AsyncSessionLocal() as db:
            execucao = await executar_varredura_dedup(db)
        assert execucao.status == "sucesso"

        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                text("SELECT numero_bruto, resolvido FROM saneamento_excecao_numero WHERE id_interno = :id"),
                {"id": caso},
            )).mappings().one()
        assert row["resolvido"] is False
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db, case_ids=[caso], client_ids=[cli])


@_pg
async def test_varredura_dedup_cobre_caso_legado_sem_process():
    """Caso sem NENHUM Process cadastrado (só o espelho legado
    Case.numero_processo) ainda entra na varredura — não é ignorado."""
    from app.core.database import AsyncSessionLocal
    from app.services.saneamento.produtor import executar_varredura_dedup

    async with AsyncSessionLocal() as db:
        cli = await _criar_cliente(db)
        caso = await _criar_caso(db, cli, NUM_CNJ_OFICIAL)  # só espelho, sem Process
        await db.commit()

    try:
        async with AsyncSessionLocal() as db:
            execucao = await executar_varredura_dedup(db)
        assert execucao.processados >= 1

        async with AsyncSessionLocal() as db:
            # Registro único (sem duplicata) não gera PlanoDedup nem exceção.
            total_planos = (await db.execute(
                text("SELECT count(*) FROM saneamento_plano_dedup WHERE numero_cnj = :n"),
                {"n": NUM_CNJ_OFICIAL},
            )).scalar_one()
        assert total_planos == 0
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db, case_ids=[caso], client_ids=[cli])


# ── executar_varredura_datajud ───────────────────────────────────────────────

@_pg
async def test_varredura_datajud_sem_chave_e_no_op_gracioso(monkeypatch):
    from app.core.database import AsyncSessionLocal
    from app.services.saneamento.produtor import executar_varredura_datajud

    s = get_settings()
    monkeypatch.setattr(s, "DATAJUD_ENABLED", False)

    async with AsyncSessionLocal() as db:
        execucao = await executar_varredura_datajud(db)
    assert execucao.status == "sucesso"
    assert execucao.processados == 0
    assert "motivo" in (execucao.detalhe or {})


@_pg
async def test_varredura_datajud_persiste_snapshot_e_indicativo(monkeypatch):
    from app.core.database import AsyncSessionLocal
    from app.services.saneamento.produtor import executar_varredura_datajud

    s = get_settings()
    monkeypatch.setattr(s, "DATAJUD_ENABLED", True)
    monkeypatch.setattr(s, "DATAJUD_API_KEY", "chave-publica-cnj-teste")

    fonte = {
        "numeroProcesso": NUM_CNJ_OFICIAL, "classe": {"codigo": 7},
        "orgaoJulgador": {"codigo": 1}, "dataAjuizamento": "2018-01-10T00:00:00Z",
        "tribunal": "TRF1", "grau": "G1", "formato": {"codigo": 1},
        "sistema": {"codigo": 1}, "nivelSigilo": 0,
        "movimentos": [{"codigo": 246, "nome": "Arquivado", "dataHora": "2020-01-01T00:00:00Z"}],
    }

    async def _fake_search(alias, payload, headers):
        return {"hits": {"hits": [{"_source": fonte}]}}

    monkeypatch.setattr(datajud_service, "_datajud_search", _fake_search)

    async with AsyncSessionLocal() as db:
        cli = await _criar_cliente(db)
        caso = await _criar_caso(db, cli, None)
        await _criar_processo(db, caso, NUM_CNJ_OFICIAL, instancia="G1")
        await db.commit()

    try:
        async with AsyncSessionLocal() as db:
            execucao = await executar_varredura_datajud(db, limite=10)
        assert execucao.status == "sucesso", execucao.detalhe
        assert execucao.processados >= 1

        async with AsyncSessionLocal() as db:
            snapshot = (await db.execute(
                text("SELECT tribunal, nivel_sigilo FROM saneamento_datajud_snapshot WHERE numero_cnj = :n"),
                {"n": NUM_CNJ_OFICIAL},
            )).mappings().one()
            indicativo = (await db.execute(
                text("SELECT candidato, confianca FROM saneamento_indicativo_encerramento WHERE numero_cnj = :n"),
                {"n": NUM_CNJ_OFICIAL},
            )).mappings().one()
        assert snapshot["tribunal"] == "TRF1"
        assert snapshot["nivel_sigilo"] == 0
        # Código 246 (semeado pela migration) = terminativo; silêncio desde
        # 2020 supera os 180 dias padrão — candidato a encerramento.
        assert indicativo["candidato"] is True
        assert indicativo["confianca"] in ("alta", "media", "baixa")
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db, case_ids=[caso], client_ids=[cli])


@_pg
async def test_varredura_datajud_atualiza_indicativo_pendente_em_vez_de_duplicar(monkeypatch):
    """Rodar duas vezes não cria dois indicativos pendentes para o mesmo
    numero_cnj — atualiza a linha existente (achado de revisão de código:
    job não pode empilhar sinalização a cada execução)."""
    from app.core.database import AsyncSessionLocal
    from app.services.saneamento.produtor import executar_varredura_datajud

    s = get_settings()
    monkeypatch.setattr(s, "DATAJUD_ENABLED", True)
    monkeypatch.setattr(s, "DATAJUD_API_KEY", "chave-publica-cnj-teste")

    fonte = {
        "classe": {"codigo": 7}, "orgaoJulgador": {"codigo": 1}, "tribunal": "TRF1",
        "grau": "G1", "nivelSigilo": 0,
        "movimentos": [{"codigo": 246, "nome": "Arquivado", "dataHora": "2020-01-01T00:00:00Z"}],
    }

    async def _fake_search(alias, payload, headers):
        return {"hits": {"hits": [{"_source": fonte}]}}

    monkeypatch.setattr(datajud_service, "_datajud_search", _fake_search)

    async with AsyncSessionLocal() as db:
        cli = await _criar_cliente(db)
        caso = await _criar_caso(db, cli, None)
        await _criar_processo(db, caso, NUM_CNJ_OFICIAL)
        await db.commit()

    try:
        async with AsyncSessionLocal() as db:
            await executar_varredura_datajud(db, limite=10)
        async with AsyncSessionLocal() as db:
            await executar_varredura_datajud(db, limite=10)

        async with AsyncSessionLocal() as db:
            total = (await db.execute(
                text("SELECT count(*) FROM saneamento_indicativo_encerramento "
                     "WHERE numero_cnj = :n AND decisao IS NULL"),
                {"n": NUM_CNJ_OFICIAL},
            )).scalar_one()
        assert total == 1
    finally:
        async with AsyncSessionLocal() as db:
            await _limpar(db, case_ids=[caso], client_ids=[cli])
