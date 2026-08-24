# ── app/services/radar_jurisprudencial_registro.py ───────────────────────────
# Radar Jurisprudencial — persistência do alerta (PR 4, Commit 2).
#
# Separado de `radar_jurisprudencial.py` (Camada 1, função pura) de propósito:
# aquele módulo não toca banco; este é "o chamador" que grava o resultado em
# `TeseAlertaJurisprudencial` (app/models/tese_extensoes.py, já existe desde a
# migração 148 — zero mudança de schema aqui).
#
# Dedup: `chave_dedup` é `f"radar:{chave_origem}"`, reusando a MESMA chave que
# já identifica a decisão de forma única e estável em `KnowledgeDoc.
# chave_origem` (a mesma usada por `juris_import/ingest.py::importar_julgados`
# para dedup de jurisprudência) — só prefixada por namespace, para não colidir
# com outro uso futuro da coluna `chave_dedup`. Isso torna o job idempotente
# mesmo se reprocessar a mesma decisão duas vezes: o UNIQUE da coluna rejeita
# o segundo INSERT, e este módulo checa a existência ANTES de tentar gravar
# (mesmo padrão de `importar_julgados`/`importar_evidencias`).
from __future__ import annotations

from datetime import date
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tese_extensoes import SEVERIDADES_ALERTA, TeseAlertaJurisprudencial


def _parse_data(data_iso: str | None) -> date | None:
    """Data da decisão vem como string ISO ou None — a coluna exige `date`
    real. Data malformada vira None (nunca levanta)."""
    if not data_iso:
        return None
    try:
        return date.fromisoformat(str(data_iso)[:10])
    except ValueError:
        return None


def _severidade_mais_grave(teses_afetadas: list[dict]) -> str:
    """A pior (mais crítica) severidade entre as teses afetadas — é isso que
    determina prioridade de tratamento do alerta como um todo."""
    return min(
        (t["severidade"] for t in teses_afetadas),
        key=SEVERIDADES_ALERTA.index,
    )


async def registrar_alerta(
    db: AsyncSession,
    decisao: dict,
    teses_afetadas: list[dict],
    *,
    chave_origem: str,
) -> dict:
    """Persiste um alerta a partir do resultado da Camada 1 (`avaliar_decisao`).

    `decisao`: mesmo dict consumido por `radar_jurisprudencial.avaliar_decisao`
    (`titulo`, `ementa`, `tribunal`, `numero_processo`, `data_julgamento`,
    `link`), mais `fonte` opcional (`KnowledgeDoc.extra.fonte_importacao`).
    `chave_origem`: `KnowledgeDoc.chave_origem` da decisão — identifica a
    decisão de forma única e estável, usada para dedup.
    `teses_afetadas`: saída de `avaliar_decisao` (não vazia — chamador não
    deveria invocar isto para decisão sem tese afetada, mas o caminho é
    tratado de forma segura mesmo assim).

    Retorna `{"status": "criado"|"duplicado"|"sem_teses_afetadas",
    "alerta_id": str|None}` — nunca levanta por decisão já vista, dedup é
    fluxo normal, não erro.
    """
    if not teses_afetadas:
        return {"status": "sem_teses_afetadas", "alerta_id": None}

    chave_dedup = f"radar:{chave_origem}"[:200]
    existente = (await db.execute(
        select(TeseAlertaJurisprudencial.id)
        .where(TeseAlertaJurisprudencial.chave_dedup == chave_dedup)
    )).scalar_one_or_none()
    if existente:
        return {"status": "duplicado", "alerta_id": existente}

    alerta = TeseAlertaJurisprudencial(
        id=str(uuid4()),
        fonte=(decisao.get("fonte") or "radar_jurisprudencial")[:30],
        chave_dedup=chave_dedup,
        titulo=(decisao.get("titulo") or "")[:500] or None,
        ementa=decisao.get("ementa"),
        tribunal=(decisao.get("tribunal") or "")[:120] or None,
        numero_processo=(decisao.get("numero_processo") or "")[:120] or None,
        link=decisao.get("link"),
        data_julgamento=_parse_data(decisao.get("data_julgamento")),
        severidade=_severidade_mais_grave(teses_afetadas),
        teses_afetadas=teses_afetadas,
        status="novo",
    )
    db.add(alerta)
    await db.commit()
    return {"status": "criado", "alerta_id": alerta.id}
