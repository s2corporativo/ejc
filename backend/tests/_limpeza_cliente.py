"""Limpeza de teste: dependências de `clients` na ordem correta das FKs.

Por que este helper existe
--------------------------
Os testes `*_dblevel.py` rodam contra o Postgres real e limpam o que criaram
no `finally`/fixture, porque não há harness global de banco (cada arquivo
apaga o próprio rastro). O teardown clássico era `deadlines → cases → clients`,
o que bastava enquanto criar um cliente só criava um cliente.

Deixou de bastar quando a admissão passou a emitir o kit documental no ato do
cadastro (`_kit_admissao_automatico` em `app/routers/clients.py`): o `POST
/clients` grava também a procuração e o contrato de honorários em `legal_docs`.
A FK `fk_legal_docs_client_id_clients` é `NO ACTION`, então o `DELETE FROM
clients` estourava `ForeignKeyViolationError`, o cliente SOBREVIVIA ao teste e
poluía os testes seguintes — que falhavam em `ux_clients_cpf_hash` ao inserir o
mesmo CPF de fixture, ou em busca/conflito/dedupe achando cliente alheio.

O que este helper apaga
-----------------------
Somente as tabelas cuja FK para `clients` é `NO ACTION`/`RESTRICT` — as únicas
que efetivamente barram o `DELETE FROM clients`. As FKs `ON DELETE CASCADE`
(`atendimentos`, `dpt_diagnosticos`) e `ON DELETE SET NULL` (`case_partes`,
`contratos_societarios`, `data_rooms`, `inadimplencia_alerts`) se resolvem
sozinhas e não são tocadas. Onde a própria dependente tem filhos `NO ACTION`
(`documents`, `fees`, `solicitacoes_documentos`), os filhos vão antes.

Fora do escopo de propósito: `cases`, `users` e o próprio `clients`. Cada teste
já apaga esses três com os critérios que lhe interessam (por `case_id`, por
`LIKE` de nome, por lista de ids); duplicar isso aqui esconderia a intenção de
cada arquivo. Chame este helper ANTES de apagar `cases`/`users`/`clients`.

Escopo restrito de propósito: tudo é filtrado pelos `client_ids` recebidos —
nada de `TRUNCATE`, nada de `CASCADE` global, nada de apagar dado de outro
teste.

Uso::

    from _limpeza_cliente import limpar_dependencias_de_clientes

    await limpar_dependencias_de_clientes(db, [cid])
    await db.execute(text("DELETE FROM cases WHERE client_id = :id"), {"id": cid})
    await db.execute(text("DELETE FROM clients WHERE id = :id"), {"id": cid})
    await db.commit()

O helper NÃO faz commit: quem chama controla a transação.
"""
from __future__ import annotations

from typing import Iterable

from sqlalchemy import text

# Ordem obrigatória: netos → filhos → dependentes diretas de `clients`.
# `:cid` é sempre o id do cliente; nenhuma etapa alcança linha fora dele.
_ETAPAS: tuple[str, ...] = (
    # -- solicitações de documentos (itens apontam para a solicitação E para o
    #    documento; ambos os caminhos precisam sair antes dos pais).
    "DELETE FROM solicitacao_documento_itens WHERE solicitacao_id IN "
    "(SELECT id FROM solicitacoes_documentos WHERE client_id = :cid) "
    "OR documento_id IN (SELECT id FROM documents WHERE client_id = :cid)",
    "DELETE FROM solicitacoes_documentos WHERE client_id = :cid",
    # -- dependentes de `documents` com FK NO ACTION.
    "DELETE FROM provas WHERE document_id IN "
    "(SELECT id FROM documents WHERE client_id = :cid)",
    "DELETE FROM documentos_processo_eletronico_dedup WHERE document_id IN "
    "(SELECT id FROM documents WHERE client_id = :cid)",
    "DELETE FROM deadlines WHERE origem_documento_id IN "
    "(SELECT id FROM documents WHERE client_id = :cid)",
    # -- kit de admissão: assinatura aponta para o documento, então sai antes
    #    de `documents`; `legal_docs` e `procuracoes` são o kit em si.
    "DELETE FROM signature_requests WHERE client_id = :cid "
    "OR document_id IN (SELECT id FROM documents WHERE client_id = :cid)",
    "DELETE FROM legal_docs WHERE client_id = :cid",
    "DELETE FROM procuracoes WHERE client_id = :cid",
    "DELETE FROM documents WHERE client_id = :cid",
    # -- dependentes de `fees` com FK NO ACTION (a nota fiscal aponta para o
    #    honorário E para o cliente; sai por inteiro antes de `fees`).
    "DELETE FROM case_despesas WHERE fee_id IN "
    "(SELECT id FROM fees WHERE client_id = :cid)",
    "DELETE FROM fee_cobranca_envios WHERE fee_id IN "
    "(SELECT id FROM fees WHERE client_id = :cid)",
    "DELETE FROM fee_payments WHERE fee_id IN "
    "(SELECT id FROM fees WHERE client_id = :cid)",
    "DELETE FROM time_entries WHERE fee_id IN "
    "(SELECT id FROM fees WHERE client_id = :cid)",
    "DELETE FROM notas_fiscais_servico WHERE client_id = :cid "
    "OR fee_id IN (SELECT id FROM fees WHERE client_id = :cid)",
    "DELETE FROM fees WHERE client_id = :cid",
    # -- demais dependentes diretas com FK NO ACTION (filhos em CASCADE).
    "DELETE FROM document_intake_batches WHERE client_id = :cid",
    "DELETE FROM legal_chat_sessions WHERE client_id = :cid",
    "DELETE FROM preliminares WHERE client_id = :cid",
    "DELETE FROM sociedades_cliente WHERE client_id = :cid",
    "DELETE FROM lgpd_registros_tratamento WHERE client_id = :cid",
)


async def limpar_dependencias_de_clientes(db, client_ids: Iterable[str]) -> None:
    """Apaga as dependências que barram `DELETE FROM clients` desses clientes.

    Idempotente: rodar duas vezes (ou sobre id inexistente) não é erro. Ignora
    entradas vazias/`None` para o chamador poder passar a lista direto.
    """
    for cid in client_ids or ():
        if not cid:
            continue
        for sql in _ETAPAS:
            await db.execute(text(sql), {"cid": cid})


async def limpar_dependencias_de_clientes_por_sql(db, subconsulta: str,
                                                  params: dict | None = None) -> None:
    """Variante para teardown que seleciona clientes por critério, não por id.

    `subconsulta` é um SELECT que devolve ids de `clients` (ex.: o `LIKE` de
    nome usado pelos testes de CNPJ). Resolve os ids primeiro e delega, para a
    limpeza ficar com o mesmo caminho — e o mesmo escopo restrito — do resto.
    """
    ids = (await db.execute(text(subconsulta), params or {})).scalars().all()
    await limpar_dependencias_de_clientes(db, ids)
