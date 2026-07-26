"""audit_log_worm — torna audit_logs imutável (WORM) via trigger (SYS-138)

Até aqui a imutabilidade da trilha de auditoria era só CONVENÇÃO (comentário no
model app/models/audit_log.py). Qualquer UPDATE/DELETE — por bug, credencial de
banco comprometida ou operador mal-intencionado — podia adulterar ou apagar
registros de auditoria sem barreira técnica.

Esta migration cria uma barreira no PRÓPRIO BANCO: uma função + trigger
BEFORE UPDATE OR DELETE em `audit_logs` que levanta exceção, bloqueando toda
alteração/exclusão de linhas existentes. INSERT continua livre (a trilha só
cresce — Write Once, Read Many). Reforça a imutabilidade exigida pela LGPD
(art. 37 — registro das operações de tratamento) com defesa em profundidade.

Aditiva e não-destrutiva: nenhuma linha é alterada; nenhum INSERT é afetado.
Idempotente (CREATE OR REPLACE FUNCTION + DROP TRIGGER IF EXISTS antes do CREATE).

Revision ID: 127_audit_log_worm
Revises: 126_fee_valor_check
Create Date: 2026-07-26
"""
from alembic import op

revision = "127_audit_log_worm"
down_revision = "126_fee_valor_check"
branch_labels = None
depends_on = None

_FUNC = "audit_logs_impedir_mutacao"
_TRIGGER = "trg_audit_logs_worm"


def upgrade() -> None:
    # Função que recusa qualquer UPDATE/DELETE em audit_logs.
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_FUNC}()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs é imutável (WORM): % não permitido (LGPD art.37)', TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    # Trigger BEFORE UPDATE OR DELETE — INSERT permanece livre (append-only).
    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER} ON audit_logs")
    op.execute(
        f"""
        CREATE TRIGGER {_TRIGGER}
            BEFORE UPDATE OR DELETE ON audit_logs
            FOR EACH ROW EXECUTE FUNCTION {_FUNC}();
        """
    )


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER} ON audit_logs")
    op.execute(f"DROP FUNCTION IF EXISTS {_FUNC}()")
