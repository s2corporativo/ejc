"""Remove 'ollama' do CHECK constraint de engine em ejc_skills.

Issue #761 (pedido do titular): remoção completa do provider Ollama local do
sistema. A engenharia do provider em si (`services/providers/ollama_provider.py`,
flags `OLLAMA_*` de `core/config.py`, referências em `services/ai_gateway.py`)
é escopo de outra frente, em paralelo. Esta migration cobre só a ponta de
schema: o CHECK constraint criado em `051_ejc_skills.py`
(`CHECK (engine IN ('anthropic','groq','ollama'))`, sem nome explícito — o
Postgres deu o nome padrão `ejc_skills_engine_check` por ser o único CHECK
inline da coluna) e as 3 linhas seedadas com `engine='ollama'`
(resumidor-audiencias, humanizador-juridico, gestor-checklists-acoes — ver
`app/seeds/skills_seed.py`, ajustado no mesmo PR para semear `engine='groq'`
daqui pra frente).

Ordem importa: o UPDATE de dados roda ANTES de trocar o CHECK constraint —
o Postgres valida o CHECK novo contra as linhas existentes no momento do
ALTER, e uma linha ainda com `engine='ollama'` faria o ALTER falhar.

LIMITAÇÃO CONHECIDA (aceita, não é perda de dado essencial): o downgrade
recoloca `'ollama'` como valor permitido no CHECK, mas NÃO tenta reverter
`engine='groq'` para `'ollama'` nas linhas afetadas pelo upgrade — depois do
UPDATE não há como distinguir, só pela coluna, uma linha que já era
`engine='groq'` antes desta migration de uma que virou `'groq'` por causa
dela. Reverter às cegas trocaria skills que nunca foram Ollama. Ollama está
saindo do sistema por decisão de produto (Issue #761); o cenário em que
faria sentido restaurar `'ollama'` como engine ativo de alguma skill não
existe mais.

Revision ID: 132_ai_skills_rm_engine_ollama
Revises: 131_audit_logs_worm
Create Date: 2026-08-07

Nota sobre o revision id: encurtado de "132_ai_skills_remover_engine_ollama"
(35 caracteres) para "132_ai_skills_rm_engine_ollama" (30 caracteres) porque
`alembic_version.version_num` é `VARCHAR(32)` — o id original estourava a
coluna e derrubava `alembic upgrade head` em qualquer banco limpo (achado do
agente verifier em 2026-08-07). Renomeado antes de qualquer merge, sem
migration aplicada em produção a preservar.
"""
from alembic import op

revision = "132_ai_skills_rm_engine_ollama"
down_revision = "131_audit_logs_worm"
branch_labels = None
depends_on = None

_CONSTRAINT = "ejc_skills_engine_check"


def upgrade() -> None:
    # 1) Dados primeiro: sem isto o ALTER TABLE abaixo falha com
    #    "check constraint is violated by some row" nas 3 skills seedadas
    #    com engine='ollama' (resumidor-audiencias, humanizador-juridico,
    #    gestor-checklists-acoes).
    op.execute("UPDATE ejc_skills SET engine = 'groq' WHERE engine = 'ollama'")

    # 2) Constraint depois: troca o CHECK para não aceitar mais 'ollama'.
    op.execute(f"ALTER TABLE ejc_skills DROP CONSTRAINT IF EXISTS {_CONSTRAINT}")
    op.execute(
        f"ALTER TABLE ejc_skills ADD CONSTRAINT {_CONSTRAINT} "
        "CHECK (engine IN ('anthropic','groq'))"
    )


def downgrade() -> None:
    # Só o constraint volta a aceitar 'ollama'. Os dados NÃO são revertidos
    # (ver docstring — não é possível saber, só pela coluna, quais linhas
    # eram originalmente 'ollama' vs. 'groq' nativo).
    op.execute(f"ALTER TABLE ejc_skills DROP CONSTRAINT IF EXISTS {_CONSTRAINT}")
    op.execute(
        f"ALTER TABLE ejc_skills ADD CONSTRAINT {_CONSTRAINT} "
        "CHECK (engine IN ('anthropic','groq','ollama'))"
    )
