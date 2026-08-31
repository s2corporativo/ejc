# -*- coding: utf-8 -*-
"""Guardrails não podem contar peça de caso EXCLUÍDO (AUD27-P2-1).

Reincidência pontual de V2-3.3 (exclusão de caso não cascateia): os
contadores de `/ia-governanca/guardrails` filtravam só o `deleted_at` da
própria peça, então o painel de governança seguia cobrando revisão humana
de peças cujo caso já foi excluído — trabalho que não existe mais.

O teste executa a condição REAL usada pelo endpoint contra o schema
migrado, porque o defeito é da consulta, não da view.
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, func, select, text

pytestmark = pytest.mark.skipif(
    not (os.getenv("RUN_DB_TESTS") and os.getenv("SCHEMA_CHECK_DATABASE_URL")),
    reason="requer PostgreSQL (RUN_DB_TESTS=1 e SCHEMA_CHECK_DATABASE_URL)",
)

MARCA = "AUD27P21"


@pytest.fixture()
def conn():
    eng = create_engine(os.environ["SCHEMA_CHECK_DATABASE_URL"])
    with eng.begin() as c:
        yield c
        c.execute(text(f"DELETE FROM legal_docs WHERE titulo LIKE '{MARCA}-%'"))
        c.execute(text(f"DELETE FROM cases WHERE titulo LIKE '{MARCA}-%'"))
        c.execute(text(f"DELETE FROM clients WHERE nome LIKE '{MARCA}-%'"))


def _cliente(conn) -> str:
    ident = str(uuid.uuid4())
    conn.execute(text(
        "INSERT INTO clients (id, nome, tipo, created_at, updated_at) "
        "VALUES (:i, :n, 'PF', now(), now())"
    ), {"i": ident, "n": f"{MARCA}-cliente"})
    return ident


def _caso(conn, client_id: str, *, excluido: bool) -> str:
    ident = str(uuid.uuid4())
    conn.execute(text(
        "INSERT INTO cases (id, client_id, titulo, area, created_at, updated_at, deleted_at) "
        "VALUES (:i, :c, :t, 'civil', now(), now(), :d)"
    ), {"i": ident, "c": client_id, "t": f"{MARCA}-caso",
        "d": "2026-08-30 00:00:00+00" if excluido else None})
    return ident


def _peca(conn, case_id: str | None) -> str:
    ident = str(uuid.uuid4())
    conn.execute(text(
        "INSERT INTO legal_docs (id, titulo, tipo_peca, conteudo, case_id, "
        "ai_generated, human_reviewed, created_at, updated_at) "
        "VALUES (:i, :t, 'peticao_inicial', 'x', :c, true, false, now(), now())"
    ), {"i": ident, "t": f"{MARCA}-peca", "c": case_id})
    return ident


def _contar(conn, ids: list[str]) -> int:
    """Conta com a MESMA condição do endpoint, restrita às peças do teste."""
    from app.models.legal_doc import LegalDoc
    from app.routers.ia_governanca import _peca_de_caso_vivo

    stmt = (
        select(func.count())
        .select_from(LegalDoc)
        .where(*_peca_de_caso_vivo(), LegalDoc.id.in_(ids))
    )
    return conn.execute(stmt).scalar() or 0


def test_peca_de_caso_excluido_nao_conta(conn):
    from app.models.legal_doc import LegalDoc

    cli = _cliente(conn)
    peca = _peca(conn, _caso(conn, cli, excluido=True))

    # Anti-vácuo: a peça existe e NÃO está excluída — pela condição antiga
    # (só o `deleted_at` da própria peça) ela contaria. Se este assert cair,
    # o teste virou vácuo e não guarda mais nada.
    naive = conn.execute(
        select(func.count()).select_from(LegalDoc)
        .where(LegalDoc.deleted_at.is_(None), LegalDoc.id == peca)
    ).scalar()
    assert naive == 1

    assert _contar(conn, [peca]) == 0, (
        "peça de caso excluído voltou a contar no guardrail — o painel cobra "
        "revisão humana de trabalho que já não existe"
    )


def test_peca_de_caso_vivo_conta(conn):
    cli = _cliente(conn)
    peca = _peca(conn, _caso(conn, cli, excluido=False))
    assert _contar(conn, [peca]) == 1


def test_peca_avulsa_continua_contando(conn):
    """Peça sem caso (vínculo por cliente) é legítima — a correção não pode
    engoli-la junto com o filho de caso excluído."""
    peca = _peca(conn, None)
    assert _contar(conn, [peca]) == 1
