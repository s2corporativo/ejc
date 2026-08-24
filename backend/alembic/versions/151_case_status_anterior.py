"""Coluna ``status_anterior`` em ``cases`` (Issue #1272).

Classe B do plano-mestre de padronização (`docs/estrategia/PLANO_MESTRE_EJC.md`):
`POST /cases/{id}/arquivar` e `POST /cases/{id}/encerrar` sempre jogavam o
caso para um dos dois estados terminais SEM registrar em que estágio de
trabalho real ele estava (`em_instrucao`/`em_producao`/`protocolado`).
Consequência: `POST /cases/{id}/desarquivar` — e o `PATCH {status:"aberto"}`
que o frontend usava para "reabrir" um caso encerrado — sempre devolviam o
caso para "aberto", descartando onde ele realmente estava.

`status_anterior` é preenchido no momento de arquivar/encerrar e consumido
(e limpo) no momento de desarquivar/reabrir — ver o event listener
`_limpar_campos_terminais_ao_reabrir` em `app/models/case.py`, que já cuida
de zerar os demais campos de desfecho/arquivamento ao sair de um estado
terminal e agora zera este também.

Migration puramente aditiva e NULLABLE: casos já arquivados/encerrados antes
desta migration têm `NULL` aqui, e o código trata `NULL` como "sem estágio
registrado" — cai no comportamento legado (reabre em "aberto"), nunca quebra.
Nenhum backfill: não há como reconstruir com certeza o estágio real de um
caso já arquivado sem essa informação.
"""

from alembic import op
import sqlalchemy as sa

revision = "151_case_status_anterior"
down_revision = "150_indices_fk_espinha_dominio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cases",
        sa.Column("status_anterior", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    # Reversível com perda apenas do estágio registrado depois do upgrade:
    # nenhuma outra tabela referencia esta coluna e nada é derivado dela.
    op.drop_column("cases", "status_anterior")
