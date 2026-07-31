"""Vínculo estrutural e versionado entre LegalDoc e AILog.

Substitui a correlação por marcador textual truncável por:
- FK nullable `ai_logs.legal_doc_id`;
- SHA-256 do conteúdo efetivamente validado;
- flag estrutural de validade corrente;
- trigger que invalida validações quando `legal_docs.conteudo` muda.

Não há backfill heurístico: logs legados permanecem preservados e desvinculados.

Revision ID: 123_legal_doc_ai_log_vinculo
Revises: 122_route_usage_metrics
Create Date: 2026-07-29
"""

from alembic import op
import sqlalchemy as sa

revision = "123_legal_doc_ai_log_vinculo"
down_revision = "122_route_usage_metrics"
branch_labels = None
depends_on = None

_FK = "fk_ai_logs_legal_doc_id"
_INDEX = "ix_ai_logs_legal_doc_current_created"
_TRIGGER = "trg_legal_docs_invalidate_ai_validation"
_FUNCTION = "invalidate_legal_doc_ai_validations"


def upgrade() -> None:
    op.add_column(
        "ai_logs",
        sa.Column("legal_doc_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "ai_logs",
        sa.Column("legal_doc_content_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "ai_logs",
        sa.Column(
            "legal_doc_validation_current",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_foreign_key(
        _FK,
        "ai_logs",
        "legal_docs",
        ["legal_doc_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        _INDEX,
        "ai_logs",
        ["legal_doc_id", "legal_doc_validation_current", "created_at"],
        unique=False,
    )

    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.conteudo IS DISTINCT FROM OLD.conteudo THEN
                UPDATE ai_logs
                   SET legal_doc_validation_current = FALSE
                 WHERE legal_doc_id = NEW.id
                   AND legal_doc_validation_current = TRUE;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_TRIGGER}
        AFTER UPDATE OF conteudo ON legal_docs
        FOR EACH ROW
        EXECUTE FUNCTION {_FUNCTION}()
        """
    )


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER} ON legal_docs")
    op.execute(f"DROP FUNCTION IF EXISTS {_FUNCTION}()")
    op.drop_index(_INDEX, table_name="ai_logs")
    op.drop_constraint(_FK, "ai_logs", type_="foreignkey")
    op.drop_column("ai_logs", "legal_doc_validation_current")
    op.drop_column("ai_logs", "legal_doc_content_hash")
    op.drop_column("ai_logs", "legal_doc_id")
