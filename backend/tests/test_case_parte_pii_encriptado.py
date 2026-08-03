"""P1-5 — o CPF/CNPJ da PARTE processual não existe mais em texto puro.

Auditoria integral, `docs/auditoria-ejc/12-seguranca-lgpd.md`. O cutover C6/LGPD
(migrations 061 → 112) tirou o documento em claro de `clients` e parou ali:
`case_partes.cpf_cnpj` — o CPF do autor, do réu, do terceiro e do procurador de
cada caso — seguia legível no banco. Era o furo mais largo dos dois, porque
guarda também o documento de quem NÃO é cliente e nunca contratou o escritório.

A migration 127 fecha isso. Estes testes travam as três consequências que um
refactor distraído desfaria:

1. a coluna em texto puro não volta (nem no model, nem em SQL escrito à mão);
2. quem cruza documento usa o ÍNDICE CEGO, não o valor — buscar por texto puro
   voltaria a exigir a coluna e reabriria o furo pela porta da consulta;
3. a leitura em claro continua possível para quem tem acesso ao caso, senão a
   aba de partes viraria uma lista de máscaras e o escritório perderia o dado
   de que precisa para peticionar.

Sem banco: o que se verifica aqui é o CONTRATO do model e das consultas. A
verificação row-level, contra Postgres real, está em
`test_client_anonimizacao_dblevel.py::test_anonimizacao_alcanca_as_tabelas_satelite`.
"""
from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def test_model_nao_tem_mais_coluna_de_texto_puro():
    from app.models.case_parte import CaseParte

    colunas = set(CaseParte.__table__.columns.keys())
    assert "cpf_cnpj" not in colunas, (
        "a coluna em texto puro voltou ao model — a migration 127 a removeu do banco, "
        "então o ORM passaria a pedir uma coluna inexistente"
    )
    assert {"cpf_cnpj_enc", "cpf_cnpj_hash", "cpf_cnpj_mascarado"} <= colunas


def test_documento_da_parte_faz_a_volta_completa(monkeypatch):
    """Cifra → grava → decifra devolve o MESMO documento normalizado.

    É o teste que prova que o dado não foi perdido no cutover: a máscara e o
    hash são derivados, mas o `cpf_cnpj_enc` tem de ser reversível.
    """
    from app.models.case_parte import CaseParte
    from app.services.pii_crypto import (
        encrypt, hash_documento, mascarar_documento, normalizar_documento,
    )

    doc = normalizar_documento("390.533.447-05")
    parte = CaseParte(cpf_cnpj_enc=encrypt(doc), cpf_cnpj_hash=hash_documento(doc),
                      cpf_cnpj_mascarado=mascarar_documento(doc))

    assert parte.cpf_cnpj_plain == "39053344705"
    assert parte.cpf_cnpj_mascarado == "***.533.447-**"
    # O que sai em resposta de busca/conflito é a MÁSCARA, e ela não permite
    # reconstruir o documento: 6 dos 11 dígitos ficam ocultos.
    assert "39053344705" not in parte.cpf_cnpj_mascarado


def test_ciphertext_corrompido_degrada_a_linha_e_nao_a_listagem():
    """A aba de partes decifra CADA linha — uma chave rotacionada não pode
    derrubar a aba inteira. Mesmo contrato de `Client.cpf_plain`."""
    from app.models.case_parte import CaseParte
    from app.models.client import PII_INDECIFRAVEL

    parte = CaseParte(cpf_cnpj_enc="isto-nao-e-um-token-fernet")
    assert parte.cpf_cnpj_plain == PII_INDECIFRAVEL


# `cpf_cnpj` como palavra INTEIRA. O lookbehind exclui `cliente_cpf_cnpj` (campo
# de template, sobre `clients`) e o lookahead exclui as colunas novas.
_NUA = re.compile(r"(?<![\w.])cpf_cnpj(?![\w])")

# Migrations e seeds são fotografias de um schema num ponto do tempo — a própria
# 127 precisa nomear a coluna que remove. Este arquivo também sai: é a guarda, e
# suas docstrings e mensagens de erro NOMEIAM a coluna de propósito.
_FORA_DA_VARREDURA = ("alembic/versions/", "seeds/", "tests/test_case_parte_pii_encriptado.py")


