"""Constraints da migration 154 (tabelas `saneamento_*`) contra Postgres real.

Cobre exatamente as garantias que o CLAUDE.md exige verificar antes do push
de uma migration: as CHECK/índice que carregam as regras de negócio
inegociáveis do módulo, não só "a migration roda".

  - `saneamento_indicativo_encerramento`: decisão SEM autor+data é rejeitada
    PELO BANCO (não só pelo router) — sinaliza, nunca decide sozinho.
  - `saneamento_datajud_snapshot`: UniqueConstraint (numero_cnj, grau) —
    grau NOT NULL DEFAULT '' — permite o mesmo processo em graus distintos
    e bloqueia duplicata real.
  - `numero_cnj`/`numero_bruto`: CHECK de 20 dígitos rejeita lixo.

Sem RUN_DB_TESTS=1, toda a suíte deste arquivo é pulada (mesmo padrão dos
demais *_dblevel.py do repositório).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, DBAPIError

_pg = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)

NUM_CNJ_OFICIAL = "00008323520184013202"


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste():
    yield
    from app.core.database import engine
    await engine.dispose()


async def _limpar(db):
    await db.execute(text("DELETE FROM saneamento_indicativo_encerramento WHERE numero_cnj = :n"),
                      {"n": NUM_CNJ_OFICIAL})
    await db.execute(text("DELETE FROM saneamento_datajud_snapshot WHERE numero_cnj = :n"),
                      {"n": NUM_CNJ_OFICIAL})
    await db.execute(text("DELETE FROM saneamento_excecao_numero WHERE numero_bruto = :n"),
                      {"n": "lixo"})
    await db.commit()


@_pg
async def test_decisao_sem_autor_e_rejeitada_pelo_banco():
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await _limpar(db)
        with pytest.raises((IntegrityError, DBAPIError)):
            await db.execute(
                text(
                    "INSERT INTO saneamento_indicativo_encerramento "
                    "(numero_cnj, candidato, confianca, decisao) "
                    "VALUES (:n, true, 'alta', 'encerrar')"
                ),
                {"n": NUM_CNJ_OFICIAL},
            )
            await db.commit()
        await db.rollback()
        await _limpar(db)


@_pg
async def test_decisao_com_autor_e_data_e_aceita():
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await _limpar(db)
        await db.execute(
            text(
                "INSERT INTO saneamento_indicativo_encerramento "
                "(numero_cnj, candidato, confianca, decisao, decidido_por, decidido_em) "
                "VALUES (:n, true, 'alta', 'encerrar', 'adv-teste', :agora)"
            ),
            {"n": NUM_CNJ_OFICIAL, "agora": datetime.now(timezone.utc)},
        )
        await db.commit()
        row = (await db.execute(
            text("SELECT decisao, decidido_por FROM saneamento_indicativo_encerramento "
                 "WHERE numero_cnj = :n"),
            {"n": NUM_CNJ_OFICIAL},
        )).mappings().one()
        assert row["decisao"] == "encerrar"
        assert row["decidido_por"] == "adv-teste"
        await _limpar(db)


@_pg
async def test_indice_unico_bloqueia_duplicata_mas_permite_multi_grau():
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await _limpar(db)
        await db.execute(
            text("INSERT INTO saneamento_datajud_snapshot (numero_cnj, grau, payload) "
                 "VALUES (:n, 'G1', '{}'::jsonb)"),
            {"n": NUM_CNJ_OFICIAL},
        )
        await db.commit()

        # Mesmo grau de novo — deve violar o índice único.
        with pytest.raises((IntegrityError, DBAPIError)):
            await db.execute(
                text("INSERT INTO saneamento_datajud_snapshot (numero_cnj, grau, payload) "
                     "VALUES (:n, 'G1', '{}'::jsonb)"),
                {"n": NUM_CNJ_OFICIAL},
            )
            await db.commit()
        await db.rollback()

        # Grau diferente — mesmo processo em fase recursal, deve passar.
        await db.execute(
            text("INSERT INTO saneamento_datajud_snapshot (numero_cnj, grau, payload) "
                 "VALUES (:n, 'G2', '{}'::jsonb)"),
            {"n": NUM_CNJ_OFICIAL},
        )
        await db.commit()

        total = (await db.execute(
            text("SELECT count(*) FROM saneamento_datajud_snapshot WHERE numero_cnj = :n"),
            {"n": NUM_CNJ_OFICIAL},
        )).scalar()
        assert total == 2
        await _limpar(db)


@_pg
async def test_numero_fora_do_padrao_20_digitos_e_rejeitado():
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        with pytest.raises((IntegrityError, DBAPIError)):
            await db.execute(
                text("INSERT INTO saneamento_excecao_numero (id_interno, numero_bruto, numero_corrigido, motivo) "
                     "VALUES ('x', 'lixo', '123', 'teste')"),
            )
            await db.commit()
        await db.rollback()


@_pg
async def test_excecao_numero_aceita_numero_corrigido_valido():
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await db.execute(
            text("INSERT INTO saneamento_excecao_numero (id_interno, numero_bruto, numero_corrigido, motivo) "
                 "VALUES ('x-ok', 'lixo', :corrigido, 'teste')"),
            {"corrigido": NUM_CNJ_OFICIAL},
        )
        await db.commit()
        await db.execute(text("DELETE FROM saneamento_excecao_numero WHERE id_interno = 'x-ok'"))
        await db.commit()
