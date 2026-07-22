"""app/seeds/base_juridica_seed.py — seed AUTOMÁTICO e IDEMPOTENTE da base de
conhecimento jurídica REAL (fundamentação que o RAG recupera de verdade).

Motivação (auditoria da Central de IA — P0): o boot só semeava admin + skills +
tipos de documento e, no deploy, apenas a Bíblia FICTÍCIA. Um ambiente
recém-provisionado respondia consultas jurídicas com o RAG VAZIO de fontes reais
(o modelo caía no conhecimento paramétrico). Este módulo passa a semear, no
fluxo automático, as duas fontes reais que já existiam mas só entravam via o
script manual `scripts/popular_base_conhecimento.sh`:

  1. SÚMULAS conferidas (STF/STJ/TST) — dataset OFFLINE curado em
     `app/services/sumulas_ingestion.py` (SUMULAS_SEED, extra.conferido=true,
     extra.rag_status='aprovado'). Sem rede, instantâneo, idempotente.
  2. LEGISLAÇÃO federal (lei seca) — ingestor `app/services/ingestors/planalto.py`
     (categoria='legislacao', chave `planalto:<slug>`, chunk por artigo,
     extra.rag_status='aprovado'). Faz download do Planalto (REDE).

Por que a fundamentação semeada REALMENTE aparece na busca (filtros de RAG em
`app/services/ai_service.py`):
  • _FILTRO_APROVADO_RAG (RAG_EXIGIR_APROVADO=true, default) exige
    extra->>'rag_status'='aprovado' — súmulas e legislação já gravam 'aprovado'.
  • _FILTRO_SUMULAS_QUARENTENA (default) exige extra->>'conferido'=true para docs
    de súmula — SUMULAS_SEED grava conferido=true nos verbetes reconferidos.
  • O gate filtra por extra->>'rag_status', NÃO por status_indexacao. Por isso
    docs semeados com embutir_vetores=False (status_indexacao='pendente')
    já são recuperados pela busca LEXICAL/FTS; a busca SEMÂNTICA passa a
    devolvê-los assim que os vetores forem preenchidos (ver abaixo).

Degradação graciosa dos EMBEDDINGS (nunca quebra o boot):
  • O seed NÃO vetoriza inline (embutir_vetores=False). Os chunks nascem órfãos
    (embedding NULL, status_indexacao='pendente').
  • Quem completa os vetores, sem passo manual, quando o serviço de embeddings
    estiver disponível:
      - scheduler `_reembedar_rag_orfaos` (de hora em hora, minuto :20);
      - deploy `scripts/reparar_conhecimento_rag.py` (aprova + reembeda);
      - a qualquer momento: `python -m scripts.reembedar_chunks_orfaos`.

Idempotência e não-destrutividade:
  • Súmulas: `ingerir_sumulas_seed` reconcilia por (titulo, tribunal) — upsert,
    nunca duplica; nenhum DROP/DELETE em massa.
  • Legislação: upsert por `chave_origem` (versionamento migration 068). Além
    disso, no boot só é disparada quando o corpus está AUSENTE (existence-guard),
    evitando rede a cada boot.
  • Toda etapa é best-effort e isolada: falha/timeout de uma NUNCA aborta o boot
    nem impede a outra.

EXPANDIR a base depois (trazer VOLUME real de jurisprudência/legislação) — não
precisa ativar aqui, só ligar os ingestores oficiais opt-in já existentes:
  • Legislação/atos: os jobs semanais do scheduler já reingerem
    `planalto` (ing_planalto, dom 03h), `camara`/`senado`, e o pacote
    `app/services/conhecimento_ingest/` (ANPD + Normas RFB, gate
    CONHECIMENTO_INGEST_ENABLED, default ON).
  • Jurisprudência: `app/services/ingestors/stj.py` (ing_stj, sáb 03h),
    `djen.py` (gate DJEN_INGEST_ENABLED, default OFF),
    `tjmg.py` (gate TJMG_INGEST_ENABLED, default OFF) e a busca LexML em
    `app/services/jurisprudencia_externa.py`.
  • Federação estadual (ALMG)/municipal (Betim)/tribunais numa fonte só:
    `app/services/ingestors/lexml.py` (ing_lexml, sáb 05h, gate
    LEXML_INGEST_ENABLED, default OFF) — legislação + jurisprudência via LexML.
  Para trazer volume: ligue os flags de env correspondentes (default OFF nos
  de jurisprudência) e amplie o CATALOGO/temas do respectivo ingestor. Todos
  escrevem via `upsert_documento` (mesma dedup por chave), então rodar seed +
  cron em qualquer ordem nunca duplica.

Uso (WORKDIR /app, dentro do container):
    python -m app.seeds.base_juridica_seed                     # só súmulas
    python -m app.seeds.base_juridica_seed --incluir-legislacao
    python -m app.seeds.base_juridica_seed --incluir-legislacao --forcar-legislacao
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os

from sqlalchemy import func, select

logger = logging.getLogger("ejc.seed_base_juridica")

# Orçamento de rede da legislação NO BOOT (segundos). Conservador de propósito:
# `seeds/seed_all.py` roda ANTES do uvicorn e o deploy só espera ~60s pelo
# /api/health (scripts/deploy_vps_safe.sh). O download do Planalto é
# existence-guarded (só na 1ª vez de um ambiente vazio); ainda assim limitamos o
# tempo para JAMAIS estourar a janela de health-check. Ajustável por env.
_TIMEOUT_BOOT_DEFAULT = 30
# No CLI (deploy, DEPOIS do health-check) a janela é folgada.
_TIMEOUT_CLI_DEFAULT = 300


def _env_bool(nome: str, default: bool) -> bool:
    v = os.getenv(nome)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on", "sim"}


async def seed_sumulas() -> dict:
    """Ingere o dataset OFFLINE de súmulas conferidas (idempotente, sem rede).

    Grava extra.conferido=true + extra.rag_status='aprovado' → passa os filtros
    _FILTRO_SUMULAS_QUARENTENA e _FILTRO_APROVADO_RAG do RAG.
    """
    from app.core.database import AsyncSessionLocal
    from app.services.sumulas_ingestion import ingerir_sumulas_seed

    async with AsyncSessionLocal() as db:
        r = await ingerir_sumulas_seed(db)
    logger.info("[base-juridica] súmulas: %s", r)
    return r


async def _legislacao_ja_semeada() -> bool:
    """True se o corpus do PLANALTO (chave `planalto:<slug>`) já existe (guard).

    Chaveado no PREFIXO da chave_origem do Planalto — NÃO na categoria genérica
    'legislacao', que também abriga ANPD/RFB (conhecimento_ingest): um banco só
    com ANPD faria o guard pular indevidamente o corpus FEDERAL que este seed
    deve garantir. Corpus parcial (raro — timeout no meio do 1º boot) é
    completado depois pelo job semanal `ing_planalto` e pelo passo de deploy,
    então basta count>0.
    """
    from app.core.database import AsyncSessionLocal
    from app.models.rag import KnowledgeDoc
    from app.services.ingestors import planalto as pl

    async with AsyncSessionLocal() as db:
        n = int((await db.execute(
            select(func.count()).select_from(KnowledgeDoc).where(
                KnowledgeDoc.chave_origem.like(pl.PREFIXO_CHAVE + "%"),
                KnowledgeDoc.vigente.is_(True),
                KnowledgeDoc.deleted_at.is_(None),
            )
        )).scalar() or 0)
    return n > 0


async def seed_legislacao(*, forcar: bool = False, timeout_s: int | None = None) -> dict:
    """Ingere a legislação federal (Planalto, por artigo) — REDE, best-effort.

    - Existence-guarded: sem `forcar`, só busca quando o corpus está ausente
      (evita rede a cada boot; idempotente por natureza).
    - embutir_vetores=False: chunks ficam 'pendente'; o auto-reembed do
      scheduler e o reparar do deploy completam os vetores depois.
    - Bounded por `timeout_s`: se estourar, é ADIADA (não trava o boot); o
      cron semanal / o deploy completam. NUNCA propaga exceção.
    """
    if not forcar and await _legislacao_ja_semeada():
        logger.info("[base-juridica] legislação já presente — pulando (idempotente).")
        return {"status": "ja_presente", "sucessos": 0, "falhas": 0}

    from app.core.database import AsyncSessionLocal
    from scripts.seed_legislacao import executar_seed_legislacao

    async def _rodar() -> dict:
        async with AsyncSessionLocal() as db:
            return await executar_seed_legislacao(db, embutir_vetores=False)

    try:
        if timeout_s and timeout_s > 0:
            rel = await asyncio.wait_for(_rodar(), timeout=timeout_s)
        else:
            rel = await _rodar()
        ok = len(rel.get("sucessos", {}))
        falhas = len(rel.get("falhas", {}))
        logger.info("[base-juridica] legislação: %d ok / %d falha(s)", ok, falhas)
        return {"status": "executado", "sucessos": ok, "falhas": falhas}
    except asyncio.TimeoutError:
        logger.warning(
            "[base-juridica] legislação excedeu %ss no boot — adiada; o cron "
            "semanal (ing_planalto) e o deploy (reparar) completam.", timeout_s,
        )
        return {"status": "timeout", "sucessos": 0, "falhas": 0}
    except Exception as exc:  # noqa: BLE001 — best-effort, nunca aborta o boot
        logger.warning("[base-juridica] legislação falhou (não-fatal): %s", exc)
        return {"status": "erro", "erro": str(exc)[:200], "sucessos": 0, "falhas": 0}


async def seed_base_juridica(
    *,
    incluir_legislacao: bool | None = None,
    forcar_legislacao: bool = False,
    timeout_legislacao: int | None = None,
) -> dict:
    """Orquestra o seed da base REAL (súmulas + legislação). Best-effort e
    idempotente: cada etapa é isolada; falha/timeout de uma não impede a outra
    nem aborta o boot.

    incluir_legislacao=None → decide por env EJC_SEED_LEGISLACAO_BOOT (default
    DESLIGADO no boot; a legislação é garantida no passo de deploy).
    timeout_legislacao=None → env EJC_SEED_LEGISLACAO_TIMEOUT_S
    (default _TIMEOUT_BOOT_DEFAULT).
    """
    resumo: dict = {}

    # 1) Súmulas — OFFLINE, sempre (rápido, sem rede, sem risco de boot).
    try:
        resumo["sumulas"] = await seed_sumulas()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[base-juridica] súmulas falharam (não-fatal): %s", exc)
        resumo["sumulas"] = {"status": "erro", "erro": str(exc)[:200]}

    # 2) Legislação — REDE, opcional/existence-guarded/bounded.
    if incluir_legislacao is None:
        # Default OFF no boot (adere ao padrão do repo: rede/integração externa
        # nasce desligada — CLAUDE.md). Súmulas (offline) entram SEMPRE; a
        # legislação do Planalto (REDE) é garantida no passo de DEPLOY
        # (deploy_vps_safe.sh, após o health-check). EJC_SEED_LEGISLACAO_BOOT=1
        # semeia a legislação já no boot de um ambiente sem deploy.
        incluir_legislacao = _env_bool("EJC_SEED_LEGISLACAO_BOOT", False)
    if incluir_legislacao:
        if timeout_legislacao is None:
            timeout_legislacao = int(
                os.getenv("EJC_SEED_LEGISLACAO_TIMEOUT_S", str(_TIMEOUT_BOOT_DEFAULT))
            )
        resumo["legislacao"] = await seed_legislacao(
            forcar=forcar_legislacao, timeout_s=timeout_legislacao
        )
    else:
        logger.info("[base-juridica] legislação desativada no boot "
                    "(EJC_SEED_LEGISLACAO_BOOT=0).")
        resumo["legislacao"] = {"status": "desativado_boot"}

    return resumo


async def _main_async(args: argparse.Namespace) -> None:
    resumo = await seed_base_juridica(
        incluir_legislacao=args.incluir_legislacao or args.forcar_legislacao,
        forcar_legislacao=args.forcar_legislacao,
        timeout_legislacao=args.timeout,
    )
    print(f"[base-juridica] resumo: {resumo}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Seed idempotente da base jurídica REAL (súmulas + legislação)."
    )
    parser.add_argument(
        "--incluir-legislacao", action="store_true",
        help="também semeia a legislação do Planalto (faz download; REDE).",
    )
    parser.add_argument(
        "--forcar-legislacao", action="store_true",
        help="ignora o existence-guard e reingere a legislação (implica --incluir-legislacao).",
    )
    parser.add_argument(
        "--timeout", type=int, default=_TIMEOUT_CLI_DEFAULT,
        help=f"timeout (s) da etapa de legislação (default {_TIMEOUT_CLI_DEFAULT}).",
    )
    asyncio.run(_main_async(parser.parse_args()))
