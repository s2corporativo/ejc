# ── app/services/radar_jurisprudencial_orquestrador.py ───────────────────────
# Radar Jurisprudencial — orquestrador (PR 4, Commit 6): liga as Camadas 1
# (determinística) e 2 (semântica) e persiste alertas em
# `TeseAlertaJurisprudencial`. É o corpo chamado pelo job agendado
# (`scheduler.py::job_radar_jurisprudencial`).
#
# Fonte de decisões novas: `knowledge_docs` com `categoria='jurisprudencia'`
# — é onde os pipelines de ingestão existentes (`juris_import/`, os jobs
# agendados `job_ingestao_stj`/`tjmg`/`lexml`) já gravam julgados. NÃO varre
# `jurisprudencias_internas` (só CRUD manual, sem importador automático) nem
# `legal_evidence` (pull por tese sob demanda, não scan em lote).
#
# Watermark: reusa `FonteIngestao`/`registrar_fonte`/`marcar_execucao`
# (mesmo controle que os ingestors já usam) sob o slug `radar_jurisprudencial`
# — só varre decisões com `created_at` após a última execução registrada.
# `marcar_execucao` já grava `ultima_execucao=now()` sozinho; este módulo não
# precisa gerenciar o timestamp.
#
# Camada 3 (explicação por IA) NÃO é chamada automaticamente aqui — decisão
# de escopo deste PR: `AILog.user_id` é NOT NULL e o job agendado não tem um
# usuário autenticado disparando-o; inventar um ator "sistema" é uma decisão
# de auth/RBAC fora do que este PR foi autorizado a mudar. A Camada 3
# (`radar_jurisprudencial_explicacao.gerar_explicacao`) fica pronta para
# acionamento futuro por um humano (ex.: endpoint "explicar este alerta").
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag import FonteIngestao, KnowledgeChunk, KnowledgeDoc
from app.models.tese import Tese
from app.services.ingestion_service import marcar_execucao, registrar_fonte
from app.services.radar_jurisprudencial import avaliar_decisao
from app.services.radar_jurisprudencial_embedding import buscar_teses_similares
from app.services.radar_jurisprudencial_registro import registrar_alerta
from app.services.tese_caso_matcher import extrair_termos

logger = logging.getLogger("ejc.radar_jurisprudencial")

FONTE_SLUG = "radar_jurisprudencial"
CATEGORIA_JURISPRUDENCIA = "jurisprudencia"

# Teto de decisões varridas por execução — evita que uma primeira rodada (sem
# watermark ainda) ou uma janela muito larga processe um lote enorme de uma
# vez. Mesma ordem de grandeza dos tetos de `impacto_regulatorio.py`.
MAX_DECISOES_POR_EXECUCAO = 200

# Severidade atribuída a uma tese que SÓ a Camada 2 (semântica) encontrou —
# nunca "critica"/"alta"/"media", que exigem sinal textual/citação da Camada
# 1 (mais confiável por definição). Semântica pura é o sinal mais fraco.
_SEVERIDADE_SO_SEMANTICA = "baixa"


async def _carregar_teses(db: AsyncSession) -> list[dict]:
    linhas = (await db.execute(
        select(
            Tese.id, Tese.titulo, Tese.area_juridica, Tese.tags,
            Tese.descricao, Tese.fundamentacao, Tese.jurisprudencia,
        ).where(
            Tese.deleted_at.is_(None),
            Tese.status_validacao.is_distinct_from("arquivada"),
        )
    )).all()
    return [
        {
            "id": r.id, "titulo": r.titulo, "area_juridica": r.area_juridica,
            "termos": extrair_termos(r.titulo, r.tags, r.descricao, r.fundamentacao),
            "fundamentacao": r.fundamentacao, "jurisprudencia": r.jurisprudencia,
        }
        for r in linhas
    ]


