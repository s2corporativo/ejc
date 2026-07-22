"""114 — consolidar Data Room e Teses v4 nas estruturas canônicas.

Revision ID: 114_consolidar_v4
Revises: 113_calendar_feed_revocation
Create Date: 2026-07-22

A migração é idempotente e não exclui as tabelas de origem. A retirada física
fica condicionada a telemetria sem uso, backup, homologação e rollback próprio.
"""
from alembic import op

revision = "114_consolidar_v4"
down_revision = "113_calendar_feed_revocation"
branch_labels = None
depends_on = None

deployment_policy = "additive_data_backfill"
data_backfill_targets = ("data_rooms", "teses")


def upgrade() -> None:
    op.execute(
        r"""
        DO $$
        BEGIN
            IF to_regclass('public.dataroom_salas') IS NOT NULL
               AND to_regclass('public.data_rooms') IS NOT NULL THEN
                INSERT INTO data_rooms (
                    id, nome, descricao, case_id, client_id, created_by,
                    created_at, updated_at, deleted_at
                )
                SELECT
                    src.id,
                    LEFT(src.nome, 200),
                    CONCAT_WS(
                        E'\n',
                        NULLIF(src.descricao, ''),
                        '[Migrado de Data Room v4]',
                        CASE
                            WHEN src.expira_em IS NOT NULL
                            THEN 'Expiração histórica: ' || src.expira_em::text
                            ELSE NULL
                        END,
                        CASE
                            WHEN COALESCE(src.publica, false)
                            THEN 'A sala era marcada como pública; gere um link canônico para novo acesso.'
                            ELSE NULL
                        END,
                        CASE
                            WHEN src.client_id IS NOT NULL AND cli.id IS NULL
                            THEN 'Vínculo histórico com cliente inexistente: ' || src.client_id
                            ELSE NULL
                        END
                    ),
                    NULL,
                    CASE WHEN cli.id IS NOT NULL THEN src.client_id ELSE NULL END,
                    NULL,
                    COALESCE(src.created_at, now()),
                    now(),
                    NULL
                FROM dataroom_salas src
                LEFT JOIN clients cli ON cli.id = src.client_id
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM data_rooms dst
                    WHERE dst.id = src.id
                       OR (
                            lower(trim(dst.nome)) = lower(trim(LEFT(src.nome, 200)))
                            AND COALESCE(dst.client_id, '') = COALESCE(cli.id, '')
                            AND dst.deleted_at IS NULL
                       )
                );
            END IF;
        END $$;
        """
    )

    op.execute(
        r"""
        DO $$
        BEGIN
            IF to_regclass('public.teses_juridicas_v4') IS NOT NULL
               AND to_regclass('public.teses') IS NOT NULL THEN
                INSERT INTO teses (
                    id, titulo, descricao, fundamentacao, jurisprudencia,
                    contra_argumento, area_juridica, tribunal, magistrado,
                    tags, observacoes, tipo, status,
                    vezes_usada, vezes_venceu, vezes_perdeu, taxa_sucesso,
                    created_by, created_at, updated_at, deleted_at
                )
                SELECT
                    src.id,
                    LEFT(src.titulo, 300),
                    src.descricao,
                    src.fundamentacao,
                    src.jurisprudencia,
                    NULL,
                    LEFT(src.area_juridica, 60),
                    LEFT(src.tribunal, 120),
                    LEFT(src.magistrado, 200),
                    'migrada_v4',
                    CASE
                        WHEN COALESCE(src.vencedora, false)
                        THEN 'Migrada do banco v4; marcada historicamente como vencedora.'
                        ELSE 'Migrada do banco v4.'
                    END,
                    'escritorio'::tesetipo,
                    'ativa'::tesestatus,
                    CASE WHEN COALESCE(src.vencedora, false) THEN 1 ELSE 0 END,
                    CASE WHEN COALESCE(src.vencedora, false) THEN 1 ELSE 0 END,
                    0,
                    src.taxa_sucesso,
                    NULL,
                    COALESCE(src.created_at, now()),
                    now(),
                    NULL
                FROM teses_juridicas_v4 src
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM teses dst
                    WHERE dst.id = src.id
                       OR (
                            lower(trim(dst.titulo)) = lower(trim(LEFT(src.titulo, 300)))
                            AND COALESCE(dst.area_juridica, '') = COALESCE(LEFT(src.area_juridica, 60), '')
                            AND dst.deleted_at IS NULL
                       )
                );
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    pass
