"""162 — Teses: pinned, fluxo de aprovação do sócio, fork e versionamento.

Estende o banco de Teses existente (``teses``) com 4 capacidades que faltavam
para a IA ser orientada pela doutrina do escritório:

1. ``pinned`` (booleano) — tese inegociável que entra SEMPRE no system_prompt
   das ``ai_skills``, mesmo sem seleção explícita (equivalente ao ``#`` do
   catálogo de habilidades).
2. Fluxo ``draft → in_review → approved`` — o ``TeseStatus`` atual
   (rascunho/ativa/arquivada) não distingue "aguardando sócio". Mantemos o
   enum legado e adicionamos ``revisor_id`` + ``revisao_em``: uma tese só é
   injetada no prompt quando ``status='ativa'`` E ``revisor_id IS NOT NULL``
   (carimbo do sócio responsável).
3. ``experiencia_minima`` (júnior/pleno/sênior/geral) — gating de uso.
4. ``tese_forks`` (cópia por advogado) e ``tese_versions`` (auditoria de
   edição) — o advogado personaliza uma tese aprovada sem mexer no original;
   toda edição de conteúdo salva a versão anterior.

A injeção no prompt acontece em ``app/services/ai_skill_service.py`` (PR
acompanha o patch): as teses ``pinned`` + as da área do caso entram no
``system_prompt`` da skill como bloco de doutrina — complementar ao RAG
(fato do caso) e à skill (operação).

Aditivo: não altera colunas existentes, não remove nada. Safe em produção.
"""
from alembic import op
import sqlalchemy as sa

revision = "162_teses_pinned_flow_prompt"
down_revision = "161_fee_estornos"


def upgrade() -> None:
    # 1. Novas colunas em `teses` (todas nullable p/ não quebrar linhas existentes)
    op.add_column("teses", sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("teses", sa.Column("experiencia_minima", sa.String(30), nullable=False, server_default="geral"))
    op.add_column("teses", sa.Column("revisor_id", sa.String(36), nullable=True))
    op.add_column("teses", sa.Column("revisao_em", sa.DateTime(timezone=True), nullable=True))
    op.add_column("teses", sa.Column("conteudo_estruturado", sa.Text(), nullable=True))
    # Markdown em 6 seções (Fundamentação/Tese central/Requisitos/Riscos/
    # Procedimento/Checklist) — separado de `descricao`/`fundamentacao`
    # legados para preservar reads existentes.

    op.create_index("ix_teses_pinned", "teses", ["pinned"])
    op.create_index("ix_teses_revisor_id", "teses", ["revisor_id"])
    op.create_foreign_key(
        "fk_teses_revisor_id_users",
        "teses", "users",
        ["revisor_id"], ["id"],
        ondelete="SET NULL",
    )

    # 2. Forks: cópia pessoal de uma tese aprovada, por advogado
    op.create_table(
        "tese_forks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tese_id", sa.String(36), sa.ForeignKey("teses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conteudo", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tese_id", "user_id", name="uq_tese_fork_tese_user"),
    )
    op.create_index("ix_tese_forks_tese_id", "tese_forks", ["tese_id"])
    op.create_index("ix_tese_forks_user_id", "tese_forks", ["user_id"])

    # 3. Versions: auditoria de cada edição de conteúdo
    op.create_table(
        "tese_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tese_id", sa.String(36), sa.ForeignKey("teses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conteudo", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("autor_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_tese_versions_tese_id", "tese_versions", ["tese_id"])
    op.create_index("ix_tese_versions_tese_id_version", "tese_versions", ["tese_id", "version"])


def downgrade() -> None:
    op.drop_index("ix_tese_versions_tese_id_version", table_name="tese_versions")
    op.drop_index("ix_tese_versions_tese_id", table_name="tese_versions")
    op.drop_table("tese_versions")

    op.drop_index("ix_tese_forks_user_id", table_name="tese_forks")
    op.drop_index("ix_tese_forks_tese_id", table_name="tese_forks")
    op.drop_table("tese_forks")

    op.drop_constraint("fk_teses_revisor_id_users", "teses", type_="foreignkey")
    op.drop_index("ix_teses_revisor_id", table_name="teses")
    op.drop_index("ix_teses_pinned", table_name="teses")
    op.drop_column("teses", "conteudo_estruturado")
    op.drop_column("teses", "revisao_em")
    op.drop_column("teses", "revisor_id")
    op.drop_column("teses", "experiencia_minima")
    op.drop_column("teses", "pinned")