async def _montar_decisao(db: AsyncSession, doc: KnowledgeDoc) -> dict:
    chunks = (await db.execute(
        select(KnowledgeChunk.conteudo)
        .where(KnowledgeChunk.doc_id == doc.id)
        .order_by(KnowledgeChunk.chunk_index.asc())
    )).scalars().all()
    extra = doc.extra or {}
    return {
        "titulo": doc.titulo,
        "ementa": "\n".join(chunks),
        "tribunal": doc.tribunal,
        "numero_processo": extra.get("numero_processo"),
        "data_julgamento": extra.get("data_julgamento"),
        "link": doc.fonte,
        "area_juridica": extra.get("area_juridica"),
        "fonte": extra.get("fonte_importacao"),
    }


def _mesclar_camada_semantica(afetadas: list[dict], semelhantes: list[dict]) -> list[dict]:
    """Camada 2 só ADICIONA teses que a Camada 1 não achou — nunca rebaixa
    severidade já definida pela Camada 1 (evidências de natureza diferente:
    match de termo/citação vs. proximidade vetorial)."""
    ja_encontradas = {t["tese_id"] for t in afetadas}
    extras = [
        {
            "tese_id": s["tese_id"], "titulo": s["titulo"], "score": None,
            "termos_casados": [], "citacoes_casadas": [],
            "severidade": _SEVERIDADE_SO_SEMANTICA, "area_alinhada": None,
            "score_semantico": s["score_semantico"],
        }
        for s in semelhantes
        if s["tese_id"] not in ja_encontradas
    ]
    return afetadas + extras


async def executar_radar(
    db: AsyncSession, *, limite_decisoes: int = MAX_DECISOES_POR_EXECUCAO,
) -> dict:
    """Varre decisões novas desde a última execução, avalia contra as teses
    (Camadas 1+2) e persiste os alertas. Retorna um resumo consultável pelo
    heartbeat (`decisoes_varridas`, `alertas_criados`, `alertas_duplicados`,
    `erros`) — nunca "ok" mudo (achado de auditoria: monitoramento precisa
    aferir resultado, não só execução).

    Erro ao processar UMA decisão não aborta as demais (mesmo padrão de
    `importar_julgados`/`importar_evidencias`).
    """
    await registrar_fonte(db, FONTE_SLUG, "Radar Jurisprudencial — varredura de decisões novas")
    fonte = (await db.execute(
        select(FonteIngestao).where(FonteIngestao.slug == FONTE_SLUG)
    )).scalar_one()

    filtros = [
        KnowledgeDoc.categoria == CATEGORIA_JURISPRUDENCIA,
        KnowledgeDoc.deleted_at.is_(None),
        KnowledgeDoc.vigente.is_(True),
    ]
    if fonte.ultima_execucao is not None:
        filtros.append(KnowledgeDoc.created_at > fonte.ultima_execucao)
    docs = (await db.execute(
        select(KnowledgeDoc).where(*filtros)
        .order_by(KnowledgeDoc.created_at.asc())
        .limit(limite_decisoes)
    )).scalars().all()

    teses = await _carregar_teses(db)

    decisoes_varridas = alertas_criados = alertas_duplicados = erros = 0
    for doc in docs:
        try:
            decisao = await _montar_decisao(db, doc)
            afetadas = avaliar_decisao(decisao, teses)

            texto_semantico = f"{decisao['titulo']} {decisao['ementa']}".strip()
            semelhantes = await buscar_teses_similares(db, texto_semantico)
            afetadas = _mesclar_camada_semantica(afetadas, semelhantes)

            resultado = await registrar_alerta(
                db, decisao, afetadas, chave_origem=doc.chave_origem or doc.id,
            )
            if resultado["status"] == "criado":
                alertas_criados += 1
            elif resultado["status"] == "duplicado":
                alertas_duplicados += 1
            decisoes_varridas += 1
        except Exception:
            erros += 1
            logger.exception("Radar Jurisprudencial: falha ao processar decisão %s", doc.id)

    await marcar_execucao(
        db, FONTE_SLUG,
        status="erro" if erros else "ok",
        novos=alertas_criados, total=decisoes_varridas,
    )
    await db.commit()

    return {
        "decisoes_varridas": decisoes_varridas,
        "alertas_criados": alertas_criados,
        "alertas_duplicados": alertas_duplicados,
        "erros": erros,
    }
