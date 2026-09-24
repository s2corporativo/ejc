"""Gate de regressão para SQL dinâmico nos módulos endurecidos.

O objetivo não é proibir SQLAlchemy text() em todo o EJC. O gate impede o
retorno dos padrões específicos em que identificadores eram montados a partir
de estruturas mutáveis sem uma allowlist única.
"""
from __future__ import annotations

from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]


def _src(rel: str) -> str:
    return (BACKEND / rel).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "rel",
    [
        "app/routers/agenda_eventos.py",
        "app/routers/pending_items.py",
        "app/routers/memoria_institucional.py",
        "app/routers/office_contracts.py",
        "app/routers/despesas.py",
    ],
)
def test_updates_dinamicos_usam_sql_safe(rel: str):
    src = _src(rel)
    assert "from app.core.sql_safe import construir_update" in src
    assert "construir_update(" in src
    assert 'text(f"UPDATE' not in src


def test_agenda_nao_reintroduz_filtro_ou_set_manual():
    src = _src("app/routers/agenda_eventos.py")
    assert "WHERE e.deleted_at IS NULL{filtro_pessoal}" not in src
    assert '", ".join(f"{k} = :{k}"' not in src


def test_pending_items_nao_reintroduz_coluna_do_payload_no_sql():
    src = _src("app/routers/pending_items.py")
    assert 'sets.append(f"{field}=:{field}")' not in src
    assert 'q += " AND status=:status"' not in src


def test_bank_analysis_tem_queries_estaticas_por_escopo():
    src = _src("app/routers/bank_analysis.py")
    assert "escopo =" not in src
    assert "{escopo}" not in src


def test_memoria_nao_reintroduz_where_por_join_de_strings():
    src = _src("app/routers/memoria_institucional.py")
    assert "' AND '.join(cond)" not in src
    assert 'sets.append(f"{field} = :{field}")' not in src


def test_office_contracts_nao_reintroduz_query_incremental():
    src = _src("app/routers/office_contracts.py")
    assert "cond_teto =" not in src
    assert 'q += " AND status=:status"' not in src
    assert 'sets = ", ".join(' not in src


def test_despesas_nao_reintroduz_where_ou_set_manual():
    src = _src("app/routers/despesas.py")
    assert "{comp_filter}" not in src
    assert "WHERE {where}" not in src
    assert 'set_clause = ", ".join(' not in src


def test_scheduler_flags_sql_sao_mapeadas_estaticamente():
    src = _src("app/services/scheduler.py")
    assert "_PRAZO_ALERTA_SQL" in src
    assert "d.{flag}" not in src
    assert "SET {flag}" not in src
    for flag in (
        "alerta_7d_enviado",
        "alerta_3d_enviado",
        "alerta_1d_enviado",
    ):
        assert f"AND d.{flag} = false" in src
        assert f"SET {flag}=true" in src


def test_fusao_mantem_excecao_de_identificador_quotado():
    # fusao.py descobre tabelas/colunas no information_schema; não é input do
    # request. A proteção adequada ali é quoting integral do identificador.
    from app.services.saneamento.fusao import _ident

    payload = 'x"; DROP TABLE cases; --'
    quoted = _ident(payload)
    assert quoted == '"x""; DROP TABLE cases; --"'
    assert quoted.startswith('"') and quoted.endswith('"')

    src = _src("app/services/saneamento/fusao.py")
    assert "information_schema" in src
    assert "_ident(tabela)" in src
    assert "_ident(coluna)" in src
