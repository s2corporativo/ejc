"""094 — amplia a taxonomia canônica de áreas jurídicas do EJC.

Revision ID: 094_case_area_taxonomia
Revises: 093_raio_x_processo
"""
from alembic import op

revision = "094_case_area_taxonomia"
down_revision = "093_raio_x_processo"
branch_labels = None
depends_on = None

_NOVOS_VALORES = [
    "saude",
    "medico",
    "agrario",
    "agronegocio",
    "eleitoral",
    "internacional",
    "contratual",
    "societario",
    "licitacoes",
]

_AREAS = [
    ("saude", "Direito da Saúde", 170),
    ("medico", "Direito Médico", 180),
    ("agrario", "Direito Agrário", 190),
    ("agronegocio", "Direito do Agronegócio", 200),
    ("eleitoral", "Direito Eleitoral", 210),
    ("internacional", "Direito Internacional", 220),
    ("contratual", "Direito Contratual", 230),
    ("societario", "Direito Societário", 240),
    ("licitacoes", "Licitações e Contratos Administrativos", 250),
]


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for value in _NOVOS_VALORES:
            op.execute(f"ALTER TYPE casearea ADD VALUE IF NOT EXISTS '{value}'")

    values = ", ".join(
        f"('{slug}', '{name}', {order}, true)" for slug, name, order in _AREAS
    )
    op.execute(
        f"INSERT INTO areas (slug, nome, ordem, ativo) VALUES {values} "
        "ON CONFLICT (slug) DO NOTHING"
    )


def downgrade() -> None:
    # Valores de enum não são removidos para evitar reescrita destrutiva da coluna.
    conditions = " OR ".join(
        f"(slug = '{slug}' AND nome = '{name}')" for slug, name, _ in _AREAS
    )
    op.execute(f"DELETE FROM areas WHERE {conditions}")
