# ── app/services/juris_import/ingest.py ──────────────────────────────────────
# Ingestão de julgados normalizados nos DOIS consumidores existentes:
#
#   1. Base de conhecimento RAG — via upsert_documento (chunking + embeddings
#      LOCAIS + versionamento), categoria "jurisprudencia".
#   2. Base oficial de citações validadas — o gate anti-alucinação de peças
#      (_fonte_juris_validada em routers/legal_docs.py) consulta os MESMOS
#      knowledge_docs: categoria em _JURIS_CATEGORIAS + extra.fonte_validada
#      = true + extra.confidence_level em (alta|media) + extra.rag_status em
#      (aprovado|disponivel), casando por extra.numero_processo ou pela URL em
#      `fonte`. Um único upsert com esses campos alimenta os dois consumidores.
#
# DEDUP por tribunal+número: chave_origem principal do conector (canônica
# "julgado:<TRIB>:<digitos>" ou a MESMA chave do ingestor agendado, ex.
# "stj:<registro>") + demais chaves — julgado existente NÃO é reimportado.
#
# Execução em background com status consultável: segue o padrão de jobs de
# ingestão do repo (FonteIngestao/registrar_fonte/marcar_execucao) + trilha em
# AuditLog (criar_audit_log). Determinístico, sem IA externa (LGPD).
from __future__ import annotations

import json
import logging
from collections import OrderedDict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import criar_audit_log
from app.models.rag import KnowledgeDoc
from app.services.ingestion_service import (
    marcar_execucao, registrar_fonte, upsert_documento,
)
from app.services.juris_import.base import JulgadoNormalizado, no_ano
from app.services.verificador_jurisprudencia import formatar_cnj

logger = logging.getLogger("ejc.juris_import")

CATEGORIA_RAG = "jurisprudencia"     # ∈ _JURIS_CATEGORIAS do gate de citações


def _numero_canonico(j: JulgadoNormalizado) -> str:
    """Número no formato que as peças citam (máscara CNJ p/ 20 dígitos)."""
    dig = j.numero_digitos()
    return formatar_cnj(dig) if len(dig) == 20 else (j.numero or "").strip()


async def importar_julgados(
    db: AsyncSession, julgados: list[JulgadoNormalizado], *, fonte_slug: str,
    ano: int | None = None,
) -> dict:
    """Grava julgados no RAG + base de citações validadas, com dedup.

    Retorna {"importados": int, "duplicados": int, "erros": int} — e, quando
    `ano` é informado, também "fora_do_ano" (julgados barrados pelo filtro).
    `ano` é a GARANTIA FINAL client-side (base.no_ano): os conectores já
    filtram na busca, mas nada fora do ano solicitado chega ao RAG mesmo que
    um conector deixe passar. Commit POR JULGADO após cada upsert bem-sucedido
    (limite ≤ 100 — custo ok): o rollback de um item com erro nunca descarta
    itens já contados, e erro em um julgado não aborta os demais.
    """
    fora_do_ano = 0
    if ano is not None:
        aceitos = [j for j in julgados if no_ano(j.data, ano)]
        fora_do_ano = len(julgados) - len(aceitos)
        julgados = aceitos
    importados = duplicados = erros = 0
    for j in julgados:
        try:
            chaves = j.chaves_dedup()
            existente = (await db.execute(
                select(KnowledgeDoc.id).where(
                    KnowledgeDoc.chave_origem.in_(chaves),
                    KnowledgeDoc.deleted_at.is_(None),
                ).limit(1)
            )).scalar_one_or_none()
            if existente:
                duplicados += 1
                continue
            titulo = f"{j.tribunal} {j.classe or ''} {j.numero}".strip()
            conteudo = j.ementa
            if j.inteiro_teor:
                conteudo = f"{conteudo}\n\nINTEIRO TEOR:\n{j.inteiro_teor}"
            res = await upsert_documento(
                db,
                titulo=titulo[:500],
                categoria=CATEGORIA_RAG,
                conteudo=conteudo,
                chave_origem=j.chave_dedup(),
                fonte=j.url_fonte,           # URL oficial → validação por URL
                tribunal=(j.tribunal or "")[:20] or None,
                confianca="alta",            # fonte oficial documentada
                extra={
                    # Campos lidos por _fonte_juris_validada (gate de peças):
                    "numero_processo": _numero_canonico(j),
                    "fonte_validada": True,
                    "rag_status": "aprovado",
                    "tipo_fonte": "jurisprudencia_oficial",
                    # Metadados de citação (tribunal+número+data+url):
                    "numero_bruto": j.numero,
                    "data_julgamento": j.data,
                    "orgao_julgador": j.orgao_julgador,
                    "relator": j.relator,
                    "classe": j.classe,
                    "url_fonte": j.url_fonte,
                    "fonte_importacao": fonte_slug,
                },
            )
            if res == "novo":
                importados += 1
            else:               # "inalterado"/"atualizado" — já existia
                duplicados += 1
            await db.commit()   # durável antes de contar o próximo item
        except Exception as e:
            erros += 1
            logger.warning("[juris_import:%s] falha em %s: %s: %s",
                           fonte_slug, j.numero, type(e).__name__, e)
            await db.rollback()  # afeta só o item corrente (já commitados a salvo)
    resumo = {"importados": importados, "duplicados": duplicados, "erros": erros}
    if ano is not None:      # chave condicional — contrato antigo inalterado
        resumo["fora_do_ano"] = fora_do_ano
    return resumo


