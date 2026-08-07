"""138 — Consolida fontes de ingestão duplicadas (Onda 2 — Refatoração Total).

Problema: a trilha agendada (scheduler) grava as fontes de jurisprudência com
os slugs `stj`/`tjmg`/`lexml`, enquanto a trilha on-demand (juris_import)
gravava `juris_import_stj`/`juris_import_tjmg`/`juris_import_lexml`. São a
MESMA fonte — mesmos ingestores/keyspace de dedup — com métricas separadas, e
o painel (GET /ia-governanca/fontes) mostrava cada uma duas vezes.

O código passou a usar o slug único (services/juris_import/ingest.py); esta
migration mescla o histórico das linhas antigas `juris_import_*` nas linhas
canônicas:

  • contadores (`registros_novos`, `registros_total`) são SOMADOS;
  • `ja_produziu` e `ativo` viram OR lógico (uma vez produtiva, sempre);
  • `ultima_execucao` mantém o timestamp mais recente, e `ultimo_status`/
    `ultimo_erro`/`execucoes_zeradas_consecutivas` acompanham a linha dessa
    execução mais recente — a sequência de execuções que CONTINUA após a
    unificação é a dela (somar duas sequências "consecutivas" paralelas
    fabricaria um falso `parou_de_produzir` no veredito de saúde);
  • se a linha canônica não existir, a antiga é apenas renomeada.

Idempotente: reexecutar sem linhas `juris_import_*` é no-op.

downgrade: irreversível por natureza — depois da soma não há como separar
quanto veio de cada trilha. Recuperação, se necessária, é via backup do banco
(scripts/backup.sh) anterior ao upgrade. As linhas antigas não são recriadas.
"""
from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "138_consolida_fontes_ingestao"
down_revision = "132_processo_eletronico_mni"
branch_labels = None
depends_on = None

#: Fontes com trilha dupla (agendada + on-demand) a consolidar.
FONTES_DUPLICADAS = ("stj", "tjmg", "lexml")

_CAMPOS = (
    "slug", "descricao", "categoria_rag", "ativo", "ultima_execucao",
    "ultimo_status", "registros_novos", "registros_total", "ultimo_erro",
    "execucoes_zeradas_consecutivas", "ja_produziu",
)


def _aware(dt):
    """Timestamp comparável: naive é assumido UTC (mesma convenção do app).

    Aceita string ISO porque SELECT bruto em SQLite (testes de lógica da
    migration) devolve datetime como texto; em PostgreSQL chega datetime.
    """
    if dt is None:
        return None
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def mesclar_fontes(origem: dict, destino: dict) -> dict:
    """Regra PURA de merge de duas linhas de fontes_ingestao (testável sem banco).

    `origem` é a linha antiga (`juris_import_*`), `destino` a canônica. Devolve
    os campos consolidados a gravar na linha destino (sem `slug`/`descricao`/
    `categoria_rag`, que permanecem os do destino).
    """
    exec_origem = _aware(origem.get("ultima_execucao"))
    exec_destino = _aware(destino.get("ultima_execucao"))
    # A linha "mais recente" dita status/erro/sequência de zeradas. Empate (ou
    # nenhuma execução em ambas) fica com o destino — a trilha canônica.
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


def _buscar(bind, slug: str) -> dict | None:
    row = bind.execute(
        sa.text(
            f"SELECT {', '.join(_CAMPOS)} FROM fontes_ingestao WHERE slug = :slug"
        ),
        {"slug": slug},
    ).mappings().first()
    return dict(row) if row is not None else None


def upgrade() -> None:
    bind = op.get_bind()
    for fonte in FONTES_DUPLICADAS:
        antigo = f"juris_import_{fonte}"
        origem = _buscar(bind, antigo)
        if origem is None:
            continue  # nada a consolidar (idempotência)
        destino = _buscar(bind, fonte)
        if destino is None:
            # Só a trilha on-demand existia — basta renomear para o slug único.
            bind.execute(
                sa.text(
                    "UPDATE fontes_ingestao SET slug = :novo WHERE slug = :antigo"
                ),
                {"novo": fonte, "antigo": antigo},
            )
            continue
        consolidado = mesclar_fontes(origem, destino)
        bind.execute(
            sa.text(
                "UPDATE fontes_ingestao SET "
                "ultima_execucao = :ultima_execucao, "
                "ultimo_status = :ultimo_status, "
                "ultimo_erro = :ultimo_erro, "
                "execucoes_zeradas_consecutivas = :execucoes_zeradas_consecutivas, "
                "registros_novos = :registros_novos, "
                "registros_total = :registros_total, "
                "ja_produziu = :ja_produziu, "
                "ativo = :ativo "
                "WHERE slug = :slug"
            ),
            {**consolidado, "slug": fonte},
        )
        bind.execute(
            sa.text("DELETE FROM fontes_ingestao WHERE slug = :slug"),
            {"slug": antigo},
        )


def downgrade() -> None:
    # Irreversível por natureza (ver docstring): as somas não podem ser
    # desfeitas e as linhas `juris_import_*` não são recriadas. No-op.
    pass
