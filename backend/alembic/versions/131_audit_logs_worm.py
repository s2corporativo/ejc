"""Imutabilidade de audit_logs imposta no banco (WORM), não só por convenção.

Issue #699: hoje `audit_logs` é imutável apenas porque `backend/app/routers/audit.py`
só expõe GET e nenhum código faz UPDATE/DELETE sobre a tabela — mas nada no
SCHEMA impede um `db.execute(text(...))` futuro, um acesso direto ao Postgres
ou uma rota nova de "limpar registros de teste" de reescrever a trilha sem
deixar vestígio.

Esta migration cria dois triggers: `BEFORE UPDATE OR DELETE ON audit_logs`
(nível de linha) e `BEFORE TRUNCATE ON audit_logs` (nível de statement,
exigência do Postgres para TRUNCATE) que levantam exceção por padrão. A via
privilegiada de expurgo fica pronta mas INATIVA: nenhum código do
repositório define a GUC de sessão `ejc.audit_logs_permitir_expurgo`, então
todo UPDATE/DELETE/TRUNCATE — de qualquer papel, inclusive superusuário,
salvo desabilitação explícita do trigger — falha. Quando a Issue #582
(purga LGPD com preservação legal) definir a política de retenção, a
rotina de expurgo autorizada poderá abrir a exceção com
`SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'` dentro da própria
transação de purga, sem precisar reabrir este trigger nem tocar em GRANT/REVOKE.

LIMITAÇÃO CONHECIDA (review PR #707, não resolvida nesta migration): a GUC
acima é livremente configurável por qualquer sessão autenticada com a
credencial `ejc_user` — a aplicação e o Alembic compartilham essa mesma
credencial (`DATABASE_URL`/`DATABASE_URL_SYNC`), então SQL cru comprometido
ou uma injeção capaz de emitir múltiplos comandos poderia setar a GUC e em
seguida mutar/apagar a trilha. Restringir o bypass a um papel de banco
separado (ex.: `SET ROLE` para um role dedicado, com `current_user`
verificado na função do trigger) exigiria uma credencial de login distinta
da usada pela aplicação — a app e o Alembic não têm hoje um segundo
segredo/credencial provisionado, e os ~17 arquivos `tests/test_*_dblevel.py`
que limpam fixtures via este mesmo bypass (mesma credencial) precisariam
ser todos migrados para a credencial nova. Isso é uma decisão de
infraestrutura/provisionamento de segredo, fora do alcance desta migration.
Desenho proposto registrado na Issue de continuidade aberta a partir do
review deste PR (ver referência no corpo do PR #707).

Por que trigger e não REVOKE UPDATE/DELETE do papel da aplicação:
- A aplicação e o Alembic usam a MESMA credencial (`DATABASE_URL`/`DATABASE_URL_SYNC`
  apontam pro mesmo papel); um REVOKE bloquearia a app mas exigiria reabrir
  privilégio a cada migration futura que precisasse tocar a tabela (ex.:
  adicionar coluna com backfill), reintroduzindo a janela de risco a cada vez.
- REVOKE não impede um papel com privilégio elevado (dono da tabela,
  superusuário) de simplesmente fazer GRANT de volta antes de mutar — e essa
  concessão não fica registrada como um evento auditável específico da tabela.
- Trigger sobrevive a `pg_restore`: `pg_dump -Fc` (usado por
  `scripts/backup/backup_diario.sh`) inclui funções e triggers do schema por
  padrão; a restauração via `scripts/backup/restaurar_backup.sh`
  (`pg_restore --clean --if-exists --no-owner`) recria a função e o trigger
  junto com a tabela — não depende de reaplicar GRANT/REVOKE separadamente
  nem de rodar a migration de novo (embora `alembic upgrade head` também a
  recrie via CREATE OR REPLACE / CREATE TRIGGER, idempotente).

Revision ID: 131_audit_logs_worm
Revises: 130_ejc_skills_uso
Create Date: 2026-08-04
"""
from alembic import op

revision = "131_audit_logs_worm"
down_revision = "130_ejc_skills_uso"
branch_labels = None
depends_on = None

_FUNCTION = "audit_logs_bloqueia_mutacao"
_TRIGGER = "trg_audit_logs_bloqueia_mutacao"
_FUNCTION_TRUNCATE = "audit_logs_bloqueia_truncate"
_TRIGGER_TRUNCATE = "trg_audit_logs_bloqueia_truncate"
_GUC = "ejc.audit_logs_permitir_expurgo"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF current_setting('{_GUC}', true) IS DISTINCT FROM 'on' THEN
                RAISE EXCEPTION
                    'audit_logs e imutavel (WORM): % bloqueado. '
                    'Via privilegiada de expurgo reservada para rotina auditada '
                    '(Issue #582): SET LOCAL {_GUC} = ''on'' dentro da transacao de purga.',
                    TG_OP;
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_TRIGGER}
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW
        EXECUTE FUNCTION {_FUNCTION}()
        """
    )

    # TRUNCATE não dispara trigger de linha (BEFORE UPDATE OR DELETE acima) —
    # o Postgres exige um trigger dedicado, de nível de STATEMENT, declarado
    # explicitamente para TRUNCATE. Sem isto, `TRUNCATE audit_logs` (mesma
    # credencial dona da tabela) apagaria a trilha inteira contornando o
    # trigger de linha por completo.
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_FUNCTION_TRUNCATE}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF current_setting('{_GUC}', true) IS DISTINCT FROM 'on' THEN
                RAISE EXCEPTION
                    'audit_logs e imutavel (WORM): TRUNCATE bloqueado. '
                    'Via privilegiada de expurgo reservada para rotina auditada '
                    '(Issue #582): SET LOCAL {_GUC} = ''on'' dentro da transacao de purga.';
            END IF;
            RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_TRIGGER_TRUNCATE}
        BEFORE TRUNCATE ON audit_logs
        FOR EACH STATEMENT
        EXECUTE FUNCTION {_FUNCTION_TRUNCATE}()
        """
    )


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER_TRUNCATE} ON audit_logs")
    op.execute(f"DROP FUNCTION IF EXISTS {_FUNCTION_TRUNCATE}()")
    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER} ON audit_logs")
    op.execute(f"DROP FUNCTION IF EXISTS {_FUNCTION}()")
