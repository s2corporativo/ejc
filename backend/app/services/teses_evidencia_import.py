# ── app/services/teses_evidencia_import.py ───────────────────────────────────
# Coleta de evidência jurídica (legal_evidence) para uma tese específica, a
# partir das MESMAS fontes oficiais do pipeline de importação de jurisprudência
# já existente (app/services/juris_import/) — reusa os conectores (lexml, stj,
# tjmg, tcu), o contrato JulgadoNormalizado e o envelope de job assíncrono
# (registrar_job/status_job), mas grava num destino diferente: `legal_evidence`
# em vez de `knowledge_docs`.
#
# Duas máquinas de estado que este módulo NÃO mistura:
#   - Tese.status_validacao (11 estados) — ciclo de vida da TESE.
#   - LegalEvidence.status ("coletada"|"verificada"|...) — confiabilidade de UM
#     registro de evidência. Este módulo só cria evidências com status inicial
#     "coletada" — nunca promove tese nem evidência a um status de confiança
#     (isso é ato humano via os endpoints de validação/revisão do PR 2).
#
# Dedup por (tese_id, hash_fingerprint) OU (tese_id, tribunal, numero) já
# existente — mesma tese pode reaproveitar julgados já vistos por qualquer
# fonte sem duplicar. Commit POR ITEM (erro em um julgado não aborta os
# demais) — mesmo padrão de durabilidade de juris_import.ingest.importar_julgados.
from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import criar_audit_log
from app.models.tese_extensoes import LegalEvidence
from app.services.ingestion_service import marcar_execucao, registrar_fonte
from app.services.juris_import.base import JulgadoNormalizado
from app.services.juris_import.ingest import registrar_job, status_job  # noqa: F401 (reexportado p/ o router)

logger = logging.getLogger("ejc.teses_evidencia_import")

CATEGORIA_FONTE = "legal_evidence"


def _parse_data(data_iso: str | None) -> date | None:
    """`JulgadoNormalizado.data` vem como string ISO ou None — LegalEvidence
    exige `date` real na coluna. Data malformada vira None (nunca levanta)."""
    if not data_iso:
        return None
    try:
        return date.fromisoformat(data_iso[:10])
    except ValueError:
        return None


def _hash_fingerprint(j: JulgadoNormalizado) -> str:
    base = f"{(j.tribunal or '').upper()}|{j.numero or ''}|{j.ementa or ''}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


async def importar_evidencias(
    db: AsyncSession, julgados: list[JulgadoNormalizado], *, tese_id: str,
    fonte_slug: str, user_id: str | None,
) -> dict:
    """Grava julgados como `LegalEvidence` (status="coletada") vinculados a
    `tese_id`, com dedup e commit por item. Retorna
    {"importados", "duplicados", "erros"}."""
    importados = duplicados = erros = 0
    for j in julgados:
        try:
            hash_fp = _hash_fingerprint(j)
            existente = (await db.execute(
                select(LegalEvidence.id).where(
                    LegalEvidence.tese_id == tese_id,
                    or_(
                        LegalEvidence.hash_fingerprint == hash_fp,
                        and_(
                            LegalEvidence.tribunal == j.tribunal,
                            LegalEvidence.numero == j.numero,
                        ),
                    ),
                ).limit(1)
            )).scalar_one_or_none()
            if existente:
                duplicados += 1
                continue
            db.add(LegalEvidence(
                id=str(uuid4()),
                tese_id=tese_id,
                tipo_fonte=fonte_slug,
                tribunal=j.tribunal,
                numero=j.numero,
                url_oficial=j.url_fonte,
                data_consulta=datetime.now(timezone.utc),
                inteiro_teor_disponivel=bool(j.inteiro_teor),
                orgao_julgador=j.orgao_julgador,
                relator=j.relator,
                data_julgamento=_parse_data(j.data),
                status="coletada",
                trecho_relevante=(j.ementa or "")[:2000],
                hash_fingerprint=hash_fp,
                coletado_por=user_id,
            ))
            importados += 1
            await db.commit()   # durável antes de contar o próximo item
        except Exception as e:
            erros += 1
            logger.warning(
                "[teses_evidencia:%s] falha em %s/%s: %s: %s",
                fonte_slug, j.tribunal, j.numero, type(e).__name__, e,
            )
            await db.rollback()  # afeta só o item corrente
    return {"importados": importados, "duplicados": duplicados, "erros": erros}


async def executar_coleta_evidencia(
    job_id: str, tese_id: str, fonte: str, consulta: str, tribunal: str | None,
    limite: int, user_id: str | None, user_role: str | None,
    ano: int | None = None,
) -> None:
    """Corpo do BackgroundTask: busca na fonte, grava evidências, audita e
    marca status. Nunca levanta — qualquer falha vira status "erro" consultável
    no job e na linha de `fontes_ingestao`."""
    from app.core.database import AsyncSessionLocal
    from app.services.juris_import import FONTES

    # Slug com prefixo `teses_evidencia:` — namespace PRÓPRIO, separado do
    # slug puro (`lexml`/`stj`/`tjmg`/`tcu`) que juris_import/scheduler já
    # usam para a trilha de ingestão do RAG. Evita que as duas trilhas
    # (RAG vs. evidência de tese) pisem na mesma linha de fontes_ingestao.
    slug = f"teses_evidencia:{fonte}"
    registrar_job(job_id, {
        "job_id": job_id, "status": "executando", "tese_id": tese_id,
        "fonte": fonte, "consulta": consulta, "tribunal": tribunal,
        "limite": limite, "ano": ano, "user_id": user_id,
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
            await registrar_fonte(
                db, slug, f"Coleta de evidência jurídica — {info['descricao']}",
                CATEGORIA_FONTE,
            )
            resumo = await importar_evidencias(
                db, julgados, tese_id=tese_id, fonte_slug=fonte, user_id=user_id)
            await criar_audit_log(
                db, user_id, user_role,
                acao="COLETA_EVIDENCIA_TESE",
                entidade="legal_evidence",
                registro_id=tese_id,
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
        logger.error("[teses_evidencia:%s] %s", fonte, erro)
        try:
            async with AsyncSessionLocal() as db:
                await registrar_fonte(
                    db, slug, f"Coleta de evidência — {fonte}", CATEGORIA_FONTE)
                await marcar_execucao(db, slug, status="erro",
                                      novos=0, total=total, erro=erro)
                await db.commit()
        except Exception:
            logger.warning(
                "[teses_evidencia:%s] Falha ao registrar execução de erro (fail-soft).",
                fonte, exc_info=True,
            )
    registrar_job(job_id, {
        "job_id": job_id,
        "status": "erro" if erro else "concluido",
        "tese_id": tese_id, "fonte": fonte, "consulta": consulta,
        "tribunal": tribunal, "ano": ano, "user_id": user_id,
        "encontrados": total, "resumo": resumo, "erro": erro,
        "finalizado_em": datetime.now(timezone.utc).isoformat(),
    })
