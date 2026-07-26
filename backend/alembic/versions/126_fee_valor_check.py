"""fee_valor_check — CHECK de integridade nos valores financeiros (SYS-082/083)

Adiciona barreira no BANCO (defesa em profundidade além do schema Pydantic):
  - fees.valor         >= 0  (ou NULL)  — honorário nunca negativo.
  - fee_payments.valor  > 0             — pagamento estritamente positivo.

Ambos os CHECK são criados como NOT VALID de propósito: passam a valer para
TODA escrita futura (INSERT/UPDATE), mas NÃO revalidam as linhas legadas no
momento do deploy. A escolha é deliberada para dado contábil:

  - `fees.valor` só ganhou trava de não-negatividade na CRIAÇÃO; o FeeUpdate.valor
    ficou sem restrição (SYS-083), então parcelas negativas podem ter entrado via
    PATCH. `fee_payments.valor` nunca teve validação até o SYS-082 — logo ambas as
    tabelas podem conter valores inválidos herdados.
  - "Sanear" esses valores com UPDATE (zerar/inverter sinal) fabricaria um número
    contábil no lugar de um dado corrompido — pior que preservá-lo para
    reconciliação humana. Por isso NÃO saneamos: NOT VALID preserva o histórico
    (nenhum dado é dropado) e trava a corrupção daqui para frente. Depois de
    reconciliar as linhas legadas, um humano pode rodar
    `ALTER TABLE ... VALIDATE CONSTRAINT ...` para promover a validação total.

Aditiva e não-destrutiva. Idempotente (guarda em pg_constraint).

Revision ID: 126_fee_valor_check
Revises: 125_legal_doc_revisao
Create Date: 2026-07-26
"""
from alembic import op

revision = "126_fee_valor_check"
down_revision = "125_legal_doc_revisao"
branch_labels = None
depends_on = None

_CK_FEES = "ck_fees_valor_nao_negativo"
_CK_PAG = "ck_fee_payments_valor_positivo"


def _add_check_not_valid(constraint: str, tabela: str, expr: str) -> None:
    """ADD CONSTRAINT ... CHECK (...) NOT VALID de forma idempotente.

    O Postgres não tem `ADD CONSTRAINT IF NOT EXISTS`; guardamos em pg_constraint
    para o re-run não estourar 42710 (constraint duplicada)."""
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = '{constraint}'
            ) THEN
                ALTER TABLE {tabela}
                    ADD CONSTRAINT {constraint}
                    CHECK ({expr}) NOT VALID;
            END IF;
        END $$;
        """
    )


def upgrade() -> None:
    # Honorário: valor opcional (NULL até apurar), mas nunca negativo.
    _add_check_not_valid(_CK_FEES, "fees", "valor IS NULL OR valor >= 0")
    # Pagamento: obrigatório e estritamente positivo.
    _add_check_not_valid(_CK_PAG, "fee_payments", "valor > 0")


def downgrade() -> None:
    op.execute(f"ALTER TABLE fee_payments DROP CONSTRAINT IF EXISTS {_CK_PAG}")
    op.execute(f"ALTER TABLE fees DROP CONSTRAINT IF EXISTS {_CK_FEES}")
