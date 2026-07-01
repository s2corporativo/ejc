"""053 — reconciliação de schema (P0-4 da auditoria 28/06/2026)

Cria, de forma 100% IDEMPOTENTE (IF NOT EXISTS), as tabelas/colunas que o
código consulta mas que NUNCA tiveram migration — por isso só existiam em
produção (criadas fora do Alembic, a partir do working tree sujo). Sem esta
migration um banco limpo (rebuild / restore / DR) quebra com UndefinedTable.

Tabelas ORM-mapeadas sem create:   caso_areas, bank_analyses, bank_transactions,
                                    bank_abusive_charges
Colunas do model Case sem migration: 9 colunas (sync_*, kanban_*, case_type, ...)
Tabelas só em SQL cru sem create:   kanban_columns, areas, agenda_eventos,
                                    client_pending_items, domain_events,
                                    office_contracts, office_expenses,
                                    partner_withdrawals
View:                               vw_atividades

Idempotente: seguro rodar na prod (tabelas já existem → no-op) e em banco limpo.
Reversível: o downgrade NÃO dropa nada (evita perda de dados em prod). Para um
banco limpo, basta não aplicar a migration.

Revision ID: 053_reconcile_schema
Revises: 052_workflow_tables
Create Date: 2026-06-28
"""
from alembic import op

revision = "053_reconcile_schema"
down_revision = "052_workflow_tables"
branch_labels = None
depends_on = None


