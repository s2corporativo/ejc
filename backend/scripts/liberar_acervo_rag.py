#!/usr/bin/env python
# ── scripts/liberar_acervo_rag.py ────────────────────────────────────────────
# Diagnostica e (com --aplicar) LIBERA o acervo que já está no banco mas não
# chega à IA. Achado C-1 da auditoria de 04/09/2026: o gate de recuperação
# (ai_service.filtros_gate_rag) é fail-closed e está correto, mas nenhum
# ingestor automático produz os metadados que ele exige — o acervo entra, o
# painel de saúde diz "aprovado", e a recuperação devolve vazio.
#
# Este script NÃO enfraquece o gate. Ele preenche, com trilha, os metadados que
# o gate exige, e só em documentos cuja ORIGEM é fonte oficial verificável.
#
# Motivos de bloqueio e tratamento:
#   1. rag_status ausente/'pendente'  → 'aprovado'  (só origem oficial)
#   2. legal_status não verificado    → 'vigente' + proveniência
#                                       (só com --vigencia; só origem oficial;
#                                        nunca sobre marcador de revogação)
#   3. súmula sem extra.conferido     → NÃO tratado: exige reconferência
#                                       individual (ver sumulas_ingestion.py)
#   4. chunk sem embedding            → scripts.reembedar_chunks_orfaos
#
# Nunca toca: 'recusado', 'bloqueado', quarentena, requires_human_review —
# decisão humana explícita prevalece sobre qualquer liberação em lote.
#
# Uso (container ejc_backend):
#   python -m scripts.liberar_acervo_rag                       # só diagnostica
#   python -m scripts.liberar_acervo_rag --aplicar             # 1 + 4
#   python -m scripts.liberar_acervo_rag --aplicar --vigencia  # 1 + 2 + 4
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import text

from app.core.database import AsyncSessionLocal

logger = logging.getLogger("ejc.liberar_acervo")

# Origens aceitas como fonte oficial para liberação em LOTE. Documento sem uma
# destas origens nunca é tocado por este script — segue para curadoria
# individual no painel de governança.
ORIGENS_OFICIAIS = (
    "planalto:%",   # texto compilado do Planalto
    "%planalto%",
    "lexml:%",
    "%lexml%",
    "%.gov.br%",    # portais oficiais
    "%.jus.br%",    # tribunais
)

# Categorias alcançadas pelo gate de vigência (`LIKE '%legisl%'`).
# Duas ficam DE FORA de propósito:
#   • `proposicao_legislativa` — proposta em tramitação não é norma vigente e
#     não pode fundamentar peça;
#   • `referencia_legislativa` (LexML) — o PR #1452 estabeleceu que o LexML
#     federa ementa/metadado, NUNCA o inteiro teor. Não se atesta vigência a
#     partir de resumo; esses documentos seguem para curadoria individual.
CATS_VIGENCIA = ("legislacao", "legislacao_tributaria")

# Status de vigência que jamais podem ser sobrescritos por liberação em lote.
STATUS_INTOCAVEIS = ("revogada", "revogado", "parcialmente_revogada", "suspensa")

MARCADOR = "liberacao_lote:auditoria_c1_2026-09-04"

# Predicado de origem oficial, reutilizado nas três consultas.
_COND_ORIGEM = "(fonte ILIKE ANY(:origens) OR chave_origem ILIKE ANY(:origens))"

# Predicado de "candidato a aprovação": sem status, ou pendente, e sem nenhuma
# marca de decisão humana pendente/contrária.
_COND_APROVAR = f"""
    deleted_at IS NULL AND vigente = TRUE
    AND COALESCE(extra->>'rag_status','') IN ('', 'pendente')
    AND COALESCE((extra->>'quarantine_active')::boolean, false) = false
    AND COALESCE((extra->>'requires_human_review')::boolean, false) = false
    AND {_COND_ORIGEM}
"""

_COND_VIGENCIA = f"""
    deleted_at IS NULL AND vigente = TRUE
    AND categoria = ANY(:cats)
    AND lower(btrim(COALESCE(extra->>'legal_status',''))) <> ALL(:intocaveis)
    AND {_COND_ORIGEM}
"""


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _contar(db, cond: str, params: dict) -> int:
    sql = text(f"SELECT count(*) FROM knowledge_docs WHERE {cond}")
    return int((await db.execute(sql, params)).scalar() or 0)


async def diagnostico(db) -> dict:
    """Conta o acervo vigente por MOTIVO de bloqueio, com o mesmo predicado que
    `ai_service.filtros_gate_rag` aplica na recuperação."""
    sql = text("""
        SELECT
          count(*) AS total,
          count(*) FILTER (
            WHERE COALESCE(extra->>'rag_status','') <> 'aprovado'
          ) AS sem_aprovacao,
          count(*) FILTER (
            WHERE lower(COALESCE(categoria,'')) LIKE '%legisl%'
              AND NOT (
                lower(btrim(COALESCE(extra->>'legal_status',''))) = 'vigente'
                AND nullif(btrim(extra->>'legal_status_origem'),'') IS NOT NULL
                AND nullif(btrim(extra->>'legal_status_verificado_em'),'') IS NOT NULL
                AND nullif(btrim(extra->>'legal_status_inferido_em'),'') IS NULL
              )
          ) AS vigencia_nao_verificada,
          count(*) FILTER (
            WHERE (COALESCE(chave_origem,'') LIKE 'sumula:%'
                   OR COALESCE(fonte,'') = 'sumula')
              AND COALESCE((extra->>'conferido')::boolean, false) = false
          ) AS sumula_em_quarentena,
          count(*) FILTER (
            WHERE NOT EXISTS (
              SELECT 1 FROM knowledge_chunks kc WHERE kc.doc_id = kd.id
            )
          ) AS sem_chunk,
          count(*) FILTER (
            WHERE EXISTS (
              SELECT 1 FROM knowledge_chunks kc
              WHERE kc.doc_id = kd.id AND kc.embedding IS NULL
            )
          ) AS com_chunk_sem_embedding
        FROM knowledge_docs kd
        WHERE deleted_at IS NULL AND vigente = TRUE
    """)
    return dict((await db.execute(sql)).mappings().first() or {})


