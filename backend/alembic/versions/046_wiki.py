"""046 wiki_paginas (#93 Wiki interna)

Aditivo e idempotente (CREATE TABLE IF NOT EXISTS) — seguro mesmo com o grafo
do Alembic reconstruído pelo stub 044.
"""
from alembic import op  # noqa
import sqlalchemy as sa  # noqa

revision = '046_wiki'
down_revision = '045_p1_resumo_ia'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS wiki_paginas (
            id            varchar(36) PRIMARY KEY,
            titulo        varchar(255) NOT NULL,
            slug          varchar(255),
            categoria     varchar(60),
            conteudo      text,
            atualizado_por varchar(36),
            created_at    timestamptz DEFAULT now(),
            updated_at    timestamptz DEFAULT now(),
            deleted_at    timestamptz
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_wiki_paginas_categoria ON wiki_paginas(categoria)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS wiki_paginas")
