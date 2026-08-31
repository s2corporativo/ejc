# -*- coding: utf-8 -*-
"""Os índices da migration 154 estão declarados no METADATA do ORM.

Achado do review do Codex no PR #1324, comprovado ao vivo antes de corrigir:
com os índices existindo só na migration, `alembic revision --autogenerate`
propunha `op.drop_index()` para os três. Uma migration futura desfaria a
correção de desempenho em silêncio — nada quebra, a listagem só volta a
ordenar a tabela inteira para devolver uma página de 20.

O `alembic/env.py` restringe o autogenerate por TABELA (as ~30 tabelas de SQL
cru sem model), mas diz em letras que "índices/constraints (`type_ != 'table'`)
seguem o padrão normal" — ou seja, são comparados. O repositório já foi mordido
por isto: o `index=True` de `Client.responsavel_id` existe exatamente para o
autogenerate não emitir DROP INDEX (achado #11).

Companheiro de `test_indices_listagem_espinha_dblevel.py`, que checa o outro
lado (o BANCO). Aqui é o metadata, e de propósito SEM banco: é justamente onde
não há Postgres que alguém roda um autogenerate distraído.
"""
from __future__ import annotations

import pytest

_ESPERADO = {
    "cases": "ix_cases_listagem_ativa",
    "clients": "ix_clients_listagem_ativa",
    "documents": "ix_documents_listagem_ativa",
}


def _indices_declarados(tabela: str) -> dict:
    from app.core.database import Base
    from app.models import case, client, document  # noqa: F401  (popula o metadata)

    return {ix.name: ix for ix in Base.metadata.tables[tabela].indexes}


@pytest.mark.parametrize("tabela", sorted(_ESPERADO))
def test_indice_de_listagem_declarado_no_orm(tabela):
    esperado = _ESPERADO[tabela]
    assert esperado in _indices_declarados(tabela), (
        f"{esperado} existe no banco (migration 154) mas NÃO está declarado no "
        f"model de {tabela}: o próximo `alembic revision --autogenerate` vai "
        f"propor op.drop_index() e desfazer a correção de desempenho"
    )


@pytest.mark.parametrize("tabela", sorted(_ESPERADO))
def test_declaracao_no_orm_e_parcial(tabela):
    """Declarar o índice SEM o predicado seria pior que não declarar.

    O autogenerate compara também o `postgresql_where`: um índice declarado
    como comum contra um índice parcial no banco continua sendo drift, e ele
    proporia derrubar o parcial e criar o comum — trocando um índice pequeno,
    só das linhas vivas, por um que indexa o registro excluído que nenhuma
    listagem lê.
    """
    ix = _indices_declarados(tabela)[_ESPERADO[tabela]]
    predicado = ix.dialect_options.get("postgresql", {}).get("where")
    assert predicado is not None, (
        f"{_ESPERADO[tabela]} declarado sem `postgresql_where`: continua "
        f"divergindo do índice PARCIAL que está no banco"
    )
    assert "deleted_at IS NULL" in str(predicado)
