"""O backfill de `documents.sha256` não pode inventar hash.

Auditoria de 22/08/2026 (Issue #1237), achado 31.

A migration 147 criou a coluna e o achado 30 fez os cinco caminhos de criação
preencherem-na. Isso resolve o futuro; o acervo anterior continua `NULL`. A
maquinaria de rescan (`document_rescan_service`) calcula o SHA-256 do acervo,
mas grava em `document_hash_rescan_items` — nasceu para DETECTAR DIVERGÊNCIA,
não para preencher coluna que ainda não existia.

O que este teste protege é a decisão de projeto do script, não a mecânica:

**Para um documento sem registro de ingestão, calcular o SHA-256 do arquivo
HOJE e gravá-lo registraria o estado atual como se fosse o original.** Se
aquele arquivo tivesse sido adulterado, o backfill carimbaria a adulteração
como íntegra — um sistema de prova documental atestando exatamente o que
deveria denunciar. `NULL` é a resposta honesta: "não há prova de integridade
para este documento". Um hash calculado hoje afirmaria "este é o original",
que não sabemos.

Por isso a única fonte aceita é `document_intake_items.sha256`, calculado NA
INGESTÃO. É um teste de texto-fonte de propósito: o que precisa continuar
verdadeiro é que o script **não abre arquivo nenhum** — não existe caminho de
código, nem futuro nem acidental, que derive o hash do conteúdo em disco.
"""
from __future__ import annotations

from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "backfill_documents_sha256.py"
)


def _sem_prosa(texto: str) -> str:
    """Remove DOCSTRINGS e comentários — preserva o resto do código.

    Duas versões anteriores desta função erraram, em direções opostas, e as
    duas foram pegas pelos próprios testes:

    1. ler o arquivo inteiro reprovava o script porque a prosa que EXPLICA a
       regra ("nenhum `filepath` é impresso") contém as palavras proibidas;
    2. remover toda string iniciada em linha própria engolia os literais SQL
       dentro de `text(\"\"\"...\"\"\")` — que são exatamente o código a inspecionar.

    O corte certo é sintático: só `Expr(Constant(str))` em posição de docstring
    (módulo, classe, função) sai; qualquer outra string fica.
    """
    import ast
    import io
    import tokenize

    linhas = texto.splitlines(keepends=True)
    apagar: set[int] = set()

    arvore = ast.parse(texto)
    for no in ast.walk(arvore):
        if not isinstance(
            no, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        corpo = getattr(no, "body", None)
        if not corpo:
            continue
        primeiro = corpo[0]
        if (
            isinstance(primeiro, ast.Expr)
            and isinstance(primeiro.value, ast.Constant)
            and isinstance(primeiro.value.value, str)
        ):
            apagar.update(range(primeiro.lineno, (primeiro.end_lineno or 0) + 1))

    comentarios: dict[int, int] = {}
    for tok in tokenize.generate_tokens(io.StringIO(texto).readline):
        if tok.type == tokenize.COMMENT:
            comentarios.setdefault(tok.start[0], tok.start[1])

    saida = []
    for numero, linha in enumerate(linhas, start=1):
        if numero in apagar:
            saida.append("\n")
        elif numero in comentarios:
            saida.append(linha[: comentarios[numero]].rstrip() + "\n")
        else:
            saida.append(linha)
    return "".join(saida)


@pytest.fixture(scope="module")
def fonte() -> str:
    """Só o código do script: docstrings e comentários fora."""
    assert SCRIPT.exists(), f"script de backfill ausente: {SCRIPT}"
    return _sem_prosa(SCRIPT.read_text(encoding="utf-8"))


def test_nao_calcula_hash_a_partir_do_arquivo(fonte: str):
    """O núcleo do achado 31: nenhuma via para derivar hash do disco."""
    proibidos = [
        "hashlib",                       # cálculo direto
        "calcular_sha256_local",         # primitiva local do rescan
        "calcular_sha256_remoto",        # primitiva remota (rclone)
        "document_hash_service",
        "open(",                         # leitura de arquivo
        "filepath",                      # nem sequer seleciona o caminho
    ]
    achados = [p for p in proibidos if p in fonte]
    assert not achados, (
        "o backfill não pode derivar hash do arquivo atual — isso carimbaria "
        f"como íntegro um arquivo possivelmente adulterado. Encontrado: {achados}"
    )


def test_a_unica_fonte_e_o_hash_de_ingestao(fonte: str):
    assert "document_intake_items" in fonte, (
        "a fonte do backfill precisa ser o hash calculado NA INGESTÃO"
    )


def test_so_escreve_onde_a_coluna_esta_nula(fonte: str):
    """Idempotência e não-sobrescrita, garantidas no próprio UPDATE.

    `AND sha256 IS NULL` no UPDATE (não só na seleção) fecha a janela entre o
    SELECT e a escrita: um upload concorrente que preencheu a coluna no meio do
    caminho não é sobrescrito por um valor decidido com estado velho.
    """
    assert "UPDATE documents SET sha256" in fonte
    idx = fonte.index("UPDATE documents SET sha256")
    trecho = fonte[idx:idx + 200]
    assert "sha256 IS NULL" in trecho, (
        "o UPDATE precisa condicionar a `sha256 IS NULL`, senão sobrescreve "
        "hash existente e deixa de ser idempotente"
    )


def test_dry_run_e_o_padrao(fonte: str):
    """Script que escreve em acervo jurídico não age por omissão."""
    assert 'APLICAR = "--aplicar" in sys.argv' in fonte, (
        "gravar precisa ser opt-in explícito"
    )


def test_conflito_entre_intakes_nao_e_desempatado_por_heuristica(fonte: str):
    """Dois hashes de ingestão para o mesmo arquivo é achado, não empate.

    Preencher com um dos dois esconderia uma divergência de integridade.
    """
    assert "count(DISTINCT i.sha256) = 1" in fonte, (
        "só preencher quando os intakes concordam"
    )
    assert "count(DISTINCT i.sha256) > 1" in fonte, (
        "os divergentes precisam ser contados e reportados, não ignorados"
    )


def test_nao_imprime_dado_pessoal_nem_caminho(fonte: str):
    """A saída é auditável e vai para log: só contagem e id (LGPD)."""
    for termo in ("filename", "titulo", "filepath"):
        assert termo not in fonte, (
            f"o relatório não pode expor `{termo}` — só contagens e ids"
        )


def test_documento_excluido_fica_de_fora(fonte: str):
    assert fonte.count("deleted_at IS NULL") >= 4, (
        "toda consulta precisa excluir documento apagado"
    )
