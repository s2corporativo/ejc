"""097 — vw_atividades enriquecida (prioridade + subtipo). Pendência do PR #274.

A Central de Atividades (frontend) fazia 3 chamadas extras (/tasks, /deadlines,
/agenda-eventos) só para obter responsável/prioridade. A view já expunha
responsavel_id (o router descartava); aqui APENAS ACRESCENTAMOS ao final do
SELECT (CREATE OR REPLACE VIEW exige mesma ordem/tipo das colunas existentes):

  - prioridade  TEXT — deadlines.prioridade (enum→text) e tasks.prioridade;
                NULL nas fontes sem o conceito (suspensões, agenda, intimações).
  - subtipo     TEXT — tipo real do evento de agenda (reuniao/audiencia/
                diligencia/compromisso/outro) na perna de agenda_eventos;
                NULL nas demais.

Sem mudança de tabela: agenda_eventos.responsavel_id já existe desde a 053.
Downgrade restaura a definição exata da 053 (DROP + CREATE, pois OR REPLACE
não remove colunas).

Revision ID: 100_vw_atividades_enriquecida
Revises: 096_rag_embedding_1024
"""
from alembic import op

revision = "100_vw_atividades_enriquecida"
down_revision = "099_legal_doc_protocolo"
branch_labels = None
depends_on = None

# Definição anterior (053_reconcile_schema) — usada no downgrade.
_VIEW_053 = """
    CREATE VIEW vw_atividades AS
        SELECT d.id, 'prazo'::text AS tipo, d.titulo, d.descricao,
               d.data_prazo::date AS data, d.status::text AS status,
               d.case_id, d.responsavel_id
        FROM deadlines d WHERE d.deleted_at IS NULL
        UNION ALL
        SELECT t.id, 'tarefa'::text, t.titulo, t.descricao,
               t.data_limite::date, t.status::text, t.case_id, t.responsavel_id
        FROM tasks t WHERE t.deleted_at IS NULL
        UNION ALL
        SELECT s.id, 'suspensao'::text, s.motivo, s.ato_normativo,
               s.data_inicio::date, NULL::text, NULL::varchar(36), s.created_by
        FROM suspensoes_tribunal s WHERE s.deleted_at IS NULL
        UNION ALL
        SELECT a.id, 'agenda'::text, a.titulo, a.descricao,
               a.data_evento::date,
               CASE WHEN a.concluido THEN 'concluido' ELSE 'pendente' END,
               a.case_id, a.responsavel_id
        FROM agenda_eventos a WHERE a.deleted_at IS NULL
        UNION ALL
        SELECT j.id, 'intimacao'::text, j.tipo_comunicacao, j.texto_resumo,
               j.data_disponibilizacao::date,
               CASE WHEN j.processada THEN 'tratada' ELSE 'pendente' END,
               j.case_id, j.advogado_id
        FROM djen_comunicacoes j;
"""


def upgrade() -> None:
    # Colunas novas só no FINAL do SELECT → CREATE OR REPLACE é válido e não
    # derruba dependências. Aditivo: contrato anterior preservado.
    op.execute("""
    CREATE OR REPLACE VIEW vw_atividades AS
        SELECT d.id, 'prazo'::text AS tipo, d.titulo, d.descricao,
               d.data_prazo::date AS data, d.status::text AS status,
               d.case_id, d.responsavel_id,
               d.prioridade::text AS prioridade, NULL::text AS subtipo
        FROM deadlines d WHERE d.deleted_at IS NULL
        UNION ALL
        SELECT t.id, 'tarefa'::text, t.titulo, t.descricao,
               t.data_limite::date, t.status::text, t.case_id, t.responsavel_id,
               t.prioridade::text, NULL::text
        FROM tasks t WHERE t.deleted_at IS NULL
        UNION ALL
        SELECT s.id, 'suspensao'::text, s.motivo, s.ato_normativo,
               s.data_inicio::date, NULL::text, NULL::varchar(36), s.created_by,
               NULL::text, NULL::text
        FROM suspensoes_tribunal s WHERE s.deleted_at IS NULL
        UNION ALL
        SELECT a.id, 'agenda'::text, a.titulo, a.descricao,
               a.data_evento::date,
               CASE WHEN a.concluido THEN 'concluido' ELSE 'pendente' END,
               a.case_id, a.responsavel_id,
               NULL::text, a.tipo::text
        FROM agenda_eventos a WHERE a.deleted_at IS NULL
        UNION ALL
        SELECT j.id, 'intimacao'::text, j.tipo_comunicacao, j.texto_resumo,
               j.data_disponibilizacao::date,
               CASE WHEN j.processada THEN 'tratada' ELSE 'pendente' END,
               j.case_id, j.advogado_id,
               NULL::text, NULL::text
        FROM djen_comunicacoes j;
    """)


def downgrade() -> None:
    # OR REPLACE não remove colunas → DROP + recriação exata da versão 053.
    op.execute("DROP VIEW IF EXISTS vw_atividades;")
    op.execute(_VIEW_053)
