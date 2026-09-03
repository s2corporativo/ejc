"""Regressões do GED/Documentos encontradas na auditoria E2E de 02/09/2026.

Estes testes são deliberadamente estáticos: protegem invariantes de lifecycle e
consulta sem depender de banco, Drive ou Redis e rodam também na suíte curta de
CI. Testes de integração continuam necessários para validar o fluxo completo.
"""
from __future__ import annotations

import ast
from pathlib import Path


ROUTER = Path(__file__).resolve().parents[1] / "app" / "routers" / "documents.py"


def _source() -> str:
    return ROUTER.read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    source = _source()
    tree = ast.parse(source)
    lines = source.splitlines()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            assert node.end_lineno is not None
            return "\n".join(lines[node.lineno - 1 : node.end_lineno])
    raise AssertionError(f"Função {name!r} não encontrada em {ROUTER}")


def test_router_documentos_compila_com_ast() -> None:
    ast.parse(_source())


def test_soft_delete_por_doc_id_nao_apaga_storage_drive() -> None:
    remover = _function_source("remover")
    assert "gd.delete_file" not in remover
    assert "_soft_delete_documento" in remover


def test_soft_delete_drive_legado_nao_apaga_storage_drive() -> None:
    remover_drive = _function_source("deletar_documento_drive")
    assert "gd.delete_file" not in remover_drive
    assert "_soft_delete_documento" in remover_drive


def test_listagem_limita_busca_e_tem_desempate_deterministico() -> None:
    listar = _function_source("listar")
    assert "max_length=200" in listar
    assert "page_size: int = Query(20, ge=1, le=100)" in listar
    assert "Document.created_at.desc(), Document.id.desc()" in listar


def test_busca_escapa_wildcards_sql_like() -> None:
    listar = _function_source("listar")
    assert '.replace("%", "\\\\%")' in listar
    assert '.replace("_", "\\\\_")' in listar
    assert 'escape="\\\\"' in listar
