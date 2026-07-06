"""078 — Semeia colunas padrão do Kanban de Casos (item 5.5).

A tabela `kanban_columns` era criada vazia (migration 053) e nunca semeada, então
o Kanban de Casos mostrava "Nenhuma coluna configurada para esta área". Esta
migration insere um conjunto padrão por `legal_area`.

Os nomes são ALINHADOS ao mapeamento coluna→status (`_status_da_coluna` em
routers/kanban.py) para que mover um card sincronize o status do caso:
  "aguardando prazo" → suspenso · "acordo" → acordo · "encerrad/entregue" →
  encerrado · "arquiv" → arquivado. "Triagem"/"Em andamento" não alteram status
  (comportamento desejado no início do fluxo).

Idempotente: só insere num `legal_area` que ainda não tem coluna alguma —
seguro em re-deploy e não sobrescreve colunas customizadas. Downgrade remove
apenas as linhas com os nomes semeados aqui (não toca colunas criadas pelo time).

Revision ID: 078_seed_kanban_columns
Revises: 077_deadline_confirmado_doc
"""
from alembic import op

revision = "078_seed_kanban_columns"
down_revision = "077_deadline_confirmado_doc"
branch_labels = None
depends_on = None


# (legal_area, [(name, position, color), ...])
_FLUXOS = {
    "default": [        # judicial
        ("Triagem", 0, "blue"),
        ("Em andamento", 1, "amber"),
        ("Aguardando prazo", 2, "orange"),
        ("Acordo", 3, "green"),
        ("Encerrado", 4, "slate"),
        ("Arquivado", 5, "slate"),
    ],
    "extrajudicial": [
        ("Triagem", 0, "blue"),
        ("Em negociação", 1, "amber"),
        ("Acordo", 2, "green"),
        ("Encerrado", 3, "slate"),
        ("Arquivado", 4, "slate"),
    ],
    "consultoria": [
        ("Triagem", 0, "blue"),
        ("Em elaboração", 1, "amber"),
        ("Entregue", 2, "green"),
        ("Arquivado", 3, "slate"),
    ],
}


def upgrade() -> None:
    for area, cols in _FLUXOS.items():
        values = ", ".join(
            f"(gen_random_uuid()::text, '{name}', '{area}', {pos}, '{color}', true)"
            for (name, pos, color) in cols
        )
        # Só semeia se a área ainda não tem NENHUMA coluna (não duplica, não
        # sobrescreve configuração existente).
        op.execute(f"""
            INSERT INTO kanban_columns (id, name, legal_area, position, color, is_active)
            SELECT * FROM (VALUES {values}) AS v(id, name, legal_area, position, color, is_active)
            WHERE NOT EXISTS (
                SELECT 1 FROM kanban_columns k WHERE k.legal_area = '{area}'
            );
        """)


def downgrade() -> None:
    for area, cols in _FLUXOS.items():
        nomes = ", ".join(f"'{name}'" for (name, _pos, _color) in cols)
        op.execute(
            f"DELETE FROM kanban_columns WHERE legal_area = '{area}' "
            f"AND name IN ({nomes});"
        )