async def aprovar_fonte_oficial(db, aplicar: bool) -> int:
    """`rag_status` ausente/'pendente' → 'aprovado', só para origem oficial."""
    params = {"origens": list(ORIGENS_OFICIAIS)}
    if not aplicar:
        return await _contar(db, _COND_APROVAR, params)
    sql = text(f"""
        UPDATE knowledge_docs
        SET extra = COALESCE(extra, '{{}}'::jsonb) || jsonb_build_object(
              'rag_status', 'aprovado',
              'rag_status_origem', :marcador,
              'rag_status_liberado_em', :agora
            )
        WHERE {_COND_APROVAR}
        RETURNING id
    """)
    rows = (await db.execute(sql, {**params, "marcador": MARCADOR,
                                   "agora": _agora()})).fetchall()
    return len(rows)


async def liberar_vigencia(db, aplicar: bool) -> int:
    """`legal_status` → 'vigente' com proveniência, para legislação de origem
    oficial e SEM marcador de revogação/suspensão.

    DECISÃO JURÍDICA, registrada na própria trilha: a liberação é POR ORIGEM
    (lote), não por conferência individual de cada diploma.
    `legal_status_origem` grava o marcador do lote justamente para que a
    curadoria futura distinga o que foi conferido do que foi liberado por
    origem — e para que a liberação seja reversível por marcador.
    """
    params = {"cats": list(CATS_VIGENCIA), "intocaveis": list(STATUS_INTOCAVEIS),
              "origens": list(ORIGENS_OFICIAIS)}
    if not aplicar:
        return await _contar(db, _COND_VIGENCIA, params)
    sql = text(f"""
        UPDATE knowledge_docs
        SET extra = (COALESCE(extra, '{{}}'::jsonb) - 'legal_status_inferido_em')
            || jsonb_build_object(
              'legal_status', 'vigente',
              'legal_status_origem', :marcador,
              'legal_status_verificado_em', :agora
            )
        WHERE {_COND_VIGENCIA}
        RETURNING id
    """)
    rows = (await db.execute(sql, {**params, "marcador": MARCADOR,
                                   "agora": _agora()})).fetchall()
    return len(rows)


async def executar(aplicar: bool, vigencia: bool) -> dict:
    saida: dict = {"marcador": MARCADOR, "aplicado": aplicar,
                   "vigencia_em_lote": vigencia}
    async with AsyncSessionLocal() as db:
        saida["antes"] = await diagnostico(db)
        saida["aprovados"] = await aprovar_fonte_oficial(db, aplicar)
        if vigencia:
            saida["vigencia_liberada"] = await liberar_vigencia(db, aplicar)
        if aplicar:
            await db.commit()
            saida["depois"] = await diagnostico(db)

    if aplicar:
        # Documento liberado sem vetor continua invisível: a perna densa exige
        # `kc.embedding IS NOT NULL`. Reembeda os órfãos no mesmo passe.
        from scripts.reembedar_chunks_orfaos import reembedar
        saida["reembed"] = await reembedar(batch_size=20, dry_run=False)
    return saida


def _imprimir(saida: dict) -> None:
    a = saida["antes"]
    cabecalho = "APLICADO" if saida["aplicado"] else "SIMULAÇÃO (use --aplicar)"
    print(f"\n{cabecalho} — {MARCADOR}\n")
    print(f"  docs vigentes no acervo ............ {a.get('total')}")
    print(f"  sem rag_status='aprovado' .......... {a.get('sem_aprovacao')}")
    print(f"  legislação sem vigência verificada . {a.get('vigencia_nao_verificada')}")
    print(f"  súmula em quarentena ............... {a.get('sumula_em_quarentena')}")
    print(f"  sem nenhum chunk ................... {a.get('sem_chunk')}")
    print(f"  com chunk sem embedding ............ {a.get('com_chunk_sem_embedding')}")
    print(f"\n  → aprovados por fonte oficial ...... {saida.get('aprovados')}")
    if saida["vigencia_em_lote"]:
        print(f"  → vigência liberada em lote ........ {saida.get('vigencia_liberada')}")
    else:
        print("  → vigência: NÃO tocada (use --vigencia)")
    if saida["aplicado"]:
        d = saida.get("depois", {})
        print(f"\n  restam bloqueados por aprovação .... {d.get('sem_aprovacao')}")
        print(f"  restam bloqueados por vigência ..... {d.get('vigencia_nao_verificada')}")
        print(f"  reembed ............................ {saida.get('reembed')}")
    print()


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Libera o acervo do RAG bloqueado por metadado de curadoria."
    )
    p.add_argument("--aplicar", action="store_true",
                   help="grava as alterações (default: apenas simula)")
    p.add_argument("--vigencia", action="store_true",
                   help="também libera legal_status='vigente' em lote por ORIGEM "
                        "oficial — decisão jurídica do titular, ver docstring")
    p.add_argument("--formato", choices=("texto", "json"), default="texto")
    return p.parse_args()


async def _main(args: argparse.Namespace) -> None:
    saida = await executar(args.aplicar, args.vigencia)
    if args.formato == "json":
        print(json.dumps(saida, indent=2, ensure_ascii=False, default=str))
    else:
        _imprimir(saida)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main(_parse_args()))
