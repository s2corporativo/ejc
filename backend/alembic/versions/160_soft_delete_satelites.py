"""160 — EXPAND: soft-delete (`deleted_at`) em atendimentos e case_partes (DB-05).

Achado DB-05 (P2) da auditoria de camadas de 06/09/2026: 54 models têm
soft-delete e 77 não. Um caso soft-deletado (`cases.deleted_at`) mantém seus
atendimentos e partes "vivos" — aparecem em listagens por cliente, no dossiê e
nos jobs do scheduler como se o caso existisse. `notification` ficou fora
desta rodada de propósito: a notificação é efêmera (lida/arquivada) e não
participa de listagem por caso vivo.

O que esta migration faz (ADITIVA, sem tocar em dado):
- `atendimentos.deleted_at` e `case_partes.deleted_at` — timestamptz NULL.
  NULL = vivo, exatamente a semântica de `cases`/`clients`/`documents`.
- Índices PARCIAIS para as listagens que passarão a filtrar por vivo:
  `ix_atendimentos_vivos_client_data (client_id, data_atendimento DESC)
  WHERE deleted_at IS NULL` — a listagem do histórico do cliente ordena
  assim (`routers/atendimentos.py`); `ix_case_partes_vivas_case (case_id)
  WHERE deleted_at IS NULL` — toda leitura de partes é escopada ao caso.
  Parciais pelo mesmo motivo medido na 155: só linha viva entra no índice.

O que esta migration NÃO faz: não filtra nada. Os routers e services que
listam essas tabelas precisam acrescentar `deleted_at IS NULL` (lista no
relatório do PR) e o soft-delete do caso precisa propagar às satélites — é
alteração de comportamento com teste, feita em PR de aplicação, não aqui.
Até lá, `deleted_at` fica NULL em todas as linhas e nada muda.

Os dois índices estão DECLARADOS NO ORM (`__table_args__`), pelo mesmo
motivo da 155: sem isso o autogenerate propõe `drop_index`.

`downgrade()` remove os índices e as colunas. Como nenhum código grava
`deleted_at` nestas tabelas antes do PR de aplicação, o downgrade não perde
informação; depois dele, um downgrade descartaria as marcações de exclusão
(as linhas voltariam a "vivas") — comportamento esperado de reverter um
soft-delete de schema.
"""
from alembic import op
import sqlalchemy as sa


revision = "160_soft_delete_satelites"
down_revision = "159_case_partes_pii_expand"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "atendimentos",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "case_partes",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_atendimentos_vivos_client_data",
        "atendimentos",
        ["client_id", sa.text("data_atendimento DESC")],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_case_partes_vivas_case",
        "case_partes",
        ["case_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_case_partes_vivas_case", table_name="case_partes")
    op.drop_index("ix_atendimentos_vivos_client_data", table_name="atendimentos")
    op.drop_column("case_partes", "deleted_at")
    op.drop_column("atendimentos", "deleted_at")
