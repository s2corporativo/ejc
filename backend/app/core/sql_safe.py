# ── app/core/sql_safe.py ─────────────────────────────────────────────────────
# Proteção contra SQL injection em cláusulas WHERE/SET dinâmicas.
# Aproveitado do EJC v2 (componente validado em produção) +
# tabelas novas do v3: environmental_cases, legal_docs, fees, documents.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations
import re

# Colunas permitidas por tabela — whitelist explícita
COLUNAS_PERMITIDAS: dict[str, frozenset[str]] = {
    "users": frozenset([
        "email", "full_name", "role", "phone", "oab_number",
        "is_active", "avatar_url", "updated_at",
    ]),
    "clients": frozenset([
        "tipo", "nome", "razao_social", "cpf", "cnpj",
        "email", "telefone", "whatsapp", "cep", "logradouro",
        "numero", "complemento", "bairro", "cidade", "estado",
        "origem", "status", "observacoes", "responsavel_id", "updated_at",
    ]),
    "cases": frozenset([
        "titulo", "area", "status", "fase", "prioridade", "risco",
        "numero_processo", "tribunal", "comarca", "vara",
        "parte_contraria", "valor_causa", "tese_principal",
        "pontos_fortes", "pontos_fracos", "observacoes",
        "advogado_responsavel_id", "advogado_auxiliar_id",
        "data_encerramento", "updated_at",
    ]),
    "deadlines": frozenset([
        "titulo", "descricao", "tipo", "prioridade", "status",
        "data_prazo", "data_conclusao", "responsavel_id",
        "base_legal", "observacoes", "updated_at",
    ]),
    "documents": frozenset([
        "titulo", "descricao", "tipo", "confidencialidade",
        "case_id", "client_id", "updated_at",
    ]),
    "legal_docs": frozenset([
        "titulo", "tipo_peca", "status", "human_reviewed",
        "revisor_id", "revisado_em", "versao", "updated_at",
    ]),
    "fees": frozenset([
        "tipo", "valor", "percentual_exito", "status",
        "data_vencimento", "data_pagamento", "observacoes", "updated_at",
    ]),
    "environmental_cases": frozenset([
        "tipo", "orgao_autuador", "numero_auto", "status_defesa",
        "valor_multa", "valor_multa_convertida", "resultado_julgamento",
        "observacoes", "updated_at",
    ]),
}

_COLUNA_RE   = re.compile(r'^[a-z_][a-z0-9_.]{0,60}$')
_OPERADOR_RE = re.compile(
    r'^(=|!=|<|>|<=|>=|LIKE|ILIKE|IS NULL|IS NOT NULL|IN|NOT IN)$', re.I
)


def validar_coluna(coluna: str, tabela: str = "") -> str:
    """Valida que o nome de coluna é seguro. Lança ValueError se não for."""
    if not _COLUNA_RE.match(coluna):
        raise ValueError(f"Nome de coluna inválido: {coluna!r}")
    if tabela and tabela in COLUNAS_PERMITIDAS:
        if coluna not in COLUNAS_PERMITIDAS[tabela]:
            raise ValueError(f"Coluna '{coluna}' não permitida na tabela '{tabela}'")
    return coluna


def construir_set(campos: dict, tabela: str = "") -> tuple[str, dict]:
    """
    Constrói cláusula SET segura a partir de dict de campos validados.
    Retorna (set_sql, params) onde set_sql usa apenas nomes validados.
    """
    if not campos:
        raise ValueError("Nenhum campo para atualizar")
    sets, params = [], {}
    for campo, valor in campos.items():
        validar_coluna(campo, tabela)
        sets.append(f"{campo}=:{campo}")
        params[campo] = valor
    sets.append("updated_at=NOW()")
    return ", ".join(sets), params


def construir_where(
    filtros: list[tuple[str, str, str]], tabela: str = ""
) -> tuple[str, dict]:
    """
    Constrói cláusula WHERE segura.
    filtros: lista de (coluna, operador, nome_param)
    Valores devem ser adicionados pelo chamador no dict retornado.
    """
    if not filtros:
        return "", {}
    partes = []
    for coluna, operador, param in filtros:
        validar_coluna(coluna, tabela)
        if not _OPERADOR_RE.match(operador):
            raise ValueError(f"Operador inválido: {operador!r}")
        partes.append(f"{coluna} {operador} :{param}")
    return "WHERE " + " AND ".join(partes), {}
