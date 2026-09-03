"""Ficha viva do Banco de Teses — versionamento, fontes, overrides e gatilhos

Revision ID: 156_ficha_viva_teses
Revises: 155_indices_listagem_espinha
Create Date: 2026-09-03

⚠️ NÚMERO DISPUTADO — não integrar como 156 sem renumerar.
Bloqueio de governança registrado no PR #1417 (03/09/2026): a `main` continua
em `155_indices_listagem_espinha` e há quatro candidatas ao 156 (#1333, #1412,
#1368 e esta). A decisão vigente dá precedência a #1333, por ser a mudança
mais isolada de schema. A renumeração NÃO deve ser antecipada — o
procedimento e as condições estão no aviso do topo de
`alembic/MIGRATION_RESERVATIONS.md`. O conteúdo desta migration não muda com
a renumeração; mudam `revision`, `down_revision`, o ledger e as três guardas
de head.

Implementa a FASE "LEGAL KNOWLEDGE SKILLS" (§5 do Legal Drafting 2.0) sobre a
estrutura CANÔNICA, não ao lado dela.

A missão pedia quatro tabelas com nomes próprios — LegalSkillVersion,
LegalSkillSource, LegalSkillOverride, LegalSkillCaseUsage. Criá-las assim
contrariaria uma decisão já registrada neste mesmo ledger:

    "A fonte de verdade é `teses` + `tese_caso_links`. Não criar
     `legal_theses`, `teses_juridicas`, `teses_v2`, `teses_v4` ou outro banco
     paralelo. Qualquer evolução deve estender a estrutura canônica de forma
     aditiva."

E contrariaria o próprio §39 da missão ("não duplicar Banco de Teses"). `teses`
já É a ficha viva: título, fundamentação, jurisprudência, contra-argumento,
área, tribunal, tags e — o que não se obtém criando tabela — vitórias e
derrotas MEDIDAS em casos reais. Um catálogo paralelo nasceria com confiança
declarada em vez de medida, e as duas taxas divergiriam no primeiro mês.

Mapeamento efetivo:

    LegalSkillCaseUsage → `tese_caso_links`   JÁ EXISTIA — nada a fazer
    LegalSkillVersion   → `tese_versoes`      nova
    LegalSkillSource    → `tese_fontes`       nova
    LegalSkillOverride  → `tese_overrides`    nova
    gatilhos            → `teses.gatilhos`    nova coluna

ADITIVA E REVERSÍVEL: três tabelas novas e duas colunas novas com
`server_default`. Nenhuma tabela existente perde coluna, nenhum dado é
reescrito, nenhuma constraint nova incide sobre linha já gravada. Jurimetria,
Súmulas, matcher tese↔caso, Matriz de Teses e o frontend de `/teses` continuam
lendo exatamente o que liam.

`server_default` nas duas colunas é deliberado: sem ele, as linhas existentes
de `teses` ficariam com NULL numa coluna NOT NULL e a migration falharia em
banco com dado — e é justamente o banco de produção que tem dado.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "156_ficha_viva_teses"
down_revision = "155_indices_listagem_espinha"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Colunas novas na ficha canônica ───────────────────────────────────
    op.add_column(
        "teses",
        sa.Column("gatilhos", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default="[]"),
    )
    op.add_column(
        "teses",
        sa.Column("versao", sa.Integer(), nullable=False, server_default="1"),
    )

    # ── 2. Histórico IMUTÁVEL da ficha ───────────────────────────────────────
    op.create_table(
        "tese_versoes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tese_id", sa.String(length=36), nullable=False),
        sa.Column("versao", sa.Integer(), nullable=False),
        sa.Column("conteudo", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("resumo_mudanca", sa.Text(), nullable=True),
        sa.Column("criado_por", sa.String(length=36), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tese_id"], ["teses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["criado_por"], ["users.id"], ondelete="SET NULL"),
        # Duas versões 3 da mesma ficha tornariam o histórico ambíguo — e é o
        # histórico que responde "com base em quê o escritório sustentou isto".
        sa.UniqueConstraint("tese_id", "versao", name="uq_tese_versoes_tese_versao"),
    )
    op.create_index("ix_tese_versoes_tese_id", "tese_versoes", ["tese_id"])

    # ── 3. Lastro REAL de cada elemento da ficha ─────────────────────────────
    op.create_table(
        "tese_fontes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tese_id", sa.String(length=36), nullable=False),
        sa.Column("elemento", sa.String(length=20), nullable=False),
        sa.Column("referencia", sa.String(length=300), nullable=False),
        sa.Column("trecho", sa.Text(), nullable=False),
        sa.Column("fonte_url", sa.String(length=500), nullable=True),
        sa.Column("knowledge_doc_id", sa.String(length=36), nullable=True),
        sa.Column("authority_record_id", sa.String(length=36), nullable=True),
        sa.Column("status_verificacao", sa.String(length=20), nullable=False,
                  server_default="nao_verificada"),
        sa.Column("verificado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criado_por", sa.String(length=36), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tese_id"], ["teses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["authority_record_id"], ["authority_records.id"],
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["criado_por"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_tese_fontes_tese_id", "tese_fontes", ["tese_id"])
    # `knowledge_doc_id` SEM foreign key, de propósito: `knowledge_docs` é
    # curada e um documento pode ser removido do acervo sem que a ficha perca o
    # registro de que aquela fonte foi consultada — o `trecho` fica gravado
    # aqui. Índice para a consulta reversa ("que fichas citam este documento?").
    op.create_index("ix_tese_fontes_knowledge_doc_id", "tese_fontes",
                    ["knowledge_doc_id"])

    # ── 4. Decisão humana que AFASTA a ficha num caso ────────────────────────
    op.create_table(
        "tese_overrides",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tese_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("versao_tese", sa.Integer(), nullable=True),
        sa.Column("motivo", sa.String(length=30), nullable=False),
        sa.Column("justificativa", sa.Text(), nullable=False),
        sa.Column("criado_por", sa.String(length=36), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tese_id"], ["teses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["criado_por"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_tese_overrides_tese_id", "tese_overrides", ["tese_id"])
    op.create_index("ix_tese_overrides_case_id", "tese_overrides", ["case_id"])


def downgrade() -> None:
    # Ordem inversa. As tabelas novas só guardam dado que nasceu aqui, então o
    # downgrade não perde nada que exista em outro lugar — mas PERDE o histórico
    # de versões e os overrides, que são registro de auditoria: faça backup
    # antes de reverter em banco com uso real.
    op.drop_index("ix_tese_overrides_case_id", table_name="tese_overrides")
    op.drop_index("ix_tese_overrides_tese_id", table_name="tese_overrides")
    op.drop_table("tese_overrides")

    op.drop_index("ix_tese_fontes_knowledge_doc_id", table_name="tese_fontes")
    op.drop_index("ix_tese_fontes_tese_id", table_name="tese_fontes")
    op.drop_table("tese_fontes")

    op.drop_index("ix_tese_versoes_tese_id", table_name="tese_versoes")
    op.drop_table("tese_versoes")

    op.drop_column("teses", "versao")
    op.drop_column("teses", "gatilhos")
