# ── app/core/sql_safe.py ─────────────────────────────────────────────────────
# Construção defensiva de fragmentos SQL para identificadores dinâmicos.
#
# Regra: valores continuam SEMPRE em bind parameters. Este módulo só existe
# para os poucos casos em que o nome de uma coluna precisa variar em runtime.
# Identificadores de tabela/coluna nunca devem vir diretamente do request.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from sqlalchemy import bindparam, column, func, table, update
from sqlalchemy.sql.dml import Update


# Colunas editáveis por tabela — allowlist explícita. Campos gerenciados pelo
# sistema (id/created_at/updated_at/deleted_at) ficam deliberadamente fora.
COLUNAS_PERMITIDAS: dict[str, frozenset[str]] = {
    "users": frozenset({
        "email", "full_name", "role", "phone", "oab_number",
        "is_active", "avatar_url",
    }),
    "clients": frozenset({
        "tipo", "nome", "razao_social", "cpf", "cnpj",
        "email", "telefone", "whatsapp", "cep", "logradouro",
        "numero", "complemento", "bairro", "cidade", "estado",
        "origem", "status", "observacoes", "responsavel_id",
    }),
    "cases": frozenset({
        "titulo", "area", "status", "fase", "prioridade", "risco",
        "numero_processo", "tribunal", "comarca", "vara",
        "parte_contraria", "valor_causa", "tese_principal",
        "pontos_fortes", "pontos_fracos", "observacoes",
        "advogado_responsavel_id", "advogado_auxiliar_id",
        "data_encerramento",
    }),
    "deadlines": frozenset({
        "titulo", "descricao", "tipo", "prioridade", "status",
        "data_prazo", "data_conclusao", "responsavel_id",
        "base_legal", "observacoes",
    }),
    "documents": frozenset({
        "titulo", "descricao", "tipo", "confidencialidade",
        "case_id", "client_id",
    }),
    "legal_docs": frozenset({
        "titulo", "tipo_peca", "status", "human_reviewed",
        "revisor_id", "revisado_em", "versao",
    }),
    "fees": frozenset({
        "tipo", "valor", "percentual_exito", "status",
        "data_vencimento", "data_pagamento", "observacoes",
    }),
    "environmental_cases": frozenset({
        "tipo", "orgao_autuador", "numero_auto", "status_defesa",
        "valor_multa", "valor_multa_convertida", "resultado_julgamento",
        "observacoes",
    }),
    "agenda_eventos": frozenset({
        "titulo", "tipo", "data_evento", "hora", "local", "descricao",
        "concluido", "responsavel_id",
    }),
    "client_pending_items": frozenset({
        "case_id", "title", "description", "type", "status", "due_date",
        "impacto", "providencia",
    }),
    "office_contracts": frozenset({
        "title", "counterparty", "contract_type", "status", "start_date",
        "end_date", "value", "description", "file_url", "alert_days_before",
    }),
    "office_expenses": frozenset({
        "categoria", "subcategoria", "tipo", "descricao", "valor",
        "vencimento", "pago_em", "recorrente", "recorrencia", "status",
        "competencia",
    }),
    "memoria_institucional": frozenset({
        "tipo", "titulo", "conteudo", "resultado", "area_direito",
    }),
}

_COLUNA_RE = re.compile(r"^[a-z_][a-z0-9_.]{0,60}$", re.I)
_PARAM_RE = re.compile(r"^[a-z_][a-z0-9_]{0,60}$", re.I)
_OPERADOR_RE = re.compile(
    r"^(=|!=|<|>|<=|>=|LIKE|ILIKE|IS NULL|IS NOT NULL)$",
    re.I,
)
_RESERVED_SET_FIELDS = frozenset({"id", "created_at", "updated_at", "deleted_at"})
_OPERADORES_SEM_PARAM = frozenset({"IS NULL", "IS NOT NULL"})


def _exigir_tabela_permitida(tabela: str) -> frozenset[str]:
    if not tabela:
        raise ValueError("Tabela obrigatória para construção de SQL dinâmico")
    permitidas = COLUNAS_PERMITIDAS.get(tabela)
    if permitidas is None:
        raise ValueError(f"Tabela não permitida: {tabela!r}")
    return permitidas


def validar_coluna(coluna: str, tabela: str = "") -> str:
    """Valida sintaxe e, quando informada, a allowlist da tabela."""
    if not isinstance(coluna, str) or not _COLUNA_RE.fullmatch(coluna):
        raise ValueError(f"Nome de coluna inválido: {coluna!r}")
    if tabela:
        permitidas = _exigir_tabela_permitida(tabela)
        if coluna not in permitidas:
            raise ValueError(f"Coluna {coluna!r} não permitida na tabela {tabela!r}")
    return coluna