def upgrade():
    # ── 1. caso_areas (model CasoArea — consultada em cases.py / rentabilidade) ──
    op.execute("""
    CREATE TABLE IF NOT EXISTS caso_areas (
        id         VARCHAR(36)  PRIMARY KEY DEFAULT gen_random_uuid()::text,
        case_id    VARCHAR(36)  NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
        area       VARCHAR(40)  NOT NULL,
        principal  BOOLEAN      NOT NULL DEFAULT FALSE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_caso_areas_case ON caso_areas (case_id);")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_caso_areas_case_area ON caso_areas (case_id, area);")

    # ── 2. Módulo Análise Bancária (models BankAnalysis/Transaction/AbusiveCharge) ──
    op.execute("""
    CREATE TABLE IF NOT EXISTS bank_analyses (
        id               VARCHAR(36)  PRIMARY KEY DEFAULT gen_random_uuid()::text,
        case_id          VARCHAR(36),
        client_id        VARCHAR(36),
        banco            VARCHAR(60),
        formato          VARCHAR(10),
        arquivo_nome     VARCHAR(255),
        periodo_inicio   DATE,
        periodo_fim      DATE,
        total_transacoes INTEGER       DEFAULT 0,
        total_creditos   NUMERIC(14,2) DEFAULT 0,
        total_debitos    NUMERIC(14,2) DEFAULT 0,
        total_abusivo    NUMERIC(14,2) DEFAULT 0,
        qtd_abusivas     INTEGER       DEFAULT 0,
        status           VARCHAR(20)   DEFAULT 'processando',
        erro             TEXT,
        created_by       VARCHAR(36),
        created_at       TIMESTAMP WITH TIME ZONE DEFAULT now(),
        deleted_at       TIMESTAMP WITH TIME ZONE
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_bank_analyses_case ON bank_analyses (case_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_bank_analyses_client ON bank_analyses (client_id);")

    op.execute("""
    CREATE TABLE IF NOT EXISTS bank_transactions (
        id          VARCHAR(36)  PRIMARY KEY DEFAULT gen_random_uuid()::text,
        analysis_id VARCHAR(36)  NOT NULL,
        data        DATE,
        descricao   VARCHAR(500),
        valor       NUMERIC(14,2),
        tipo        VARCHAR(10),
        saldo       NUMERIC(14,2),
        created_at  TIMESTAMP WITH TIME ZONE DEFAULT now()
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_bank_transactions_analysis ON bank_transactions (analysis_id);")

    op.execute("""
    CREATE TABLE IF NOT EXISTS bank_abusive_charges (
        id             VARCHAR(36)  PRIMARY KEY DEFAULT gen_random_uuid()::text,
        analysis_id    VARCHAR(36)  NOT NULL,
        transaction_id VARCHAR(36),
        regra          VARCHAR(40),
        titulo         VARCHAR(200),
        descricao      TEXT,
        base_legal     VARCHAR(255),
        prioridade     VARCHAR(10),
        valor          NUMERIC(14,2),
        created_at     TIMESTAMP WITH TIME ZONE DEFAULT now()
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_bank_abusive_analysis ON bank_abusive_charges (analysis_id);")

    # ── 3. Colunas faltantes do model Case (sync, kanban, conversão judicial) ──
    op.execute("""
    ALTER TABLE cases
        ADD COLUMN IF NOT EXISTS last_synced_at          TIMESTAMP WITH TIME ZONE,
        ADD COLUMN IF NOT EXISTS sync_pending            BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS sync_error              TEXT,
        ADD COLUMN IF NOT EXISTS case_type               VARCHAR(50) DEFAULT 'judicial',
        ADD COLUMN IF NOT EXISTS extrajudicial_type      VARCHAR(50),
        ADD COLUMN IF NOT EXISTS has_judicial_process    BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS kanban_column           VARCHAR(100),
        ADD COLUMN IF NOT EXISTS kanban_position         INTEGER,
        ADD COLUMN IF NOT EXISTS linked_judicial_case_id VARCHAR(36);
    """)

    # ── 4. kanban_columns (SQL cru: kanban.py, cases.py, case_automacao.py) ──
    op.execute("""
    CREATE TABLE IF NOT EXISTS kanban_columns (
        id         VARCHAR(36)  PRIMARY KEY DEFAULT gen_random_uuid()::text,
        name       VARCHAR(120) NOT NULL,
        legal_area VARCHAR(60)  NOT NULL DEFAULT 'default',
        position   INTEGER      NOT NULL DEFAULT 0,
        color      VARCHAR(20),
        icon       VARCHAR(40),
        is_active  BOOLEAN      NOT NULL DEFAULT TRUE
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_kanban_columns_area_active_pos ON kanban_columns (legal_area, is_active, position);")

    # ── 5. areas (SQL cru: areas.py — slug é a PK natural) ──
    op.execute("""
    CREATE TABLE IF NOT EXISTS areas (
        slug  VARCHAR(60)  PRIMARY KEY,
        nome  VARCHAR(120) NOT NULL,
        ordem INTEGER      NOT NULL DEFAULT 0,
        ativo BOOLEAN      NOT NULL DEFAULT TRUE
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_areas_ativo_ordem ON areas (ativo, ordem);")

    # ── 6. agenda_eventos (SQL cru: agenda_eventos.py) ──
    op.execute("""
    CREATE TABLE IF NOT EXISTS agenda_eventos (
        id             VARCHAR(36)  PRIMARY KEY DEFAULT gen_random_uuid()::text,
        titulo         VARCHAR(255) NOT NULL,
        tipo           VARCHAR(40)  NOT NULL DEFAULT 'compromisso',
        data_evento    DATE         NOT NULL,
        hora           VARCHAR(10),
        local          VARCHAR(255),
        descricao      TEXT,
        case_id        VARCHAR(36)  REFERENCES cases(id) ON DELETE SET NULL,
        responsavel_id VARCHAR(36),
        concluido      BOOLEAN      NOT NULL DEFAULT FALSE,
        created_by     VARCHAR(36),
        created_at     TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
        updated_at     TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
        deleted_at     TIMESTAMP WITH TIME ZONE
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_agenda_eventos_data ON agenda_eventos (data_evento, hora);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_agenda_eventos_case ON agenda_eventos (case_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_agenda_eventos_deleted ON agenda_eventos (deleted_at);")

    # ── 7. client_pending_items (SQL cru: pending_items.py) ──
    op.execute("""
    CREATE TABLE IF NOT EXISTS client_pending_items (
        id           VARCHAR(36)  PRIMARY KEY DEFAULT gen_random_uuid()::text,
        client_id    VARCHAR(36)  NOT NULL,
        case_id      VARCHAR(36),
        type         VARCHAR(40)  NOT NULL DEFAULT 'documento',
        title        VARCHAR(255) NOT NULL,
        description  TEXT,
        status       VARCHAR(40)  NOT NULL DEFAULT 'pendente',
        due_date     DATE,
        created_by   VARCHAR(36),
        completed_at TIMESTAMP WITH TIME ZONE,
        created_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
        updated_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
        deleted_at   TIMESTAMP WITH TIME ZONE
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_client_pending_items_client ON client_pending_items (client_id, status);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_client_pending_items_deleted ON client_pending_items (deleted_at);")

    # ── 8. domain_events (outbox: event_bus.py) ──
    op.execute("""
    CREATE TABLE IF NOT EXISTS domain_events (
        id          VARCHAR(36)  PRIMARY KEY,
        tipo        VARCHAR(80)  NOT NULL,
        entidade    VARCHAR(60)  NOT NULL,
        entidade_id VARCHAR(36)  NOT NULL,
        payload     JSONB        NOT NULL DEFAULT '{}'::jsonb,
        usuario_id  VARCHAR(36),
        created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_domain_events_tipo ON domain_events (tipo);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_domain_events_entidade ON domain_events (entidade, entidade_id);")

    # ── 9. office_contracts (SQL cru: office_contracts.py) ──
    op.execute("""
    CREATE TABLE IF NOT EXISTS office_contracts (
        id                VARCHAR(36)  PRIMARY KEY DEFAULT gen_random_uuid()::text,
        title             VARCHAR(255) NOT NULL,
        counterparty      VARCHAR(255) NOT NULL,
        contract_type     VARCHAR(60)  NOT NULL DEFAULT 'prestacao_servico',
        status            VARCHAR(40)  NOT NULL DEFAULT 'vigente',
        start_date        DATE         NOT NULL,
        end_date          DATE,
        value             NUMERIC(14,2),
        description       TEXT,
        file_url          TEXT,
        alert_days_before INTEGER      NOT NULL DEFAULT 30,
        created_by        VARCHAR(36),
        created_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
        updated_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
        deleted_at        TIMESTAMP WITH TIME ZONE
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_office_contracts_status ON office_contracts (status, end_date);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_office_contracts_deleted ON office_contracts (deleted_at);")

    # ── 10. office_expenses (SQL cru: despesas.py) ──
    op.execute("""
    CREATE TABLE IF NOT EXISTS office_expenses (
        id           VARCHAR(36)   PRIMARY KEY DEFAULT gen_random_uuid()::text,
        categoria    VARCHAR(80)   NOT NULL,
        subcategoria VARCHAR(80),
        tipo         VARCHAR(20)   NOT NULL DEFAULT 'fixo',
        descricao    TEXT          NOT NULL,
        valor        NUMERIC(14,2) NOT NULL DEFAULT 0,
        vencimento   DATE,
        pago_em      DATE,
        recorrente   BOOLEAN       NOT NULL DEFAULT FALSE,
        recorrencia  VARCHAR(40),
        status       VARCHAR(20)   NOT NULL DEFAULT 'pendente',
        competencia  VARCHAR(7),
        created_by   VARCHAR(36),
        created_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
        updated_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
        deleted_at   TIMESTAMP WITH TIME ZONE
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_office_expenses_filters ON office_expenses (categoria, tipo, status, competencia);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_office_expenses_deleted ON office_expenses (deleted_at);")

    # ── 11. partner_withdrawals (SQL cru: partner_withdrawals.py) ──
    op.execute("""
    CREATE TABLE IF NOT EXISTS partner_withdrawals (
        id               VARCHAR(36)   PRIMARY KEY DEFAULT gen_random_uuid()::text,
        partner_id       VARCHAR(36)   NOT NULL,
        gross_value      NUMERIC(14,2) NOT NULL,
        case_expenses    NUMERIC(14,2) NOT NULL DEFAULT 0,
        net_value        NUMERIC(14,2),
        partner_share    NUMERIC(14,2),
        description      TEXT,
        period_reference VARCHAR(40),
        status           VARCHAR(20)   NOT NULL DEFAULT 'pendente',
        approved_by      VARCHAR(36),
        approved_at      TIMESTAMP WITH TIME ZONE,
        paid_at          TIMESTAMP WITH TIME ZONE,
        created_at       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
        updated_at       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
        deleted_at       TIMESTAMP WITH TIME ZONE
    );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_partner_withdrawals_partner ON partner_withdrawals (partner_id, status);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_partner_withdrawals_deleted ON partner_withdrawals (deleted_at);")

    # ── 12. View vw_atividades (atividades.py) — agrega prazos/tarefas/suspensões/
    #        agenda/intimações. CREATE OR REPLACE é idempotente. Depende de
    #        agenda_eventos (criada acima) + tabelas já existentes.
    op.execute("""
    DROP VIEW IF EXISTS vw_atividades;
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
    """)


def downgrade():
    # NÃO dropar tabelas/colunas: em produção elas contêm dados reais criados
    # fora do Alembic. Downgrade é intencionalmente um no-op seguro (apenas a
    # view pode ser removida sem perda de dados).
    op.execute("DROP VIEW IF EXISTS vw_atividades;")
