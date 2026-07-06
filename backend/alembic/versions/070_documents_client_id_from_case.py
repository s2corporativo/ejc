"""070_documents_client_id_from_case — vincula documentos ao cliente do caso

Revision ID: 070_documents_client_id_from_case
Revises: 069_api_keys
Create Date: 2026-07-06

Garante na camada de banco que documentos com case_id usem sempre o client_id
canônico do próprio caso. Isso evita divergência entre case_id e client_id vinda
de formulário, importação ou integração futura.
"""
from alembic import op

revision = "070_documents_client_id_from_case"
down_revision = "069_api_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION sync_document_client_id_from_case()
        RETURNS trigger AS $$
        DECLARE
            case_client_id VARCHAR(36);
        BEGIN
            IF NEW.case_id IS NULL THEN
                RETURN NEW;
            END IF;

            SELECT c.client_id
              INTO case_client_id
              FROM cases c
             WHERE c.id = NEW.case_id
               AND c.deleted_at IS NULL
             LIMIT 1;

            IF NOT FOUND THEN
                RAISE EXCEPTION 'Caso % não encontrado para vincular documento', NEW.case_id;
            END IF;

            NEW.client_id := case_client_id;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        DROP TRIGGER IF EXISTS trg_documents_client_id_from_case ON documents;
    """)
    op.execute("""
        CREATE TRIGGER trg_documents_client_id_from_case
        BEFORE INSERT OR UPDATE OF case_id, client_id ON documents
        FOR EACH ROW
        EXECUTE FUNCTION sync_document_client_id_from_case();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_documents_client_id_from_case ON documents")
    op.execute("DROP FUNCTION IF EXISTS sync_document_client_id_from_case()")