# ── Jobs em background com status consultável ────────────────────────────────
# Registro em memória (processo único / uvicorn) — o resultado DURÁVEL fica em
# fontes_ingestao (marcar_execucao) e na trilha de auditoria (audit_logs).
_JOBS: "OrderedDict[str, dict]" = OrderedDict()
_MAX_JOBS = 100


def registrar_job(job_id: str, dados: dict) -> None:
    _JOBS[job_id] = dados
    while len(_JOBS) > _MAX_JOBS:
        _JOBS.popitem(last=False)


def status_job(job_id: str) -> dict | None:
    return _JOBS.get(job_id)


async def executar_importacao(
    job_id: str, fonte: str, consulta: str, tribunal: str | None,
    limite: int, user_id: str | None, user_role: str | None,
    ano: int | None = None,
) -> None:
    """Corpo do BackgroundTask: busca na fonte, ingere, audita e marca status.

    Nunca levanta — qualquer falha vira status "erro" consultável no job e na
    linha da fonte (fontes_ingestao).
    """
    from app.core.database import AsyncSessionLocal
    from app.services.juris_import import FONTES

    slug = f"juris_import_{fonte}"
    registrar_job(job_id, {
        "job_id": job_id, "status": "executando", "fonte": fonte,
        "consulta": consulta, "tribunal": tribunal, "limite": limite,
        "ano": ano,
        "user_id": user_id,   # ownership: GET /status só para o dono (ou admin)
        "iniciado_em": datetime.now(timezone.utc).isoformat(),
    })
    resumo = {"importados": 0, "duplicados": 0, "erros": 0}
    erro: str | None = None
    total = 0
    try:
        info = FONTES[fonte]
        julgados = await info["buscar"](
            consulta, tribunal=tribunal, limite=limite, ano=ano)
        total = len(julgados)
        async with AsyncSessionLocal() as db:
            await registrar_fonte(db, slug, info["descricao"], CATEGORIA_RAG)
            resumo = await importar_julgados(
                db, julgados, fonte_slug=slug, ano=ano)
            await criar_audit_log(
                db, user_id, user_role,
                acao="IMPORTACAO_JURISPRUDENCIA",
                entidade="knowledge_docs",
                registro_id=job_id,
                detalhes=json.dumps({
                    "fonte": fonte, "consulta": consulta[:200],
                    "tribunal": tribunal, "limite": limite, "ano": ano,
                    "encontrados": total, **resumo,
                }, ensure_ascii=False),
            )
            await marcar_execucao(
                db, slug,
                status="erro" if resumo["erros"] and not resumo["importados"]
                else ("parcial" if resumo["erros"] else "sucesso"),
                novos=resumo["importados"], total=total,
            )
            await db.commit()
    except Exception as e:      # fail-safe: job nunca derruba o worker
        erro = f"{type(e).__name__}: {e}"[:300]
        logger.error("[juris_import:%s] %s", fonte, erro)
        try:
            async with AsyncSessionLocal() as db:
                await registrar_fonte(db, slug, f"Importação {fonte}", CATEGORIA_RAG)
                await marcar_execucao(db, slug, status="erro",
                                      novos=0, total=total, erro=erro)
                await db.commit()
        except Exception:
            logger.warning(
                "[juris_import:%s] Falha ao registrar execução de erro (fail-soft).",
                fonte, exc_info=True,
            )
    registrar_job(job_id, {
        "job_id": job_id,
        "status": "erro" if erro else "concluido",
        "fonte": fonte, "consulta": consulta, "tribunal": tribunal,
        "ano": ano,
        "user_id": user_id,
        "encontrados": total, "resumo": resumo, "erro": erro,
        "finalizado_em": datetime.now(timezone.utc).isoformat(),
    })