def validar_parametro(param: str) -> str:
    """Valida o nome do bind parameter; o valor nunca é interpolado no SQL."""
    if not isinstance(param, str) or not _PARAM_RE.fullmatch(param):
        raise ValueError(f"Nome de parâmetro inválido: {param!r}")
    return param


def construir_set(
    campos: Mapping[str, Any],
    *,
    tabela: str,
    touch_updated_at: bool = True,
) -> tuple[str, dict[str, Any]]:
    """Constrói SET com colunas allowlisted e valores via bind parameters."""
    _exigir_tabela_permitida(tabela)
    if not campos:
        raise ValueError("Nenhum campo para atualizar")

    sets: list[str] = []
    params: dict[str, Any] = {}
    for campo, valor in campos.items():
        if campo in _RESERVED_SET_FIELDS:
            raise ValueError(f"Campo gerenciado pelo sistema não pode ser atualizado: {campo!r}")
        validar_coluna(campo, tabela)
        validar_parametro(campo)
        sets.append(f"{campo} = :{campo}")
        params[campo] = valor

    if touch_updated_at:
        sets.append("updated_at=NOW()")
    return ", ".join(sets), params


def construir_update(
    campos: Mapping[str, Any],
    *,
    tabela: str,
    id_param: str = "where_id",
    exigir_nao_excluido: bool = False,
    touch_updated_at: bool = True,
) -> tuple[Update, dict[str, Any]]:
    """Constrói UPDATE via SQLAlchemy Core, sem interpolar SQL textual.

    A tabela precisa existir em COLUNAS_PERMITIDAS e cada campo precisa estar
    na allowlist correspondente. O identificador de linha é sempre a coluna
    interna id e o nome do bind usado no WHERE também é validado.
    """
    _exigir_tabela_permitida(tabela)
    validar_parametro(id_param)
    if not campos:
        raise ValueError("Nenhum campo para atualizar")

    nomes: list[str] = []
    params: dict[str, Any] = {}
    for campo, valor in campos.items():
        if campo in _RESERVED_SET_FIELDS:
            raise ValueError(
                f"Campo gerenciado pelo sistema não pode ser atualizado: {campo!r}"
            )
        validar_coluna(campo, tabela)
        validar_parametro(campo)
        nomes.append(campo)
        params[campo] = valor

    colunas = {"id", *nomes}
    if touch_updated_at:
        colunas.add("updated_at")
    if exigir_nao_excluido:
        colunas.add("deleted_at")

    tbl = table(tabela, *(column(nome) for nome in sorted(colunas)))
    valores = {nome: bindparam(nome) for nome in nomes}
    if touch_updated_at:
        valores["updated_at"] = func.now()

    stmt = update(tbl).where(tbl.c.id == bindparam(id_param)).values(valores)
    if exigir_nao_excluido:
        stmt = stmt.where(tbl.c.deleted_at.is_(None))
    return stmt, params


def construir_where(
    filtros: list[tuple[str, str, str | None]],
    *,
    tabela: str,
) -> tuple[str, dict[str, Any]]:
    """Constrói WHERE estruturalmente seguro.

    Cada filtro é (coluna, operador, nome_param). Para IS NULL e IS NOT NULL,
    nome_param deve ser None. IN/NOT IN não são aceitos aqui: exigem bind
    expansível/ARRAY explícito no chamador e não podem ser simulados por texto.
    """
    _exigir_tabela_permitida(tabela)
    if not filtros:
        return "", {}

    partes: list[str] = []
    for coluna, operador, param in filtros:
        validar_coluna(coluna, tabela)
        operador_normalizado = operador.upper().strip()
        if not _OPERADOR_RE.fullmatch(operador_normalizado):
            raise ValueError(f"Operador inválido: {operador!r}")

        if operador_normalizado in _OPERADORES_SEM_PARAM:
            if param is not None:
                raise ValueError(
                    f"Operador {operador_normalizado} não aceita parâmetro"
                )
            partes.append(f"{coluna} {operador_normalizado}")
            continue

        if param is None:
            raise ValueError(f"Operador {operador_normalizado} exige parâmetro")
        validar_parametro(param)
        partes.append(f"{coluna} {operador_normalizado} :{param}")

    return "WHERE " + " AND ".join(partes), {}
