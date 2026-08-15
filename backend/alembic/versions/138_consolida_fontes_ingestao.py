"""138 — Consolida fontes de ingestão duplicadas (Onda 2 — Refatoração Total).

Problema: a trilha agendada (scheduler) grava as fontes de jurisprudência com
os slugs `stj`/`tjmg`/`lexml`, enquanto a trilha on-demand (juris_import)
gravava `juris_import_stj`/`juris_import_tjmg`/`juris_import_lexml`. São a
MESMA fonte — mesmos ingestores/keyspace de dedup — com métricas separadas.

A migration consolida os valores nas linhas canônicas sem apagar histórico:

* se só existir `juris_import_*`, a linha é renomeada para o slug canônico;
* se as duas existirem, métricas são mescladas na canônica;
* a linha antiga é preservada como `legacy_138_juris_import_*`, inativa, para
  auditoria e rollback lógico. O painel ignora apenas esse prefixo técnico.

A escolha de preservar a linha antiga substitui o DELETE da versão inicial da
migration. Isso permite que a esteira automática mantenha a política
`additive_data_backfill`: rollback de imagem nunca precisa reconstruir dado
apagado. Reexecutar a migration é no-op para as linhas já renomeadas/arquivadas.

O merge mantém:
  * contadores somados;
  * `ja_produziu` e `ativo` por OR lógico;
  * timestamp/status/erro/sequência de zeradas da execução mais recente.

`downgrade()` permanece no-op: a consolidação dos contadores é irreversível sem
um snapshot anterior, embora as linhas legadas sejam preservadas para auditoria.
"""
from __future__ import annotations

from datetime import datetime, timezone

from alembic import op

revision = "138_consolida_fontes_ingestao"
down_revision = "136_document_publicacao_portal"
branch_labels = None
depends_on = None

# Backfill estritamente aditivo/não destrutivo. O classificador do deploy
# permite UPDATE com WHERE e target declarado, mas continua recusando DELETE.
deployment_policy = "additive_data_backfill"
data_backfill_targets = ("fontes_ingestao",)

#: Mantido como especificação testável da regra usada pelos UPDATEs SQL.
FONTES_DUPLICADAS = ("stj", "tjmg", "lexml")
LEGACY_PREFIX = "legacy_138_"


def _aware(dt):
    """Timestamp comparável: naive é assumido UTC; aceita ISO string em testes."""
    if dt is None:
        return None
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def mesclar_fontes(origem: dict, destino: dict) -> dict:
    """Especificação pura da regra de merge aplicada pelo SQL da migration."""
    exec_origem = _aware(origem.get("ultima_execucao"))
    exec_destino = _aware(destino.get("ultima_execucao"))
    if exec_origem is not None and (exec_destino is None or exec_origem > exec_destino):
        recente = origem
        ultima_execucao = origem.get("ultima_execucao")
    else:
        recente = destino
        ultima_execucao = destino.get("ultima_execucao")
    return {
        "ultima_execucao": ultima_execucao,
        "ultimo_status": recente.get("ultimo_status"),
        "ultimo_erro": recente.get("ultimo_erro"),
        "execucoes_zeradas_consecutivas": int(
            recente.get("execucoes_zeradas_consecutivas") or 0
        ),
        "registros_novos": int(origem.get("registros_novos") or 0)
        + int(destino.get("registros_novos") or 0),
        "registros_total": int(origem.get("registros_total") or 0)
        + int(destino.get("registros_total") or 0),
        "ja_produziu": bool(origem.get("ja_produziu")) or bool(destino.get("ja_produziu")),
        "ativo": bool(origem.get("ativo")) or bool(destino.get("ativo")),
    }


