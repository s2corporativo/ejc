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

import inspect
from pathlib import Path

import pytest

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


@pytest.mark.parametrize(
    "arquivo",
    [
        "app/routers/case_partes.py",
        "app/routers/clients.py",
        "app/routers/search.py",
        "app/services/client_anonimizacao.py",
    ],
)
def test_nenhum_consumidor_referencia_a_coluna_removida(arquivo):
    """Guarda de cutover: `case_partes.cpf_cnpj` não existe mais no banco.

    Uma referência sobrevivente não falharia no import — falharia em produção,
    na primeira requisição, com `UndefinedColumn`. Por isso a checagem é
    textual: pega tanto o atributo de ORM quanto o SQL escrito à mão (o
    `case_partes.py` é todo `text()`), que nenhum type checker alcança.

    `cpf_cnpj` como NOME DE CAMPO da requisição segue válido (ParteCreate) — o
    contrato de entrada não mudou; o que mudou é como o valor é persistido.
    """
    fonte = (BACKEND / arquivo).read_text(encoding="utf-8")
    ofensores = [
        (n, linha.strip())
        for n, linha in enumerate(fonte.splitlines(), 1)
        # Só a referência NUA: `cpf_cnpj` seguido de `_enc`/`_hash`/`_mascarado`
        # é a coluna nova; `body.cpf_cnpj`/`cpf_cnpj:` é o campo de entrada.
        if "CaseParte.cpf_cnpj" in linha
        and not any(
            f"CaseParte.cpf_cnpj_{s}" in linha for s in ("enc", "hash", "mascarado")
        )
    ]
    assert not ofensores, (
        f"{arquivo} ainda lê a coluna removida `case_partes.cpf_cnpj`: {ofensores}"
    )


def test_sql_cru_de_case_partes_nao_menciona_a_coluna_removida():
    """`routers/case_partes.py` é o único CRUD em SQL cru desta tabela."""
    fonte = (BACKEND / "app/routers/case_partes.py").read_text(encoding="utf-8")
    for trecho in ("SELECT id, tipo", "INSERT INTO case_partes"):
        assert trecho in fonte, f"a consulta {trecho!r} mudou de forma — revise este teste"
    # Nas listas de colunas SQL, `cpf_cnpj` só aparece sufixado.
    for linha in fonte.splitlines():
        if "cpf_cnpj" in linha and "cpf_cnpj_" not in linha:
            assert "body.cpf_cnpj" in linha or "cpf_cnpj:" in linha, (
                f"referência nua à coluna removida em SQL cru: {linha.strip()!r}"
            )


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
