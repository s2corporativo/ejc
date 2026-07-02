"""archiving: reversible case/process archive metadata

Revision ID: 059_archiving_cases_processes
Revises: 058_users_email_unique
"""
from alembic import op

revision = "059_archiving_cases_processes"
down_revision = "058_users_email_unique"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE cases ADD COLUMN IF NOT EXISTS archived_at timestamptz")
    op.execute("ALTER TABLE cases ADD COLUMN IF NOT EXISTS archive_reason text")
    op.execute("CREATE INDEX IF NOT EXISTS ix_cases_archived_at ON cases (archived_at)")

    op.execute("ALTER TABLE processes ADD COLUMN IF NOT EXISTS archived_at timestamptz")
    op.execute("ALTER TABLE processes ADD COLUMN IF NOT EXISTS archive_reason text")
    op.execute("CREATE INDEX IF NOT EXISTS ix_processes_archived_at ON processes (archived_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_processes_status ON processes (status)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_processes_status")
    op.execute("DROP INDEX IF EXISTS ix_processes_archived_at")
    op.execute("ALTER TABLE processes DROP COLUMN IF EXISTS archive_reason")
    op.execute("ALTER TABLE processes DROP COLUMN IF EXISTS archived_at")

    op.execute("DROP INDEX IF EXISTS ix_cases_archived_at")
    op.execute("ALTER TABLE cases DROP COLUMN IF EXISTS archive_reason")
    op.execute("ALTER TABLE cases DROP COLUMN IF EXISTS archived_at")