def upgrade() -> None:
    # STJ — se não há canônica, apenas promove a linha antiga.
    op.execute(
        """
        UPDATE fontes_ingestao SET slug = 'stj'
        WHERE slug = 'juris_import_stj'
          AND NOT EXISTS (
              SELECT 1 FROM fontes_ingestao AS can
              WHERE can.slug = 'stj'
          )
        """
    )
    # STJ — quando coexistem, consolida na linha canônica.
    op.execute(
        """
        UPDATE fontes_ingestao SET
            ultima_execucao = CASE
                WHEN src.ultima_execucao IS NOT NULL
                 AND (fontes_ingestao.ultima_execucao IS NULL
                      OR src.ultima_execucao > fontes_ingestao.ultima_execucao)
                THEN src.ultima_execucao ELSE fontes_ingestao.ultima_execucao END,
            ultimo_status = CASE
                WHEN src.ultima_execucao IS NOT NULL
                 AND (fontes_ingestao.ultima_execucao IS NULL
                      OR src.ultima_execucao > fontes_ingestao.ultima_execucao)
                THEN src.ultimo_status ELSE fontes_ingestao.ultimo_status END,
            ultimo_erro = CASE
                WHEN src.ultima_execucao IS NOT NULL
                 AND (fontes_ingestao.ultima_execucao IS NULL
                      OR src.ultima_execucao > fontes_ingestao.ultima_execucao)
                THEN src.ultimo_erro ELSE fontes_ingestao.ultimo_erro END,
            execucoes_zeradas_consecutivas = CASE
                WHEN src.ultima_execucao IS NOT NULL
                 AND (fontes_ingestao.ultima_execucao IS NULL
                      OR src.ultima_execucao > fontes_ingestao.ultima_execucao)
                THEN COALESCE(src.execucoes_zeradas_consecutivas, 0)
                ELSE COALESCE(fontes_ingestao.execucoes_zeradas_consecutivas, 0) END,
            registros_novos = COALESCE(fontes_ingestao.registros_novos, 0)
                              + COALESCE(src.registros_novos, 0),
            registros_total = COALESCE(fontes_ingestao.registros_total, 0)
                              + COALESCE(src.registros_total, 0),
            ja_produziu = fontes_ingestao.ja_produziu OR src.ja_produziu,
            ativo = fontes_ingestao.ativo OR src.ativo
        FROM fontes_ingestao AS src
        WHERE fontes_ingestao.slug = 'stj'
          AND src.slug = 'juris_import_stj'
        """
    )
    op.execute(
        """
        UPDATE fontes_ingestao SET
            slug = 'legacy_138_juris_import_stj',
            ativo = FALSE,
            descricao = '[LEGADO CONSOLIDADO 138] ' || descricao
        WHERE slug = 'juris_import_stj'
          AND EXISTS (SELECT 1 FROM fontes_ingestao AS can WHERE can.slug = 'stj')
        """
    )

    # TJMG.
    op.execute(
        """
        UPDATE fontes_ingestao SET slug = 'tjmg'
        WHERE slug = 'juris_import_tjmg'
          AND NOT EXISTS (
              SELECT 1 FROM fontes_ingestao AS can
              WHERE can.slug = 'tjmg'
          )
        """
    )
    op.execute(
        """
        UPDATE fontes_ingestao SET
            ultima_execucao = CASE
                WHEN src.ultima_execucao IS NOT NULL
                 AND (fontes_ingestao.ultima_execucao IS NULL
                      OR src.ultima_execucao > fontes_ingestao.ultima_execucao)
                THEN src.ultima_execucao ELSE fontes_ingestao.ultima_execucao END,
            ultimo_status = CASE
                WHEN src.ultima_execucao IS NOT NULL
                 AND (fontes_ingestao.ultima_execucao IS NULL
                      OR src.ultima_execucao > fontes_ingestao.ultima_execucao)
                THEN src.ultimo_status ELSE fontes_ingestao.ultimo_status END,
            ultimo_erro = CASE
                WHEN src.ultima_execucao IS NOT NULL
                 AND (fontes_ingestao.ultima_execucao IS NULL
                      OR src.ultima_execucao > fontes_ingestao.ultima_execucao)
                THEN src.ultimo_erro ELSE fontes_ingestao.ultimo_erro END,
            execucoes_zeradas_consecutivas = CASE
                WHEN src.ultima_execucao IS NOT NULL
                 AND (fontes_ingestao.ultima_execucao IS NULL
                      OR src.ultima_execucao > fontes_ingestao.ultima_execucao)
                THEN COALESCE(src.execucoes_zeradas_consecutivas, 0)
                ELSE COALESCE(fontes_ingestao.execucoes_zeradas_consecutivas, 0) END,
            registros_novos = COALESCE(fontes_ingestao.registros_novos, 0)
                              + COALESCE(src.registros_novos, 0),
            registros_total = COALESCE(fontes_ingestao.registros_total, 0)
                              + COALESCE(src.registros_total, 0),
            ja_produziu = fontes_ingestao.ja_produziu OR src.ja_produziu,
            ativo = fontes_ingestao.ativo OR src.ativo
        FROM fontes_ingestao AS src
        WHERE fontes_ingestao.slug = 'tjmg'
          AND src.slug = 'juris_import_tjmg'
        """
    )
    op.execute(
        """
        UPDATE fontes_ingestao SET
            slug = 'legacy_138_juris_import_tjmg',
            ativo = FALSE,
            descricao = '[LEGADO CONSOLIDADO 138] ' || descricao
        WHERE slug = 'juris_import_tjmg'
          AND EXISTS (SELECT 1 FROM fontes_ingestao AS can WHERE can.slug = 'tjmg')
        """
    )

    # LexML.
    op.execute(
        """
        UPDATE fontes_ingestao SET slug = 'lexml'
        WHERE slug = 'juris_import_lexml'
          AND NOT EXISTS (
              SELECT 1 FROM fontes_ingestao AS can
              WHERE can.slug = 'lexml'
          )
        """
    )
    op.execute(
        """
        UPDATE fontes_ingestao SET
            ultima_execucao = CASE
                WHEN src.ultima_execucao IS NOT NULL
                 AND (fontes_ingestao.ultima_execucao IS NULL
                      OR src.ultima_execucao > fontes_ingestao.ultima_execucao)
                THEN src.ultima_execucao ELSE fontes_ingestao.ultima_execucao END,
            ultimo_status = CASE
                WHEN src.ultima_execucao IS NOT NULL
                 AND (fontes_ingestao.ultima_execucao IS NULL
                      OR src.ultima_execucao > fontes_ingestao.ultima_execucao)
                THEN src.ultimo_status ELSE fontes_ingestao.ultimo_status END,
            ultimo_erro = CASE
                WHEN src.ultima_execucao IS NOT NULL
                 AND (fontes_ingestao.ultima_execucao IS NULL
                      OR src.ultima_execucao > fontes_ingestao.ultima_execucao)
                THEN src.ultimo_erro ELSE fontes_ingestao.ultimo_erro END,
            execucoes_zeradas_consecutivas = CASE
                WHEN src.ultima_execucao IS NOT NULL
                 AND (fontes_ingestao.ultima_execucao IS NULL
                      OR src.ultima_execucao > fontes_ingestao.ultima_execucao)
                THEN COALESCE(src.execucoes_zeradas_consecutivas, 0)
                ELSE COALESCE(fontes_ingestao.execucoes_zeradas_consecutivas, 0) END,
            registros_novos = COALESCE(fontes_ingestao.registros_novos, 0)
                              + COALESCE(src.registros_novos, 0),
            registros_total = COALESCE(fontes_ingestao.registros_total, 0)
                              + COALESCE(src.registros_total, 0),
            ja_produziu = fontes_ingestao.ja_produziu OR src.ja_produziu,
            ativo = fontes_ingestao.ativo OR src.ativo
        FROM fontes_ingestao AS src
        WHERE fontes_ingestao.slug = 'lexml'
          AND src.slug = 'juris_import_lexml'
        """
    )
    op.execute(
        """
        UPDATE fontes_ingestao SET
            slug = 'legacy_138_juris_import_lexml',
            ativo = FALSE,
            descricao = '[LEGADO CONSOLIDADO 138] ' || descricao
        WHERE slug = 'juris_import_lexml'
          AND EXISTS (SELECT 1 FROM fontes_ingestao AS can WHERE can.slug = 'lexml')
        """
    )


def downgrade() -> None:
    # A soma dos contadores não é separável de forma confiável sem snapshot.
    # As linhas legadas, porém, continuam preservadas no próprio banco.
    pass
