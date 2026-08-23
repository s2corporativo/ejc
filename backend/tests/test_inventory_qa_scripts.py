"""Regressão dos scripts de homologação em `scripts/inventory/` (Issues #1186 e #1188).

Estes scripts só rodam contra uma stack de pé e com `EJC_QA_PASSWORD` exportada,
então não são importáveis na suíte. As checagens abaixo são estáticas (AST) e
cobrem três classes de defeito que já passaram silenciosamente por review:

1. **Placeholder no lugar da senha.** A migração para variável de ambiente trocou
   o literal por `"<ver EJC_QA_PASSWORD>"` em 10 scripts, mas manteve a string
   sendo usada como senha. O login devolve 401 e a bateria aborta no primeiro
   `authed()` — o script fica morto sem nunca acusar a causa. Complementa o gate
   de `scripts/ci_guard.sh`, que pega `SENHA = "literal"` mas não pega isto.

2. **Nome usado sem import no escopo.** O `NameError` é engolido pelo `try/except`
   de cada seção no `__main__` e a seção termina sem ter executado. Foi o que
   aconteceu com `AsyncSessionLocal` na seção 6 do M28: o relatório de homologação
   deu a bateria por concluída sem nunca testar isolamento entre casos.

3. **`global` onde o correto é `nonlocal`.** Dentro de closure, `global X` grava no
   módulo e a variável da função externa continua com o valor inicial — o teste
   cai no ramo de "não executado" mesmo quando a operação teve sucesso. Estava
   junto do defeito 2, na mesma função do M28.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


INVENTORY = Path(__file__).resolve().parents[2] / "scripts" / "inventory"

# Placeholders já commitados no lugar da senha real. Um placeholder é tão
# quebrado quanto um segredo versionado: o login falha e a bateria aborta.
PLACEHOLDERS_PROIBIDOS = ("<ver EJC_QA_PASSWORD>", "<EJC_QA_PASSWORD>", "SENHA_AQUI")

ESCOPOS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _scripts() -> list[Path]:
    return sorted(p for p in INVENTORY.glob("*.py") if p.name != "__init__.py")


def _arvore(caminho: Path) -> ast.Module:
    return ast.parse(caminho.read_text(encoding="utf-8"), filename=str(caminho))


def _pais(arvore: ast.Module) -> dict[ast.AST, ast.AST]:
    mapa: dict[ast.AST, ast.AST] = {}
    for no in ast.walk(arvore):
        for filho in ast.iter_child_nodes(no):
            mapa[filho] = no
    return mapa


def _cadeia_de_escopos(no: ast.AST, pais: dict[ast.AST, ast.AST]) -> list[ast.AST]:
    """Do escopo mais interno que contém `no` até o módulo, nessa ordem."""
    cadeia: list[ast.AST] = []
    atual = pais.get(no)
    while atual is not None:
        if isinstance(atual, ESCOPOS) or isinstance(atual, ast.Module):
            cadeia.append(atual)
        atual = pais.get(atual)
    return cadeia


def _ligados_no_escopo(escopo: ast.AST) -> set[str]:
    """Nomes ligados diretamente neste escopo, sem descer em escopos aninhados."""
    ligados: set[str] = set()
    corpo = escopo.body if isinstance(escopo, (ast.Module, *ESCOPOS[:2])) else []
    if isinstance(escopo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        args = escopo.args
        for grupo in (args.posonlyargs, args.args, args.kwonlyargs):
            ligados.update(a.arg for a in grupo)
        for extra in (args.vararg, args.kwarg):
            if extra is not None:
                ligados.add(extra.arg)

    pendentes = list(corpo)
    while pendentes:
        no = pendentes.pop()
        if isinstance(no, (ast.Import, ast.ImportFrom)):
            for alias in no.names:
                ligados.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            ligados.add(no.name)
            continue  # não desce: corpo pertence a outro escopo
        elif isinstance(no, ast.Name) and isinstance(no.ctx, ast.Store):
            ligados.add(no.id)
        pendentes.extend(ast.iter_child_nodes(no))
    return ligados


@pytest.mark.parametrize("script", _scripts(), ids=lambda p: p.name)
def test_sem_placeholder_de_senha(script: Path) -> None:
    conteudo = script.read_text(encoding="utf-8")
    encontrados = [p for p in PLACEHOLDERS_PROIBIDOS if p in conteudo]
    assert not encontrados, (
        f"{script.name} usa placeholder de senha {encontrados}. "
        "Leia de EJC_QA_PASSWORD com falha explícita quando ausente (padrão `_qa_pw`)."
    )


@pytest.mark.parametrize("script", _scripts(), ids=lambda p: p.name)
def test_senha_qa_definida_antes_do_primeiro_uso(script: Path) -> None:
    """`SENHA = _qa_pw(...)` precisa vir antes de qualquer uso.

    Vários destes scripts executam código no nível do módulo entre os imports,
    então inserir o helper depois do primeiro uso quebra com `NameError` já no
    boot — sem nem chegar no login.
    """
    arvore = _arvore(script)

    definicao = min(
        (
            no.lineno
            for no in ast.walk(arvore)
            if isinstance(no, ast.Name) and no.id == "SENHA" and isinstance(no.ctx, ast.Store)
        ),
        default=None,
    )
    if definicao is None:
        pytest.skip("script não usa a senha QA")

    usos = [
        no.lineno
        for no in ast.walk(arvore)
        if isinstance(no, ast.Name) and no.id == "SENHA" and isinstance(no.ctx, ast.Load)
    ]
    precoces = sorted(linha for linha in usos if linha < definicao)

    assert not precoces, (
        f"{script.name}: SENHA usada nas linhas {precoces} antes de ser definida na {definicao}."
    )


@pytest.mark.parametrize("script", _scripts(), ids=lambda p: p.name)
def test_async_session_local_importado_na_cadeia_de_escopos(script: Path) -> None:
    """`AsyncSessionLocal` deve estar ligado no escopo de uso ou em algum que o contenha."""
    arvore = _arvore(script)
    pais = _pais(arvore)
    cache: dict[int, set[str]] = {}

    faltando: set[str] = set()
    for no in ast.walk(arvore):
        if not (isinstance(no, ast.Name) and no.id == "AsyncSessionLocal"):
            continue
        if not isinstance(no.ctx, ast.Load):
            continue
        visivel = False
        for escopo in _cadeia_de_escopos(no, pais):
            nomes = cache.get(id(escopo))
            if nomes is None:
                nomes = _ligados_no_escopo(escopo)
                cache[id(escopo)] = nomes
            if "AsyncSessionLocal" in nomes:
                visivel = True
                break
        if not visivel:
            faltando.add(f"linha {no.lineno}")

    assert not faltando, (
        f"{script.name}: AsyncSessionLocal usado sem import visível em {sorted(faltando)}. "
        "O NameError é engolido pelo try/except da seção e o teste nunca roda."
    )


@pytest.mark.parametrize("script", _scripts(), ids=lambda p: p.name)
def test_global_nao_mascara_variavel_de_funcao_externa(script: Path) -> None:
    """`global X` numa closure cujo escopo externo já liga X é sempre `nonlocal` disfarçado."""
    arvore = _arvore(script)
    pais = _pais(arvore)

    erros: list[str] = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Global):
            continue
        # cadeia[0] é a função que contém o `global`; as demais são as externas.
        externas = [e for e in _cadeia_de_escopos(no, pais)[1:] if isinstance(e, ESCOPOS)]
        for nome in no.names:
            if any(nome in _ligados_no_escopo(e) for e in externas):
                erros.append(f"`global {nome}` na linha {no.lineno}")

    assert not erros, (
        f"{script.name}: {', '.join(erros)} — o escopo externo já liga esse nome. "
        "Use `nonlocal`, senão a função externa nunca enxerga o valor gravado."
    )
