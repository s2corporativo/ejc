"""097 — adiciona o valor 'sucumbencia' à enum nativa `feetipo` (FeeTipo)

Contexto:
    A tela Honorarios.tsx oferece o tipo "Sucumbência", mas a enum Python
    FeeTipo (backend/app/models/fee.py) e o TIPO NATIVO `feetipo` do Postgres
    (criado em 001_inicial.py, name="feetipo") não continham esse valor — lançar
    um honorário de sucumbência resultava em erro do banco
    (invalid input value for enum feetipo: "sucumbencia").

Storage:
    fees.tipo é ENUM NATIVO `feetipo` (SAEnum(FeeTipo)). Logo é necessário
    `ALTER TYPE ... ADD VALUE` — não basta reatribuir dados (diferente de 074,
    onde a coluna era VARCHAR).

Autocommit:
    `ALTER TYPE ... ADD VALUE` não roda dentro do bloco transacional que o
    Alembic abre por padrão em versões antigas do Postgres (< 12). Por isso o
    comando executa em `op.get_context().autocommit_block()` (fora da transação),
    garantindo compatibilidade em qualquer versão. IF NOT EXISTS torna o passo
    idempotente — mesmo padrão de 011_correcoes_auditoria.py (enum clientorigem).

Downgrade:
    No-op documentado. O Postgres não remove valores de enum de forma segura
    (exigiria recriar o tipo e reescrever todas as colunas que o usam) e remover
    'sucumbencia' corromperia linhas que já o utilizem. Mesmo tratamento de
    011_correcoes_auditoria.py.

Revision ID: 097_fee_tipo_sucumbencia
Revises: 096_rag_embedding_1024
"""
from alembic import op

revision = "097_fee_tipo_sucumbencia"
down_revision = "096_rag_embedding_1024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ADD VALUE precisa rodar FORA da transação do Alembic (compat. Postgres < 12).
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE feetipo ADD VALUE IF NOT EXISTS 'sucumbencia'")


def downgrade() -> None:
    # Postgres não remove valores de enum com segurança: no-op documentado.
    # (mesmo tratamento de 011_correcoes_auditoria.py / enum clientorigem.)
    pass
