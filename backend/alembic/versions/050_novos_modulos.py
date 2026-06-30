"""050 — novos modulos: pricing_rules, inadimplencia_alerts, case_ambiental, due_diligence_templates, document_access_log + cofre columns em documents

Revision ID: 050_novos_modulos
Revises: 049_totp_2fa
Create Date: 2026-06-25
"""

from alembic import op
import sqlalchemy as sa
import json as _json

revision = "050_novos_modulos"
down_revision = "049_totp_2fa"
branch_labels = None
depends_on = None


def upgrade():
    # ── 1. pricing_rules — Motor de precificação OAB ───────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS pricing_rules (
        id             VARCHAR(36)   PRIMARY KEY DEFAULT gen_random_uuid()::text,
        area           VARCHAR(100)  NOT NULL,
        case_type      VARCHAR(150)  NOT NULL,
        complexity     VARCHAR(30)   NOT NULL DEFAULT 'media'
                         CHECK (complexity IN ('simples','media','alta','muito_alta')),
        fee_type       VARCHAR(50)   NOT NULL DEFAULT 'fixo'
                         CHECK (fee_type IN ('fixo','percentual','misto','exito')),
        base_amount    NUMERIC(12,2),
        percentage_of_value NUMERIC(5,2),
        min_amount     NUMERIC(12,2),
        max_amount     NUMERIC(12,2),
        exit_percentage NUMERIC(5,2),
        oab_reference  TEXT,
        notes          TEXT,
        is_active      BOOLEAN       NOT NULL DEFAULT TRUE,
        created_by     VARCHAR(36),
        created_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
        updated_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW()
    )
    """)

    # Seed OAB/MG — 10 faixas de referência (valores médios praticados)
    op.execute("""
    INSERT INTO pricing_rules
        (id, area, case_type, complexity, fee_type, base_amount, percentage_of_value,
         min_amount, max_amount, exit_percentage, oab_reference, notes)
    SELECT * FROM (VALUES
        (gen_random_uuid()::text,
         'trabalhista','Reclamatória Trabalhista Simples','simples','misto',
         2500.00,20.00,1500.00,15000.00,30.00,
         'Tabela OAB/MG 2024 — Anexo III — item 1.1',
         'Honorários contratuais + 30%% em caso de êxito sobre valores recebidos'),
        (gen_random_uuid()::text,
         'trabalhista','Reclamatória Trabalhista Complexa','alta','misto',
         6000.00,25.00,4000.00,50000.00,35.00,
         'Tabela OAB/MG 2024 — Anexo III — item 1.2',
         'Causas com assédio, acidente ou múltiplas verbas'),
        (gen_random_uuid()::text,
         'consumidor','Ação Indenizatória CDC','simples','misto',
         3000.00,20.00,2000.00,20000.00,30.00,
         'Tabela OAB/MG 2024 — Anexo I — item 2.1',
         NULL),
        (gen_random_uuid()::text,
         'civil','Ação Civil Genérica','media','fixo',
         5000.00,NULL,3000.00,NULL,NULL,
         'Tabela OAB/MG 2024 — Anexo I — item 3.1',
         'Contencioso cível de valor moderado'),
        (gen_random_uuid()::text,
         'civil','Ação de Cobrança/Execução','media','misto',
         2000.00,15.00,1500.00,30000.00,20.00,
         'Tabela OAB/MG 2024 — Anexo I — item 3.3',
         NULL),
        (gen_random_uuid()::text,
         'penal','Defesa Criminal Simples (JECrim/Rito Sumário)','simples','fixo',
         4000.00,NULL,3000.00,NULL,NULL,
         'Tabela OAB/MG 2024 — Anexo II — item 1.1',
         NULL),
        (gen_random_uuid()::text,
         'penal','Defesa Criminal Complexa (Júri/Crimes Hediondos)','muito_alta','fixo',
         15000.00,NULL,10000.00,NULL,NULL,
         'Tabela OAB/MG 2024 — Anexo II — item 1.4',
         NULL),
        (gen_random_uuid()::text,
         'empresarial','Consultoria/Elaboração Contratual','simples','fixo',
         2500.00,NULL,1500.00,NULL,NULL,
         'Tabela OAB/MG 2024 — Anexo IV — item 1',
         'Por contrato elaborado ou revisado'),
        (gen_random_uuid()::text,
         'tributario','Defesa Administrativa Fiscal','media','misto',
         4000.00,10.00,2500.00,40000.00,NULL,
         'Tabela OAB/MG 2024 — Anexo V — item 2',
         NULL),
        (gen_random_uuid()::text,
         'ambiental','Defesa em Auto de Infração Ambiental','alta','misto',
         5000.00,12.00,3000.00,50000.00,NULL,
         'Tabela OAB/MG 2024 — Anexo VI — item 1',
         'IBAMA/IEF/SEMAD — inclui acompanhamento de prazo de defesa')
    ) AS t(id,area,case_type,complexity,fee_type,base_amount,percentage_of_value,
           min_amount,max_amount,exit_percentage,oab_reference,notes)
    WHERE NOT EXISTS (SELECT 1 FROM pricing_rules LIMIT 1)
    """)

    # ── 2. inadimplencia_alerts — Controle de inadimplência por honorários ──────
    op.execute("""
    CREATE TABLE IF NOT EXISTS inadimplencia_alerts (
        id             VARCHAR(36)   PRIMARY KEY DEFAULT gen_random_uuid()::text,
        fee_id         VARCHAR(36)   NOT NULL REFERENCES fees(id) ON DELETE CASCADE,
        case_id        VARCHAR(36)   REFERENCES cases(id) ON DELETE SET NULL,
        client_id      VARCHAR(36)   REFERENCES clients(id) ON DELETE SET NULL,
        days_overdue   INTEGER       NOT NULL DEFAULT 0,
        amount_due     NUMERIC(12,2) NOT NULL,
        alert_level    VARCHAR(30)   NOT NULL DEFAULT 'leve'
                         CHECK (alert_level IN ('leve','medio','critico','cobranca_formal')),
        action_taken   TEXT,
        resolved       BOOLEAN       NOT NULL DEFAULT FALSE,
        resolved_at    TIMESTAMPTZ,
        created_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
        updated_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW()
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_inadimplencia_fee_id ON inadimplencia_alerts(fee_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_inadimplencia_client_id ON inadimplencia_alerts(client_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_inadimplencia_resolved ON inadimplencia_alerts(resolved)")

    # ── 3. case_ambiental — Módulo Ambiental (IBAMA, CAR, TCFA, carbono) ────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS case_ambiental (
        id                   VARCHAR(36)   PRIMARY KEY DEFAULT gen_random_uuid()::text,
        case_id              VARCHAR(36)   NOT NULL UNIQUE REFERENCES cases(id) ON DELETE CASCADE,
        subtype              VARCHAR(80),
        -- Auto de Infração
        numero_auto          VARCHAR(100),
        orgao_autuador       VARCHAR(100),
        data_auto            DATE,
        prazo_defesa         DATE,
        valor_multa          NUMERIC(14,2),
        infracoes            JSONB         NOT NULL DEFAULT '[]',
        -- Licenciamento
        licenca_tipo         VARCHAR(80),
        licenca_numero       VARCHAR(100),
        licenca_validade     DATE,
        licenca_orgao        VARCHAR(100),
        -- CAR / Reserva Legal
        car_numero           VARCHAR(100),
        reserva_legal_ha     NUMERIC(10,4),
        app_area_ha          NUMERIC(10,4),
        -- TCFA
        tcfa_cnpj            VARCHAR(20),
        tcfa_atividade       VARCHAR(200),
        tcfa_vencimento      DATE,
        tcfa_valor           NUMERIC(12,2),
        -- Crédito de Carbono
        credito_carbono_ton  NUMERIC(12,4),
        -- Observações
        observacoes          TEXT,
        created_at           TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
        updated_at           TIMESTAMPTZ   NOT NULL DEFAULT NOW()
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_case_ambiental_case_id ON case_ambiental(case_id)")

    # ── 4. due_diligence_templates — Templates de Due Diligence ─────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS due_diligence_templates (
        id          VARCHAR(36)   PRIMARY KEY DEFAULT gen_random_uuid()::text,
        name        VARCHAR(200)  NOT NULL,
        dd_type     VARCHAR(100)  NOT NULL,
        items       JSONB         NOT NULL DEFAULT '[]',
        is_active   BOOLEAN       NOT NULL DEFAULT TRUE,
        created_by  VARCHAR(36)   REFERENCES users(id) ON DELETE SET NULL,
        created_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
        updated_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW()
    )
    """)

    # Seed — 3 templates (via Python params para evitar conflito com bind params SQLAlchemy)
    conn = op.get_bind()
    _dd_seeds = [
        {
            "name": "DD Societária — M&A",
            "dd_type": "societaria",
            "items": [
                {"item": "Contrato/Estatuto Social atualizado", "obrigatorio": True},
                {"item": "Certidões negativas CNPJ (RFB, FGTS, INSS)", "obrigatorio": True},
                {"item": "Balanço patrimonial 3 últimos exercícios", "obrigatorio": True},
                {"item": "Atas de eleição de diretores/sócios", "obrigatorio": True},
                {"item": "Livros societários digitalizados", "obrigatorio": False},
                {"item": "Contratos relevantes em vigor", "obrigatorio": True},
                {"item": "Passivo trabalhista — certidão TST/TRT", "obrigatorio": True},
                {"item": "Passivo tributário — PGFN/estadual/municipal", "obrigatorio": True},
                {"item": "Licenças ambientais vigentes", "obrigatorio": False},
            ],
        },
        {
            "name": "DD Imobiliária — Compra de Imóvel",
            "dd_type": "imobiliaria",
            "items": [
                {"item": "Matrícula atualizada (30 dias)", "obrigatorio": True},
                {"item": "Certidão de ônus reais", "obrigatorio": True},
                {"item": "IPTU — quitação dos últimos 5 anos", "obrigatorio": True},
                {"item": "Habite-se / Alvará de Construção", "obrigatorio": False},
                {"item": "CAR — Cadastro Ambiental Rural (zona rural)", "obrigatorio": False},
                {"item": "Certidões pessoais dos vendedores (TJ, TRF, TRT)", "obrigatorio": True},
                {"item": "CCIR / ITR atualizados (zona rural)", "obrigatorio": False},
            ],
        },
        {
            "name": "DD Trabalhista — Terceirização/Tomador",
            "dd_type": "trabalhista",
            "items": [
                {"item": "CNPJ regular — Receita Federal", "obrigatorio": True},
                {"item": "Certidão negativa INSS/FGTS da prestadora", "obrigatorio": True},
                {"item": "Contrato social e alterações", "obrigatorio": True},
                {"item": "Reclamações trabalhistas ativas (CSJT/TRT)", "obrigatorio": True},
                {"item": "Folha de pagamento 3 meses", "obrigatorio": False},
                {"item": "Programa de Gerenciamento de Riscos (PGR/PCMSO)", "obrigatorio": False},
                {"item": "Apólice de seguro de responsabilidade civil", "obrigatorio": False},
            ],
        },
    ]
    for _seed in _dd_seeds:
        conn.execute(sa.text(
            "INSERT INTO due_diligence_templates (id, name, dd_type, items) "
            "SELECT gen_random_uuid()::text, :name, :dd_type, CAST(:items AS jsonb) "
            "WHERE NOT EXISTS (SELECT 1 FROM due_diligence_templates WHERE dd_type = :dd_type)"
        ), {"name": _seed["name"], "dd_type": _seed["dd_type"],
            "items": _json.dumps(_seed["items"], ensure_ascii=False)})

    # ── 5. document_access_log — Log de acesso ao cofre ─────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS document_access_log (
        id          VARCHAR(36)   PRIMARY KEY DEFAULT gen_random_uuid()::text,
        document_id VARCHAR(36)   NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        user_id     VARCHAR(36)   NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        action      VARCHAR(30)   NOT NULL DEFAULT 'view'
                      CHECK (action IN ('view','download','print','share','delete')),
        ip_address  VARCHAR(45),
        user_agent  TEXT,
        created_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW()
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_doc_access_doc_id ON document_access_log(document_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_doc_access_user_id ON document_access_log(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_doc_access_created ON document_access_log(created_at)")

    # ── 6. ALTER TABLE documents — colunas cofre (idempotente) ──────────────────
    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='documents' AND column_name='sensitivity_level'
        ) THEN
            ALTER TABLE documents ADD COLUMN sensitivity_level VARCHAR(20)
                NOT NULL DEFAULT 'normal'
                CHECK (sensitivity_level IN ('publico','normal','confidencial','secreto'));
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='documents' AND column_name='access_users'
        ) THEN
            ALTER TABLE documents ADD COLUMN access_users JSONB NOT NULL DEFAULT '[]';
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='documents' AND column_name='watermark'
        ) THEN
            ALTER TABLE documents ADD COLUMN watermark VARCHAR(200);
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='documents' AND column_name='download_count'
        ) THEN
            ALTER TABLE documents ADD COLUMN download_count INTEGER NOT NULL DEFAULT 0;
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='documents' AND column_name='last_accessed_at'
        ) THEN
            ALTER TABLE documents ADD COLUMN last_accessed_at TIMESTAMPTZ;
        END IF;
    END $$
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS document_access_log CASCADE")
    op.execute("DROP TABLE IF EXISTS due_diligence_templates CASCADE")
    op.execute("DROP TABLE IF EXISTS case_ambiental CASCADE")
    op.execute("DROP TABLE IF EXISTS inadimplencia_alerts CASCADE")
    op.execute("DROP TABLE IF EXISTS pricing_rules CASCADE")
    op.execute("""
    ALTER TABLE documents
        DROP COLUMN IF EXISTS sensitivity_level,
        DROP COLUMN IF EXISTS access_users,
        DROP COLUMN IF EXISTS watermark,
        DROP COLUMN IF EXISTS download_count,
        DROP COLUMN IF EXISTS last_accessed_at
    """)
