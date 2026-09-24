"""Contrato de segurança para app.core.sql_safe."""
from __future__ import annotations

import pytest

from app.core.sql_safe import (
    COLUNAS_PERMITIDAS,
    construir_set,
    construir_update,
    construir_where,
    validar_coluna,
    validar_parametro,
)


def test_construir_update_nao_interpola_valores_no_sql():
    valor = "x'; DROP TABLE users; --"
    stmt, params = construir_update(
        {"titulo": valor, "concluido": True},
        tabela="agenda_eventos",
        id_param="eid",
    )
    sql = str(stmt)

    assert "UPDATE agenda_eventos SET" in sql
    assert "titulo" in sql and ":titulo" in sql
    assert "concluido" in sql and ":concluido" in sql
    assert "updated_at" in sql
    assert ":eid" in sql
    assert valor not in sql
    assert params == {"titulo": valor, "concluido": True}


def test_construir_update_falha_fechado_para_tabela_e_coluna():
    with pytest.raises(ValueError, match="Tabela não permitida"):
        construir_update({"titulo": "x"}, tabela="tabela_inventada")
    with pytest.raises(ValueError, match="não permitida"):
        construir_update({"created_by": "x"}, tabela="agenda_eventos")


def test_construir_set_usa_allowlist_e_bind_parameters():
    valor = "x'; DROP TABLE users; --"
    sql, params = construir_set(
        {"titulo": valor, "concluido": True},
        tabela="agenda_eventos",
    )

    assert sql == "titulo = :titulo, concluido = :concluido, updated_at=NOW()"
    assert valor not in sql
    assert params == {"titulo": valor, "concluido": True}


@pytest.mark.parametrize(
    ("tabela", "campo"),
    [
        ("agenda_eventos", "titulo"),
        ("client_pending_items", "status"),
        ("office_contracts", "end_date"),
        ("office_expenses", "valor"),
        ("memoria_institucional", "conteudo"),
    ],
)
def test_tabelas_reais_novas_estao_allowlisted(tabela: str, campo: str):
    assert campo in COLUNAS_PERMITIDAS[tabela]
    sql, params = construir_set({campo: "valor"}, tabela=tabela)
    assert f"{campo} = :{campo}" in sql
    assert params[campo] == "valor"


def test_tabela_desconhecida_falha_fechado():
    with pytest.raises(ValueError, match="Tabela não permitida"):
        construir_set({"titulo": "x"}, tabela="tabela_inventada")


def test_coluna_desconhecida_ou_injetada_e_rejeitada():
    with pytest.raises(ValueError, match="não permitida"):
        construir_set({"created_by": "u1"}, tabela="agenda_eventos")
    with pytest.raises(ValueError, match="Nome de coluna inválido"):
        validar_coluna("id; DROP TABLE users")


@pytest.mark.parametrize("campo", ["id", "created_at", "updated_at", "deleted_at"])
def test_campos_gerenciados_pelo_sistema_nao_entram_no_set(campo: str):
    with pytest.raises(ValueError, match="gerenciado pelo sistema"):
        construir_set({campo: "x"}, tabela="users")


@pytest.mark.parametrize(
    "param",
    ["id;DROP", "id value", "id)", ":id", "x/y"],
)
def test_nome_de_bind_parameter_e_validado(param: str):
    with pytest.raises(ValueError, match="Nome de parâmetro inválido"):
        validar_parametro(param)


def test_construir_where_valida_parametro_e_operador():
    sql, params = construir_where(
        [("status", "=", "status_filtro")],
        tabela="deadlines",
    )
    assert sql == "WHERE status = :status_filtro"
    assert params == {}

    with pytest.raises(ValueError, match="Nome de parâmetro inválido"):
        construir_where(
            [("status", "=", "status;DROP")],
            tabela="deadlines",
        )

    with pytest.raises(ValueError, match="Operador inválido"):
        construir_where(
            [("status", "IN", "status")],
            tabela="deadlines",
        )


def test_is_null_nao_gera_bind_invalido():
    sql, _ = construir_where(
        [("data_conclusao", "IS NULL", None)],
        tabela="deadlines",
    )
    assert sql == "WHERE data_conclusao IS NULL"

    with pytest.raises(ValueError, match="não aceita parâmetro"):
        construir_where(
            [("data_conclusao", "IS NULL", "p")],
            tabela="deadlines",
        )


def test_operador_comparativo_exige_parametro():
    with pytest.raises(ValueError, match="exige parâmetro"):
        construir_where(
            [("status", "=", None)],
            tabela="deadlines",
        )
