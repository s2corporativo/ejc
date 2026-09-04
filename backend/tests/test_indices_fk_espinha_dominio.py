# -*- coding: utf-8 -*-
"""FK que aponta para a espinha do domínio precisa de índice.

Achado da auditoria funcional de 22/08/2026 (Issue #1237), prioridade 15 (§71).

FK sem índice custa em dois momentos que importam: todo JOIN/filtro pela coluna
vira varredura sequencial, e remover a linha PAI varre a tabela FILHA inteira
para conferir a restrição.

A anotação anterior da auditoria dizia "6 tabelas periféricas sem índice de FK,
impacto não medido". Medido no schema real (148 migrations do zero): eram **74**
FKs de coluna única sem índice — a anotação errava por mais de uma ordem de
grandeza.

A migration 148 NÃO cobre as 74, e a escolha é o ponto deste teste. Das 74, 50
apontam para `users` (`created_by`, `aprovado_por`, `alterado_por`): trilha,
escrita uma vez e praticamente nunca usada como filtro. Indexá-las custaria
escrita em 50 tabelas por uma consulta que não existe. O que este teste trava é
a **espinha** — `cases`, `clients`, `documents` —, percorrida em toda listagem
escopada a um caso, cliente ou documento.

Guardado por `RUN_DB_TESTS` + `SCHEMA_CHECK_DATABASE_URL` como os demais testes
de schema: sem Postgres não há o que medir, e um teste que "passa" sem banco
daria a garantia sem a verificação.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.skipif(
    not (os.getenv("RUN_DB_TESTS") and os.getenv("SCHEMA_CHECK_DATABASE_URL")),
    reason="requer PostgreSQL (RUN_DB_TESTS=1 e SCHEMA_CHECK_DATABASE_URL)",
)

ESPINHA = ("cases", "clients", "documents")

# FK de coluna única cuja PRIMEIRA coluna de índice não existe em nenhum índice.
_SQL_SEM_INDICE = text("""
    SELECT c.conrelid::regclass::text AS tabela,
           a.attname                   AS coluna,
           c.confrelid::regclass::text AS referencia
    FROM pg_constraint c
    JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
    WHERE c.contype = 'f'
      AND c.connamespace = 'public'::regnamespace
      AND array_length(c.conkey, 1) = 1
      AND NOT EXISTS (
            SELECT 1 FROM pg_index i
            WHERE i.indrelid = c.conrelid AND i.indkey[0] = k.attnum
      )
    ORDER BY 1, 2
""")


def _fks_sem_indice() -> list[tuple[str, str, str]]:
    eng = create_engine(os.environ["SCHEMA_CHECK_DATABASE_URL"])
    try:
        with eng.connect() as conn:
            return [tuple(r) for r in conn.execute(_SQL_SEM_INDICE)]
    finally:
        eng.dispose()


def test_nenhuma_fk_para_a_espinha_fica_sem_indice():
    """Toda FK apontando para cases/clients/documents tem de estar indexada."""
    descobertas = [
        (t, col, ref) for t, col, ref in _fks_sem_indice() if ref in ESPINHA
    ]
    assert not descobertas, (
        "FK sem índice apontando para a espinha do domínio: "
        + "; ".join(f"{t}.{col} -> {ref}" for t, col, ref in descobertas)
    )


def test_as_fks_de_trilha_para_users_seguem_fora_de_proposito():
    """Documenta a escolha, para que ela não seja desfeita por distração.

    Se um dia alguém indexar as 50 FKs de `users`, este teste falha e obriga a
    revisar a decisão explicitamente — em vez de o custo de escrita entrar sem
    ninguém notar. Não é proibição: é exigência de decisão consciente.
    """
    para_users = [t for t, _, ref in _fks_sem_indice() if ref == "users"]
    assert len(para_users) >= 40, (
        "as FKs de trilha para `users` foram indexadas (agora "
        f"{len(para_users)} sem índice). Isso adiciona custo de escrita em "
        "dezenas de tabelas para um padrão de consulta que não existe — se foi "
        "deliberado, atualize este teste e a migration 148 com a justificativa."
    )
