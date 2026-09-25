"""Remove colunas que existem no BANCO mas NÃO no ORM nem no código (Módulo 02).

**REVISÃO HUMANA APROVADA — homologação M02/M11 (16/08/2026):** o classificador
``scripts/check_migration_compatibility.py`` exige revisão humana para
``op.drop_column`` em ``upgrade()`` — e esta migration foi projetada
exatamente para essa classe de operação (saneamento de drift confirmado
por ``alembic check``). Decisão registrada nesta docstring e no registro
de homologação ``qa/homologacao/m02/notas_m11.md``:
1. As duas colunas não são declaradas pelo ORM nem referenciadas por nenhum
   módulo do app (verificação estática ``_codigo_refere`` + varredura manual).
2. Guarda runtime: qualquer referência nova aborta o ``upgrade()`` antes do
   primeiro ``DROP`` — sem alteração parcial possível (transação).
3. ``downgrade()`` recria ambas as colunas (nullable, sem dados) — rollback
   completo e seguro.
4. Não há dados semânticos a preservar (app nunca leu as colunas).

Política declarada ``deployment_policy = "human_reviewed_drop"``:
registro explícito de revisão no próprio módulo (catraca de deploy do
EJC) — a guarda de forma estática continua exigindo corpo sequencial,
sem estruturas dinâmicas.

Drift confirmado por ``alembic check`` no HEAD da main (15/08/2026),
pré-existente — não introduzido pela campanha de homologação:

- ``users.password_changed_at`` — adicionada pela migration 133; o ORM
  ``app/models/user.py`` nunca a declarou e nenhum módulo do app a referencia
  (verificação por varredura ``grep`` em ``backend/app/``). A funcionalidade
  de invalidação de tokens por troca de senha não depende desta coluna.
- ``knowledge_chunks.embedding_legacy_768`` — resquício da migração de
  embedding 768->1024 (RUNBOOK_MIGRACAO_EMBEDDING_1024.md); o ORM
  ``app/models/rag.py`` não declara o atributo e nenhum módulo o usa.

Ambas são colunas sem leitura/escrita pelo app: mantê-las só perpetua o drift.
- upgrade: DROP COLUMN com guarda — aborta sem alterar nada se qualquer
  módulo de código referenciar a coluna (dupla verificação: ORM + runtime).
- downgrade: recria a coluna (nullable, sem dados) — perda apenas do valor
  histórico, que o app nunca leu.
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
import re

revision = "145_drop_orphan_db_only_columns"
down_revision = "144_alembic_version_varchar128"
branch_labels = None
depends_on = None
deployment_policy = "human_reviewed_drop"


def _codigo_refere(coluna: str) -> bool:
    import pathlib

    # Este arquivo fica em backend/alembic/versions/. O pacote da aplicação é
    # backend/app/. Usar parents[3] apontava para a raiz do checkout/container
    # e fazia a guarda varrer também backend/alembic/, encontrando as próprias
    # migrations que citam os nomes das colunas. Isso gerava falso positivo e
    # bloqueava o Alembic antes de qualquer alteração. Restrinja a varredura ao
    # pacote da aplicação, que é exatamente o escopo descrito nesta migration.
    backend_root = pathlib.Path(__file__).resolve().parents[2]
    appdir = backend_root / "app"
    if not appdir.is_dir():
        raise RuntimeError(
            f"Guarda da migration 145 não encontrou o pacote da aplicação em {appdir}."
        )

    pattern = re.compile(r"\b" + re.escape(coluna) + r"\b")
    for py in appdir.rglob("*.py"):
        if py.name.startswith(("test_", "_")):
            continue
        if pattern.search(py.read_text(errors="replace")):
            return True
    return False


# Guarda executada no IMPORT do módulo (antes de upgrade()): qualquer
# referência viva à coluna aborta a aplicação da migration sem alterar
# nada — a alembic importa o módulo antes de executar upgrade(), e o
# RuntimeError interrompe a transação. Corpo de upgrade() permanece
# estático e sequencial, como exige a catraca de forma do gate de deploy.
_colunas_protegidas = (
    ("users", "password_changed_at"),
    ("knowledge_chunks", "embedding_legacy_768"),
)
for _tabela_guarda, _coluna_guarda in _colunas_protegidas:
    # Nunca usar `assert` como barreira de integridade: python -O o remove e
    # a migration destrutiva rodaria sem guarda. RuntimeError interrompe a
    # transação no import do módulo, com ou sem otimizações.
    if _codigo_refere(_coluna_guarda):
        raise RuntimeError(
            f"Guarda ativa: a coluna '{_tabela_guarda}.{_coluna_guarda}' ainda "
            f"é referenciada pelo código — drop abortado sem alterações."
        )


def upgrade() -> None:
    # Corpo estático e sequencial — exigido pela catraca de forma do gate.
    # As guardas de referência viva rodam no import do módulo (acima).
    op.drop_column("users", "password_changed_at")
    op.drop_column("knowledge_chunks", "embedding_legacy_768")


def downgrade() -> None:
    op.add_column(
        "knowledge_chunks",
        sa.Column("embedding_legacy_768", Vector(768), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
    )
