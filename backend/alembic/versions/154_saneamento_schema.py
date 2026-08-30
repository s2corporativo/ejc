"""Módulo de saneamento de base processual — tabelas isoladas (PROMPT 1).

Cria 7 tabelas próprias, prefixadas ``saneamento_*`` (saneamento_tpu_movimento,
saneamento_datajud_snapshot, saneamento_excecao_numero, saneamento_plano_dedup,
saneamento_indicativo_encerramento, saneamento_divergencia,
saneamento_execucao). NENHUMA alteração em tabela existente do EJC — schema
lógico totalmente novo e independente, revertido por completo no downgrade.

DECISÃO REGISTRADA — por que prefixo de tabela e não `CREATE SCHEMA`:
a especificação original (PROMPT 1) pedia um schema Postgres dedicado
(`saneamento.tabela`). Na prática isso quebra ferramentas estáticas
compartilhadas do repositório que não têm suporte a nomes qualificados por
schema: o classificador de compatibilidade de deploy
(`scripts/check_migration_compatibility.py` — extrai nome de tabela do
primeiro argumento de `op.create_table`, sem olhar `schema=`) e os testes de
paridade schema↔ORM (`test_schema_dr_parity.py`, `test_schema_sync.py` —
regex `CREATE TABLE (\\w+)` e AST de `op.create_table`, idem). Estender essas
três ferramentas compartilhadas para um único módulo seria desproporcional.
Tabela prefixada entrega o mesmo isolamento prático (zero coluna/constraint
compartilhada com tabela existente, dropável como unidade) sem exigir mudança
em infraestrutura de terceiros.

Todas as operações usam a API idiomática do Alembic (`op.create_table`/
`op.create_index`) para passar pelo gate de deploy sem exigir revisão manual
de DDL solto — só o seed do código TPU 246 usa `op.execute`, com
`deployment_policy = "additive_data_backfill"` (mesmo idioma de
132_processo_eletronico_mni.py: INSERT...SELECT...WHERE NOT EXISTS,
idempotente por construção).

Validado com `alembic upgrade head` do zero + `downgrade -1` + reaplicação,
contra PostgreSQL 16 + pgvector real, antes de abrir o PR (CLAUDE.md).

Constraints que carregam as regras de negócio inegociáveis do módulo:
  * `numero_cnj`/`numero_bruto` como TEXT com CHECK de 20 dígitos — nunca
    CHAR (bpchar faz padding e quebra join/índice único).
  * `saneamento_datajud_snapshot`: `grau` é NOT NULL DEFAULT '' (sentinela
    "grau não informado", nunca NULL de verdade) para que uma
    UniqueConstraint simples em (numero_cnj, grau) baste — Postgres trata
    NULL como sempre distinto em UNIQUE, o que abriria uma brecha para
    duplicata real com grau ausente. Efeito idêntico ao índice funcional
    `(numero_cnj, COALESCE(grau,''))` da especificação original, sem
    precisar de um índice UNIQUE solto (que o gate de deploy sinalizaria
    para revisão de lock/dados mesmo numa tabela nova).
  * `saneamento_indicativo_encerramento.decisao` só é preenchível COM
    `decidido_por` E `decidido_em` não nulos (CHECK) — sinaliza, nunca
    decide sozinho.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision = "154_saneamento_schema"
down_revision = "153_legal_doc_client_id"
branch_labels = None
depends_on = None

# Seed de saneamento_tpu_movimento é INSERT de dados, não DDL solto — mesmo
# idioma de 132_processo_eletronico_mni.py.
deployment_policy = "additive_data_backfill"
data_backfill_targets = ("saneamento_tpu_movimento",)


def upgrade() -> None:
    # ── Catálogo TPU (Res. CNJ 46/2007) com classificação funcional revisada
    op.create_table(
        "saneamento_tpu_movimento",
        sa.Column("codigo", sa.Integer(), primary_key=True),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("classe", sa.Text(), nullable=False, server_default="nao_classificado"),
        sa.Column("fonte", sa.Text(), nullable=False, server_default=""),
        sa.Column("revisado_por", sa.Text(), nullable=True),
        sa.Column("revisado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "classe IN ('terminativo', 'suspensivo', 'reativador', 'ordinario', 'nao_classificado')",
            name="ck_saneamento_tpu_classe",
        ),
    )

    # ── Snapshot dos metadados retornados pelo DataJud
    op.create_table(
        "saneamento_datajud_snapshot",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("numero_cnj", sa.Text(), nullable=False),
        sa.Column("grau", sa.Text(), nullable=False, server_default=""),
        sa.Column("tribunal", sa.Text(), nullable=True),
        sa.Column("classe_codigo", sa.Integer(), nullable=True),
        sa.Column("orgao_codigo", sa.Integer(), nullable=True),
        sa.Column("data_ajuizamento", sa.Date(), nullable=True),
        sa.Column("nivel_sigilo", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("coletado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("numero_cnj ~ '^[0-9]{20}$'", name="ck_saneamento_snapshot_numero_20d"),
        sa.UniqueConstraint("numero_cnj", "grau", name="ux_saneamento_snapshot_numero_grau"),
    )
    op.create_index(
        "ix_saneamento_snapshot_coletado_em", "saneamento_datajud_snapshot", ["coletado_em"],
    )
    op.create_index(
        "ix_saneamento_snapshot_payload", "saneamento_datajud_snapshot", ["payload"],
        postgresql_using="gin", postgresql_ops={"payload": "jsonb_path_ops"},
    )

    # ── Fila de exceção: números que falharam na validação do dígito verificador
    op.create_table(
        "saneamento_excecao_numero",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("id_interno", sa.Text(), nullable=False),
        sa.Column("numero_bruto", sa.Text(), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=False),
        sa.Column("resolvido", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("resolvido_por", sa.Text(), nullable=True),
        sa.Column("resolvido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("numero_corrigido", sa.Text(), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "numero_corrigido IS NULL OR numero_corrigido ~ '^[0-9]{20}$'",
            name="ck_saneamento_excecao_corrigido_20d",
        ),
    )
    op.create_index(
        "ix_saneamento_excecao_pendente", "saneamento_excecao_numero", ["resolvido"],
        postgresql_where=sa.text("resolvido = false"),
    )

    # ── Plano de deduplicação (proposta — nada é aplicado sem aprovação)
    op.create_table(
        "saneamento_plano_dedup",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("numero_cnj", sa.Text(), nullable=False),
        sa.Column("id_interno_principal", sa.Text(), nullable=False),
        sa.Column("ids_absorvidos", ARRAY(sa.Text()), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("aplicado", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("aplicado_por", sa.Text(), nullable=True),
        sa.Column("aplicado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("numero_cnj ~ '^[0-9]{20}$'", name="ck_saneamento_dedup_numero_20d"),
        sa.CheckConstraint(
            "tipo IN ('duplicata', 'multi_grau', 'conexo_sugerido')",
            name="ck_saneamento_dedup_tipo",
        ),
    )
    op.create_index(
        "ix_saneamento_plano_dedup_pendente", "saneamento_plano_dedup", ["aplicado"],
        postgresql_where=sa.text("aplicado = false"),
    )

    # ── Indicativo de encerramento — SINALIZAÇÃO, nunca baixa automática
    op.create_table(
        "saneamento_indicativo_encerramento",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("numero_cnj", sa.Text(), nullable=False),
        sa.Column("candidato", sa.Boolean(), nullable=False),
        sa.Column("confianca", sa.Text(), nullable=False),
        sa.Column("motivos", JSONB(), nullable=False, server_default="[]"),
        sa.Column("dias_de_silencio", sa.Integer(), nullable=True),
        sa.Column("movimento_terminativo", sa.Integer(), nullable=True),
        sa.Column("avaliado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        # Decisão humana. Enquanto NULL, o processo permanece ativo.
        sa.Column("decisao", sa.Text(), nullable=True),
        sa.Column("decidido_por", sa.Text(), nullable=True),
        sa.Column("decidido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("justificativa", sa.Text(), nullable=True),
        sa.CheckConstraint("numero_cnj ~ '^[0-9]{20}$'", name="ck_saneamento_indic_numero_20d"),
        sa.CheckConstraint(
            "confianca IN ('alta', 'media', 'baixa', 'nenhuma')",
            name="ck_saneamento_indic_confianca",
        ),
        sa.CheckConstraint(
            "decisao IS NULL OR decisao IN ('encerrar', 'manter_ativo')",
            name="ck_saneamento_indic_decisao_valores",
        ),
        sa.CheckConstraint(
            "decisao IS NULL OR (decidido_por IS NOT NULL AND decidido_em IS NOT NULL)",
            name="ck_saneamento_indic_decisao_exige_autor_e_data",
        ),
    )
    op.create_index(
        "ix_saneamento_indic_pendente_decisao", "saneamento_indicativo_encerramento",
        ["candidato", "confianca"], postgresql_where=sa.text("decisao IS NULL"),
    )

    # ── Divergências de reconciliação
    op.create_table(
        "saneamento_divergencia",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("numero_cnj", sa.Text(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("valor_interno", JSONB(), nullable=True),
        sa.Column("valor_datajud", JSONB(), nullable=True),
        sa.Column("observacao", sa.Text(), nullable=False, server_default=""),
        sa.Column("tratada", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("tratada_por", sa.Text(), nullable=True),
        sa.Column("tratada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("numero_cnj ~ '^[0-9]{20}$'", name="ck_saneamento_divergencia_numero_20d"),
    )
    op.create_index(
        "ix_saneamento_divergencia_pendente", "saneamento_divergencia", ["tipo"],
        postgresql_where=sa.text("tratada = false"),
    )

    # ── Log de execução das cargas/varreduras
    op.create_table(
        "saneamento_execucao",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("iniciado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("finalizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="em_andamento"),
        sa.Column("processados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("falhas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("detalhe", JSONB(), nullable=False, server_default="{}"),
        sa.CheckConstraint(
            "status IN ('em_andamento', 'sucesso', 'falha')", name="ck_saneamento_execucao_status",
        ),
    )

    # Semente: único código TPU confirmado em fonte oficial na especificação
    # (TJDFT — significado dos andamentos, código 246, verificado 30/08/2026).
    # INSERT...SELECT...WHERE NOT EXISTS: idempotente por construção, sem
    # depender do nome de uma constraint (mesmo idioma de 132).
    op.execute(
        """
        INSERT INTO saneamento_tpu_movimento (codigo, nome, classe, fonte)
        SELECT 246, 'Arquivado definitivamente', 'terminativo',
               'TJDFT - significado dos andamentos, codigo 246 (verificado 30/08/2026)'
        WHERE NOT EXISTS (
            SELECT 1 FROM saneamento_tpu_movimento WHERE codigo = 246
        )
        """
    )


def downgrade() -> None:
    op.drop_table("saneamento_execucao")
    op.drop_table("saneamento_divergencia")
    op.drop_table("saneamento_indicativo_encerramento")
    op.drop_table("saneamento_plano_dedup")
    op.drop_table("saneamento_excecao_numero")
    op.drop_table("saneamento_datajud_snapshot")
    op.drop_table("saneamento_tpu_movimento")
