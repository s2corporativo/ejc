"""Coluna ``tese_banco_id`` em ``thesis_candidates`` (Issue #1272).

Classe A do plano-mestre de padronização (`docs/estrategia/PLANO_MESTRE_EJC.md`):
"tese" tinha 6 representações no banco sem ponte entre elas. A mais grave:
`matriz_teses_service.montar_matriz` já sabe, no momento de montar a matriz,
de qual `Tese` do Banco institucional cada `ThesisCandidate` se originou
(`mapa_tese_banco` local à função) -- mas descartava essa referência ao
retornar. Consequência: aprovar uma candidata (HITL, `aprovar_tese`) nunca
criava o vínculo em `tese_caso_links`, e por isso duas rotas emitiam a MESMA
chave `tese_aprovada` com fontes disjuntas para o mesmo caso --
`routers/conversao_caso.py` olhando `tese_caso_links` (vazio),
`services/legal_case_orchestrator.py` olhando `thesis_candidates.status`
(aprovada). A Jornada do caso mostrava "Teses pesquisadas: pendente" no
mesmo caso em que o Dossiê Estratégico mostrava "1 tese vinculada".

Esta coluna fecha a ponte: `montar_matriz` passa a gravar `tese_banco_id`
para candidatas originadas do Banco; `aprovar_tese` passa a materializar o
vínculo em `tese_caso_links` automaticamente na aprovação, via
`services/tese_vinculo_service.py::vincular_tese_ao_caso` (mesma função que
`POST /teses/{id}/vincular-caso` já usava, agora write-path único).

Puramente aditiva e NULLABLE: candidatas sugeridas pela IA sem tese
catalogada correspondente ficam com `NULL` (comportamento esperado, não um
buraco a preencher). SEM BACKFILL -- candidatas já aprovadas ANTES desta
migration não têm como recuperar de forma confiável qual `Tese` originaram
(o mapeamento só existia em memória Python durante `montar_matriz`, nunca
foi persistido); inventar esse vínculo por correspondência textual seria
gravar dado jurídico não confiável. Vale só para aprovações a partir de agora.
"""

from alembic import op
import sqlalchemy as sa

revision = "149_thesis_candidate_tese_banco"
down_revision = "148_case_status_anterior"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "thesis_candidates",
        sa.Column("tese_banco_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_thesis_candidates_tese_banco_id",
        "thesis_candidates", "teses",
        ["tese_banco_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Reversível com perda apenas do vínculo registrado depois do upgrade:
    # tese_caso_links (a verdade do vínculo caso<->tese) não é tocada aqui.
    op.drop_constraint(
        "fk_thesis_candidates_tese_banco_id", "thesis_candidates", type_="foreignkey"
    )
    op.drop_column("thesis_candidates", "tese_banco_id")
