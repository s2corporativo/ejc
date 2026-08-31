# -*- coding: utf-8 -*-
"""Os índices de listagem existem, são PARCIAIS e cobrem a coluna certa.

`AUD27-P3-11` pedia índice em `deleted_at`. Medido, esse índice não muda nada:
`deleted_at IS NULL` casa com ~96% das linhas, e o planejador ignora filtro que
não filtra. O custo estava na ORDENAÇÃO (`ORDER BY created_at DESC LIMIT 20`
sem índice em `created_at` ordena a tabela inteira para devolver 20 linhas).

Este teste guarda a conclusão CERTA, não a pedida — sem ele, alguém que leia o
achado original "corrige" trocando o índice parcial por um índice solto em
`deleted_at` e a regressão passa despercebida, porque nada quebra: só fica
lento de novo.

Roda contra Postgres real (o predicado parcial só existe no banco). Sem
RUN_DB_TESTS=1, pula.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.skipif(
    not (os.getenv("RUN_DB_TESTS") and os.getenv("SCHEMA_CHECK_DATABASE_URL")),
    reason="requer PostgreSQL (RUN_DB_TESTS=1 e SCHEMA_CHECK_DATABASE_URL)",
)

# tabela -> (índice, coluna que a listagem ordena)
_ESPERADOS = {
    "cases": ("ix_cases_listagem_ativa", "created_at"),
    "clients": ("ix_clients_listagem_ativa", "created_at"),
    "documents": ("ix_documents_listagem_ativa", "created_at"),
}


@pytest.fixture(scope="module")
def conn():
    eng = create_engine(os.environ["SCHEMA_CHECK_DATABASE_URL"])
    with eng.connect() as c:
        yield c


def _definicao(conn, indice: str) -> str:
    return conn.execute(
        text("SELECT indexdef FROM pg_indexes WHERE indexname = :i"),
        {"i": indice},
    ).scalar() or ""


@pytest.mark.parametrize("tabela", sorted(_ESPERADOS))
def test_indice_de_listagem_existe(conn, tabela):
    indice, _ = _ESPERADOS[tabela]
    assert _definicao(conn, indice), (
        f"{indice} sumiu — a listagem de /{tabela} volta a ordenar a tabela "
        f"inteira para devolver uma página de 20"
    )


@pytest.mark.parametrize("tabela", sorted(_ESPERADOS))
def test_indice_e_parcial_e_ordena_pela_coluna_certa(conn, tabela):
    indice, coluna = _ESPERADOS[tabela]
    ddl = _definicao(conn, indice)
    assert "WHERE (deleted_at IS NULL)" in ddl, (
        f"{indice} deixou de ser parcial: passaria a indexar também o registro "
        f"excluído, que nenhuma listagem lê"
    )
    assert coluna in ddl and "DESC" in ddl, (
        f"{indice} precisa cobrir {coluna} DESC — é a ordenação da listagem, "
        f"e é ela (não o filtro) que custa caro"
    )


def test_deadlines_nao_ganhou_indice_redundante(conn):
    """`deadlines` estava no achado e ficou de fora DE PROPÓSITO.

    Ela ordena por `data_prazo` e já tem `ix_deadlines_data_prazo`; medido, o
    parcial não acrescenta nada sobre o simples (0,16 ms × 0,19 ms). Se alguém
    adicionar depois "para completar as quatro tabelas do achado", terá pago
    escrita por zero ganho — este teste conta a medição a essa pessoa.
    """
    assert _definicao(conn, "ix_deadlines_data_prazo"), (
        "o índice que JÁ resolvia a listagem de prazos sumiu"
    )
    assert not _definicao(conn, "ix_deadlines_listagem_ativa"), (
        "índice parcial redundante em deadlines: o simples já cobre a "
        "ordenação por data_prazo (medido em 1M de linhas)"
    )
