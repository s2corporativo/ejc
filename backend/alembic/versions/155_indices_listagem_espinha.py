"""Índices parciais para a listagem das tabelas espinha

Revision ID: 155_indices_listagem_espinha
Revises: 154_saneamento_schema
Create Date: 2026-08-31

Fecha `AUD27-P3-11`, que estava aberto desde 27/08 esperando exatamente isto:
`EXPLAIN ANALYZE` com volume, porque o item era uma HIPÓTESE ("tabelas espinha
sem índice em `deleted_at`", marcado "NÃO CONFIRMADO impacto real"), não um
defeito medido.

Medido agora (PG16 local, `cases` com 1.000.000 de linhas, 4% soft-deleted,
mediana de 5 execuções), a hipótese estava ERRADA no remédio e certa no
sintoma. Índice em `deleted_at` — o que o achado pedia — não muda nada:

    sem índice ............ 401,18 ms      índice em `deleted_at` .. 380,24 ms

O planejador ignora esse índice porque `deleted_at IS NULL` casa com 96% das
linhas: filtro que não filtra não paga índice. O custo real não estava no
FILTRO, estava na ORDENAÇÃO — `ORDER BY created_at DESC LIMIT 20` sem índice
em `created_at` obriga a ordenar a tabela inteira para devolver 20 linhas:

    índice PARCIAL (created_at DESC) WHERE deleted_at IS NULL .... 0,30 ms

E o ganho não é uma constante, é uma mudança de forma: para ESTA CONSULTA o
tempo deixa de crescer com a tabela (0,16 ms com mil linhas, 0,18 ms com um
milhão), porque a varredura para no vigésimo registro em vez de percorrer tudo.

    linhas        hoje      com índice parcial
     1.000      1,31 ms          0,16 ms
    10.000     11,17 ms          0,24 ms
   100.000     61,05 ms          0,25 ms
 1.000.000    364,00 ms          0,18 ms

O ENDPOINT, PORÉM, NÃO PARA DE CRESCER — e é honesto dizer onde este índice
não chega. Antes da consulta paginada, os três handlers executam uma CONTAGEM
exata sobre todo o conjunto vivo (`select(count()).select_from(q.subquery())`
em cases.py, clients.py e documents.py). Essa contagem varre tudo por
definição, e medi que o índice praticamente não a toca: 109,23 ms sem índice
contra 99,00 ms com ele, no mesmo milhão de linhas. Ou seja: a listagem sai de
364 ms para 0,18 ms, mas a resposta inteira continua limitada pelos ~100 ms da
contagem, que seguem O(n).

Isso NÃO é corrigível por índice, e não cabe aqui: as saídas são trocar o total
exato por estimativa (`reltuples`), servir o total sob demanda, ou paginar por
cursor — todas mudam o contrato da paginação e a UX, e são decisão do titular.
Fica registrado como item próprio no plano mestre em vez de escondido atrás de
um "corrigido" (achado do review do Codex no PR #1324).

Cobre as TRÊS tabelas cuja listagem ordena por `created_at` sem índice nessa
coluna. `deadlines`, citada no achado, fica DE FORA de propósito: ela ordena
por `data_prazo`, já tem `ix_deadlines_data_prazo`, e medi que o índice
parcial não acrescenta nada sobre o que já existe (0,16 ms hoje × 0,19 ms com
o parcial; 242,81 ms sem índice nenhum). Acrescentá-lo seria custo de escrita
por zero ganho — mesmo critério que a migration 150 usou para deixar 50 FKs
de trilha sem índice.

Também medi e DESCARTEI índices por advogado
(`(advogado_responsavel_id, created_at DESC)` e o par auxiliar, para o recorte
de `_filtro_visibilidade`): com o índice parcial já no lugar, eles pioraram o
caso do advogado (2,15 ms → 2,82 ms). Três índices a menos para manter.

Parcial, e não índice comum em `created_at`: só as linhas vivas entram, que é
o universo de toda listagem do produto. Índice menor, escrita mais barata, e
o registro excluído — que ninguém lista — não ocupa espaço.

ADITIVA E REVERSÍVEL: só cria índice, não toca em dado nem em coluna. O
`downgrade` remove os três.

Renumerada de 154 para 155 ao mesclar a `main` em 2026-08-31: o #1318
(saneamento de base processual) chegou primeiro e ocupou a 154. Mesma
colisão que renumerou a migration 150 (era 148) — numeração de migration
envelhece até dentro de PR aberto, e o head real é o do `alembic heads`.

NOTA DE OPERAÇÃO: `CREATE INDEX` comum toma lock de escrita na tabela pelo
tempo da construção. Nas tabelas do EJC hoje isso é instantâneo (volume de
escritório pequeno), e é assim que as migrations 115 e 150 já criaram índice
aqui. Se um dia a `cases` chegar à casa dos milhões, a construção passa a
querer `CONCURRENTLY` — que exige rodar fora de transação e não cabe no
formato conferível que o gate deste repositório exige.
"""
import sqlalchemy as sa
from alembic import op

revision = "155_indices_listagem_espinha"
down_revision = "154_saneamento_schema"
branch_labels = None
depends_on = None

_VIVAS = "deleted_at IS NULL"


def upgrade() -> None:
    op.create_index(
        "ix_cases_listagem_ativa",
        "cases",
        [sa.text("created_at DESC")],
        postgresql_where=sa.text(_VIVAS),
    )
    op.create_index(
        "ix_clients_listagem_ativa",
        "clients",
        [sa.text("created_at DESC")],
        postgresql_where=sa.text(_VIVAS),
    )
    op.create_index(
        "ix_documents_listagem_ativa",
        "documents",
        [sa.text("created_at DESC")],
        postgresql_where=sa.text(_VIVAS),
    )


def downgrade() -> None:
    op.drop_index("ix_documents_listagem_ativa", table_name="documents")
    op.drop_index("ix_clients_listagem_ativa", table_name="clients")
    op.drop_index("ix_cases_listagem_ativa", table_name="cases")