def _varrivel(caminho: Path) -> bool:
    return not caminho.relative_to(BACKEND).as_posix().startswith(_FORA_DA_VARREDURA)


def _sql_de_case_partes(caminho: Path):
    """Extrai os literais de string do arquivo que falam de `case_partes`.

    Via AST, de propósito: é onde o SQL cru vive, e comentários, docstrings e
    nomes de variável ficam de fora automaticamente. Uma varredura por linha —
    que foi minha primeira tentativa — confunde `# a coluna cpf_cnpj saiu` com
    uma consulta real, e confunde a coluna `cpf_cnpj` de `clients`
    (`COALESCE(cpf, cnpj) AS cpf_cnpj` em `dossie_cliente.py`) com esta.
    """
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        if isinstance(no, ast.Constant) and isinstance(no.value, str):
            if "case_partes" in no.value:
                yield no.lineno, no.value


def test_nenhum_sql_cru_grava_ou_le_a_coluna_removida():
    """Guarda de cutover: `case_partes.cpf_cnpj` não existe mais no banco.

    Uma referência sobrevivente não falha no import — falha em produção, na
    primeira requisição, com `UndefinedColumn`. É o que aconteceu na primeira
    rodada do CI deste PR: a versão anterior desta guarda enumerava os quatro
    arquivos que eu conhecia, e ficaram de fora dois testes DB-level
    (`test_search_dblevel.py`, `test_case_partes_dblevel.py`) que só rodam com
    `RUN_DB_TESTS=1` — verdes localmente, vermelhos no CI. Guarda de cutover se
    faz por VARREDURA, não por lista.
    """
    ofensores = [
        (caminho.relative_to(BACKEND).as_posix(), linha)
        for caminho in sorted(BACKEND.rglob("*.py"))
        if _varrivel(caminho)
        for linha, sql in _sql_de_case_partes(caminho)
        if _NUA.search(sql)
    ]
    assert not ofensores, (
        "SQL sobre `case_partes` ainda nomeia a coluna removida `cpf_cnpj` — "
        f"migre para cpf_cnpj_enc/_hash/_mascarado: {ofensores}"
    )


def test_nenhum_consumidor_usa_o_atributo_de_orm_removido():
    """O par do teste acima, para o caminho ORM (`CaseParte.cpf_cnpj`)."""
    alvo = re.compile(r"CaseParte\.cpf_cnpj(?![\w])")
    ofensores = [
        (caminho.relative_to(BACKEND).as_posix(), n)
        for caminho in sorted(BACKEND.rglob("*.py"))
        if _varrivel(caminho)
        for n, linha in enumerate(caminho.read_text(encoding="utf-8").splitlines(), 1)
        if alvo.search(linha)
    ]
    assert not ofensores, (
        f"`CaseParte.cpf_cnpj` não existe mais no model: {ofensores}"
    )


def test_sql_cru_de_case_partes_usa_as_colunas_novas():
    """`routers/case_partes.py` é o único CRUD em SQL cru desta tabela."""
    fonte = (BACKEND / "app/routers/case_partes.py").read_text(encoding="utf-8")
    for trecho in ("SELECT id, tipo", "INSERT INTO case_partes"):
        assert trecho in fonte, f"a consulta {trecho!r} mudou de forma — revise este teste"
    for coluna in ("cpf_cnpj_enc", "cpf_cnpj_hash", "cpf_cnpj_mascarado"):
        assert coluna in fonte, f"o INSERT deixou de gravar {coluna}"


def test_cruzamento_de_conflito_usa_indice_cego():
    """EOAB arts. 34-35: a checagem de conflito cruza a base inteira.

    Antes normalizava o texto puro em SQL (quatro `replace` aninhados, sem
    índice). Agora casa pelo hash — mais barato E sem tocar no valor. Se alguém
    reintroduzir a normalização em SQL, o documento em claro volta a ser
    necessário e o cutover se desfaz.
    """
    from app.routers import clients

    fonte = inspect.getsource(clients)
    assert "CaseParte.cpf_cnpj_hash == hash_documento(" in fonte
    assert "sqlfunc.replace(CaseParte" not in fonte
