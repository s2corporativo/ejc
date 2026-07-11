"""083 — alinha a taxonomia de áreas do caso aos ramos do sistema

O enum `casearea` tinha 9 valores enquanto o frontend oferece 14 ramos
(ramosConfig.ts) — um caso bancário precisava ser cadastrado como
civil/consumidor, degradando o contexto passado à IA. Esta migration:

1. Amplia o enum `casearea` com 7 valores: administrativo, bancario,
   imobiliario, sucessoes, constitucional, digital_lgpd, transito
   (total: 16). ALTER TYPE ... ADD VALUE não pode rodar dentro da
   transação da migração (restrição do Postgres) — autocommit_block
   resolve, mesmo padrão da migration 063. IDEMPOTENTE: IF NOT EXISTS.

2. Semeia a tabela canônica `areas` (criada VAZIA na migration 053 e
   nunca populada) com os 16 slugs espelhando o enum, `ordem` seguindo
   a sequência dos ramos no frontend. IDEMPOTENTE: ON CONFLICT (slug)
   DO NOTHING — não sobrescreve nome/ordem/ativo customizados.

Downgrade: Postgres não suporta remover valor de enum sem recriar o tipo
inteiro e reescrever a coluna (padrão aceito no projeto — ver 063); os
valores extras são inócuos, no-op. O seed de `areas` é revertido apenas
para as linhas exatamente como semeadas aqui (slug+nome), preservando
linhas pré-existentes ou editadas pelo time (mesmo critério da 078).

Revision ID: 083_case_area_ramos
Revises: 082_notification_preferences
Create Date: 2026-07-10
"""

from alembic import op

revision = "083_case_area_ramos"
down_revision = "082_notification_preferences"
branch_labels = None
depends_on = None


# Valores novos do enum casearea (os 9 originais vieram da migration 001).
_NOVOS_VALORES = [
    "administrativo",
    "bancario",
    "imobiliario",
    "sucessoes",
    "constitucional",
    "digital_lgpd",
    "transito",
]

# (slug, nome, ordem) — slugs = valores do enum casearea (fonte canônica);
# nomes e ordem seguem os ramos do frontend (ramosConfig.ts); sucessoes e
# constitucional (sem ramo dedicado no frontend) ficam ao final.
_AREAS = [
    ("empresarial",    "Direito Empresarial",            10),
    ("civil",          "Direito Cível",                  20),
    ("criminal",       "Direito Penal",                  30),
    ("trabalhista",    "Direito Trabalhista",            40),
    ("administrativo", "Direito Administrativo",         50),
    ("bancario",       "Direito Bancário e Financeiro",  60),
    ("tributario",     "Direito Tributário",             70),
    ("ambiental",      "Direito Ambiental",              80),
    ("consumidor",     "Direito do Consumidor",          90),
    ("familia",        "Direito de Família",            100),
    ("imobiliario",    "Direito Imobiliário",           110),
    ("previdenciario", "Direito Previdenciário",        120),
    ("digital_lgpd",   "Direito Digital e LGPD",        130),
    ("transito",       "Direito de Trânsito",           140),
    ("sucessoes",      "Direito das Sucessões",         150),
    ("constitucional", "Direito Constitucional",        160),
]


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE não pode rodar dentro da transação da migração
    # (restrição do Postgres) — autocommit_block resolve (padrão da 063).
    with op.get_context().autocommit_block():
        for valor in _NOVOS_VALORES:
            op.execute(f"ALTER TYPE casearea ADD VALUE IF NOT EXISTS '{valor}'")

    # Seed da tabela canônica `areas` (053 criou vazia). Idempotente e não
    # destrutivo: linhas já existentes (customizadas ou não) são preservadas.
    values = ", ".join(
        f"('{slug}', '{nome}', {ordem}, true)" for (slug, nome, ordem) in _AREAS
    )
    op.execute(
        f"INSERT INTO areas (slug, nome, ordem, ativo) VALUES {values} "
        "ON CONFLICT (slug) DO NOTHING"
    )


def downgrade() -> None:
    # Enum: Postgres não suporta remover valor de enum sem recriar o tipo
    # inteiro (e reescrever a coluna cases.area). Os valores extras são
    # inócuos — no-op seguro, padrão aceito no projeto (ver migration 063).

    # Seed: remove APENAS as linhas exatamente como semeadas aqui (slug+nome),
    # preservando linhas pré-existentes/renomeadas pelo time (critério da 078).
    conds = " OR ".join(
        f"(slug = '{slug}' AND nome = '{nome}')" for (slug, nome, _) in _AREAS
    )
    op.execute(f"DELETE FROM areas WHERE {conds}")
