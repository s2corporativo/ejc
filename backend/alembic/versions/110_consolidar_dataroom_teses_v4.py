"""110 — consolidar Data Room e Teses v4 nas estruturas canônicas.

Revision ID: 110_consolidar_v4
Revises: 109_rag_scope_cliente
Create Date: 2026-07-19

A migração é idempotente, preserva os metadados sem ativar comportamento
inseguro e não exclui as tabelas de origem. A retirada física exige telemetria,
backup e PR próprio.
"""
from alembic import op

revision = "110_consolidar_v4"
down_revision = "109_rag_scope_cliente"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # O nome v4 aceitava 255 caracteres; ampliar o canônico evita truncamento.
    op.execute(
        "ALTER TABLE data_rooms ALTER COLUMN nome TYPE varchar(255)"
    )
    # Metadados transitórios: preservam o contrato antigo, mas NÃO tornam a sala
    # pública nem substituem links canônicos auditáveis e revogáveis.
    op.execute(
        "ALTER TABLE data_rooms ADD COLUMN IF NOT EXISTS legacy_expira_em "
        "timestamp with time zone NULL"
    )
    op.execute(
        "ALTER TABLE data_rooms ADD COLUMN IF NOT EXISTS legacy_publica "
        "boolean NOT NULL DEFAULT false"
    )
    # `vencedora` era um marcador binário, não uma contagem comprovada. Mantê-lo
    # separado evita fabricar vezes_usada/vezes_venceu.
    op.execute(
        "ALTER TABLE teses ADD COLUMN IF NOT EXISTS legacy_vencedora boolean NULL"
    )

    # Atualiza registros canônicos já equivalentes antes do INSERT dos ausentes.
    op.execute(
        r"""
        DO $$
        BEGIN
            IF to_regclass('public.dataroom_salas') IS NOT NULL
               AND to_regclass('public.data_rooms') IS NOT NULL THEN
                WITH source_ranked AS (
                    SELECT src.*,
                           ROW_NUMBER() OVER (
                               PARTITION BY lower(trim(src.nome)), COALESCE(src.client_id, '')
                               ORDER BY src.created_at DESC NULLS LAST, src.id DESC
                           ) AS rn
                    FROM dataroom_salas src
                ), matched AS (
                    SELECT DISTINCT ON (dst.id)
                           dst.id AS dst_id,
                           src.expira_em,
                           COALESCE(src.publica, false) AS publica,
                           src.descricao
                    FROM data_rooms dst
                    JOIN source_ranked src
                      ON src.rn = 1
                     AND (
                          dst.id = src.id
                          OR (
                              lower(trim(dst.nome)) = lower(trim(src.nome))
                              AND COALESCE(dst.client_id, '') = COALESCE(src.client_id, '')
                          )
                     )
                    WHERE dst.deleted_at IS NULL
                    ORDER BY dst.id, (dst.id = src.id) DESC
                )
                UPDATE data_rooms dst
                   SET legacy_expira_em = COALESCE(dst.legacy_expira_em, matched.expira_em),
                       legacy_publica = dst.legacy_publica OR matched.publica,
                       descricao = COALESCE(dst.descricao, matched.descricao),
                       updated_at = now()
                  FROM matched
                 WHERE dst.id = matched.dst_id;

                INSERT INTO data_rooms (
                    id, nome, descricao, case_id, client_id, created_by,
                    created_at, updated_at, deleted_at,
                    legacy_expira_em, legacy_publica
                )
                SELECT
                    src.id,
                    src.nome,
                    CONCAT_WS(
                        E'\n',
                        NULLIF(src.descricao, ''),
                        CASE
                            WHEN src.client_id IS NOT NULL AND cli.id IS NULL
                            THEN '[Migração v4] client_id histórico sem cadastro correspondente: '
                                 || src.client_id
                            ELSE NULL
                        END
                    ),
                    NULL,
                    cli.id,
                    NULL,
                    COALESCE(src.created_at, now()),
                    now(),
                    NULL,
                    src.expira_em,
                    COALESCE(src.publica, false)
                FROM dataroom_salas src
                LEFT JOIN clients cli ON cli.id = src.client_id
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM data_rooms dst
                    WHERE dst.id = src.id
                       OR (
                            lower(trim(dst.nome)) = lower(trim(src.nome))
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
                WITH source_ranked AS (
                    SELECT src.*,
                           ROW_NUMBER() OVER (
                               PARTITION BY lower(trim(src.titulo)),
                                            COALESCE(src.area_juridica, '')
                               ORDER BY src.created_at DESC NULLS LAST, src.id DESC
                           ) AS rn
                    FROM teses_juridicas_v4 src
                ), matched AS (
                    SELECT DISTINCT ON (dst.id)
                           dst.id AS dst_id,
                           src.taxa_sucesso,
                           COALESCE(src.vencedora, false) AS vencedora,
                           src.jurisprudencia,
                           src.fundamentacao
                    FROM teses dst
                    JOIN source_ranked src
                      ON src.rn = 1
                     AND (
                          dst.id = src.id
                          OR (
                              lower(trim(dst.titulo)) = lower(trim(src.titulo))
                              AND COALESCE(dst.area_juridica, '') =
                                  COALESCE(src.area_juridica, '')
                          )
                     )
                    WHERE dst.deleted_at IS NULL
                    ORDER BY dst.id, (dst.id = src.id) DESC
                )
                UPDATE teses dst
                   SET taxa_sucesso = COALESCE(dst.taxa_sucesso, matched.taxa_sucesso),
                       legacy_vencedora = COALESCE(
                           dst.legacy_vencedora, matched.vencedora
                       ),
                       jurisprudencia = COALESCE(dst.jurisprudencia, matched.jurisprudencia),
                       fundamentacao = COALESCE(dst.fundamentacao, matched.fundamentacao),
                       updated_at = now()
                  FROM matched
                 WHERE dst.id = matched.dst_id;

                INSERT INTO teses (
                    id, titulo, descricao, fundamentacao, jurisprudencia,
                    contra_argumento, area_juridica, tribunal, magistrado,
                    tags, observacoes, tipo, status,
                    vezes_usada, vezes_venceu, vezes_perdeu, taxa_sucesso,
                    legacy_vencedora,
                    created_by, created_at, updated_at, deleted_at
                )
                SELECT
                    src.id,
                    src.titulo,
                    src.descricao,
                    src.fundamentacao,
                    src.jurisprudencia,
                    NULL,
                    src.area_juridica,
                    src.tribunal,
                    src.magistrado,
                    'migrada_v4',
                    CASE
                        WHEN COALESCE(src.vencedora, false)
                        THEN 'Migrada do banco v4; marcada historicamente como vencedora.'
                        ELSE 'Migrada do banco v4.'
                    END,
                    'escritorio'::tesetipo,
                    'ativa'::tesestatus,
                    0,
                    0,
                    0,
                    src.taxa_sucesso,
                    COALESCE(src.vencedora, false),
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
                            lower(trim(dst.titulo)) = lower(trim(src.titulo))
                            AND COALESCE(dst.area_juridica, '') =
                                COALESCE(src.area_juridica, '')
                            AND dst.deleted_at IS NULL
                       )
                );
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # Não apaga colunas nem linhas: após o upgrade podem existir salas/teses
    # criadas exclusivamente pelas rotas de compatibilidade. Removê-las no
    # downgrade causaria perda. As tabelas v4 originais permanecem intactas e o
    # rollback de código continua possível.
    pass
