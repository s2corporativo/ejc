# ── app/services/datajud_cognitive_feed.py ────────────────────────────────────
"""Transforma movimentações DataJud já persistidas em conhecimento do EJC.

Não cria banco vetorial, IA ou cadastro paralelo. DataJud é tratado como fonte
de metadados informativos e nunca como comprovação de intimação ou prazo fatal.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case, CaseMovimento
from app.models.rag import KnowledgeDoc
from app.services.ingestion_service import marcar_execucao, registrar_fonte, upsert_documento

logger = logging.getLogger("ejc.datajud.cognitive_feed")

FONTE_SLUG = "datajud_processos"
CATEGORIA_RAG = "andamento_processual"
AVISO_JURIDICO = (
    "O DataJud/CNJ fornece metadados públicos de tramitação. Este registro não "
    "comprova intimação, publicação, ciência, termo inicial ou vencimento de "
    "prazo. Toda providência deve ser conferida no DJEN ou no sistema judicial "
    "autenticado e validada por advogado."
)
_RE_HASH = re.compile(r"\s*\[dj:([0-9a-f]{16})\]\s*$", re.I)
_REGRAS: tuple[tuple[str, str, str, str], ...] = (
    (r"senten[çc]a|julgamento\s+(procedente|improcedente)", "sentenca", "alta", "Revisar a decisão e avaliar providências."),
    (r"ac[oó]rd[aã]o", "acordao", "alta", "Revisar o acórdão e avaliar providências."),
    (r"decis[aã]o|despacho", "decisao", "alta", "Conferir o teor no sistema oficial."),
    (r"intima[çc][aã]o|cita[çc][aã]o", "possivel_comunicacao", "alta", "Conferir a comunicação oficial; não calcular prazo pelo DataJud."),
    (r"audi[eê]ncia", "audiencia", "alta", "Conferir data, modalidade e determinações."),
    (r"per[ií]cia|laudo\s+pericial", "pericia", "media", "Revisar o evento pericial."),
    (r"recurso|apela[çc][aã]o|agravo|embargo", "recurso", "media", "Verificar natureza, autoria e efeito."),
    (r"arquivamento|tr[aâ]nsito\s+em\s+julgado|baixado\s+definitivamente", "encerramento", "alta", "Conferir encerramento e pendências."),
    (r"juntada|peti[çc][aã]o", "juntada", "informativa", "Verificar o documento juntado quando relevante."),
)


def limpar_descricao(descricao: str | None) -> str:
    return _RE_HASH.sub("", descricao or "").strip()


def hash_movimento(descricao: str | None) -> str | None:
    match = _RE_HASH.search(descricao or "")
    return match.group(1).lower() if match else None


def classificar_movimento(descricao: str | None) -> dict[str, str]:
    texto = limpar_descricao(descricao)
    for padrao, tipo, severidade, providencia in _REGRAS:
        if re.search(padrao, texto, flags=re.I):
            return {
                "tipo_evento": tipo,
                "severidade": severidade,
                "providencia_sugerida": providencia,
            }
    return {
        "tipo_evento": "movimentacao",
        "severidade": "informativa",
        "providencia_sugerida": "Registrar na linha do tempo e revisar se necessário.",
    }


def _valor_enum(valor: Any) -> str:
    return str(getattr(valor, "value", valor) or "")


def _iso(valor: Any) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        if valor.tzinfo is None:
            valor = valor.replace(tzinfo=timezone.utc)
        return valor.isoformat()
    return str(valor)


def _extra_base(case: Case) -> dict[str, Any]:
    return {
        "source_system": "datajud",
        "official_source": True,
        "source_reliability": "official_metadata",
        "legal_effect": "informative_only",
        "deadline_source": False,
        "requires_human_review": True,
        "human_reviewed": False,
        "rag_status": "aprovado",
        "confidence_level": "media",
        "client_id": str(case.client_id),
        "case_id": str(case.id),
        "numero_processo": case.numero_processo,
        "numero_interno": case.numero_interno,
        "area": _valor_enum(case.area),
    }


def _conteudo_movimento(case: Case, mov: CaseMovimento) -> tuple[str, dict[str, Any]]:
    descricao = limpar_descricao(mov.descricao)
    classificacao = classificar_movimento(descricao)
    data_evento = _iso(mov.data_evento)
    texto = (
        "ANDAMENTO PROCESSUAL — DATAJUD/CNJ\n"
        f"Caso: {case.numero_interno or case.id}\n"
        f"Processo: {case.numero_processo or 'não informado'}\n"
        f"Tribunal: {case.tribunal or 'derivado do número CNJ'}\n"
        f"Data: {data_evento or 'não informada'}\n"
        f"Classificação: {classificacao['tipo_evento']}\n"
        f"Movimentação: {descricao}\n"
        f"Providência sugerida: {classificacao['providencia_sugerida']}\n\n"
        f"{AVISO_JURIDICO}"
    )
    extra = {
        **_extra_base(case),
        **classificacao,
        "document_type": "process_movement",
        "movement_id": str(mov.id),
        "movement_date": data_evento,
        "movement_hash": hash_movimento(mov.descricao),
    }
    return texto, extra


def _conteudo_timeline(case: Case, movimentos: list[CaseMovimento]) -> tuple[str, dict[str, Any]]:
    linhas: list[str] = []
    ordem = {"informativa": 0, "media": 1, "alta": 2, "critica": 3}
    severidade_max = "informativa"
    for mov in movimentos:
        classificacao = classificar_movimento(mov.descricao)
        if ordem.get(classificacao["severidade"], 0) > ordem.get(severidade_max, 0):
            severidade_max = classificacao["severidade"]
        linhas.append(
            f"- {_iso(mov.data_evento) or 'sem data'} | "
            f"{classificacao['tipo_evento']} | {limpar_descricao(mov.descricao)}"
        )
    texto = (
        "LINHA DO TEMPO PROCESSUAL CONSOLIDADA — DATAJUD/CNJ\n"
        f"Caso: {case.numero_interno or case.id}\n"
        f"Processo: {case.numero_processo or 'não informado'}\n"
        f"Total: {len(movimentos)} movimentações\n\n"
        + "\n".join(linhas)
        + f"\n\n{AVISO_JURIDICO}"
    )
    extra = {
        **_extra_base(case),
        "document_type": "process_timeline",
        "movement_count": len(movimentos),
        "latest_movement_at": _iso(movimentos[-1].data_evento) if movimentos else None,
        "max_operational_severity": severidade_max,
    }
    return texto, extra


async def alimentar_caso(
    db: AsyncSession,
    case: Case,
    *,
    embutir_vetores: bool = False,
) -> dict[str, Any]:
    if not case.client_id:
        raise ValueError("Caso sem client_id não pode alimentar conhecimento restrito")

    await registrar_fonte(
        db,
        FONTE_SLUG,
        "DataJud/CNJ — metadados de movimentações processuais",
        CATEGORIA_RAG,
    )
    movimentos = (await db.execute(
        select(CaseMovimento).where(
            CaseMovimento.case_id == case.id,
            CaseMovimento.tipo == "andamento_oficial",
            CaseMovimento.descricao.contains("[dj:"),
        ).order_by(CaseMovimento.data_evento.asc(), CaseMovimento.created_at.asc())
    )).scalars().all()

    if not movimentos:
        return {"case_id": str(case.id), "status": "sem_movimentos", "movimentos": 0}

    contagem = {"novo": 0, "atualizado": 0, "inalterado": 0}
    for mov in movimentos:
        chave_hash = hash_movimento(mov.descricao)
        if not chave_hash:
            continue
        conteudo, extra = _conteudo_movimento(case, mov)
        resultado = await upsert_documento(
            db,
            titulo=f"Andamento DataJud — {case.numero_processo or case.numero_interno or case.id}",
            categoria=CATEGORIA_RAG,
            conteudo=conteudo,
            chave_origem=f"datajud:movimento:{case.id}:{chave_hash}",
            fonte="DataJud/CNJ",
            tribunal=case.tribunal,
            extra=extra,
            client_id=str(case.client_id),
            case_id=str(case.id),
            confianca="media",
            embutir_vetores=embutir_vetores,
        )
        contagem[resultado] = contagem.get(resultado, 0) + 1

    timeline_texto, timeline_extra = _conteudo_timeline(case, movimentos)
    timeline_chave = f"datajud:timeline:{case.id}"
    timeline_resultado = await upsert_documento(
        db,
        titulo=f"Linha do tempo DataJud — {case.numero_processo or case.numero_interno or case.id}",
        categoria=CATEGORIA_RAG,
        conteudo=timeline_texto,
        chave_origem=timeline_chave,
        fonte="DataJud/CNJ",
        tribunal=case.tribunal,
        extra=timeline_extra,
        client_id=str(case.client_id),
        case_id=str(case.id),
        confianca="media",
        embutir_vetores=embutir_vetores,
    )
    contagem[timeline_resultado] = contagem.get(timeline_resultado, 0) + 1
    await db.flush()
    timeline_doc = (await db.execute(
        select(KnowledgeDoc).where(
            KnowledgeDoc.chave_origem == timeline_chave,
            KnowledgeDoc.client_id == case.client_id,
            KnowledgeDoc.vigente.is_(True),
            KnowledgeDoc.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    return {
        "case_id": str(case.id),
        "status": "alimentado",
        "movimentos": len(movimentos),
        "novos": contagem.get("novo", 0),
        "atualizados": contagem.get("atualizado", 0),
        "inalterados": contagem.get("inalterado", 0),
        "timeline": timeline_resultado,
        "timeline_doc_id": str(timeline_doc.id) if timeline_doc else None,
        "deadline_source": False,
        "requires_human_review": True,
    }


async def status_caso(db: AsyncSession, case: Case) -> dict[str, Any]:
    docs = (await db.execute(
        select(KnowledgeDoc).where(
            KnowledgeDoc.case_id == case.id,
            KnowledgeDoc.client_id == case.client_id,
            KnowledgeDoc.chave_origem.like("datajud:%"),
            KnowledgeDoc.vigente.is_(True),
            KnowledgeDoc.deleted_at.is_(None),
        )
    )).scalars().all()
    por_status: dict[str, int] = {}
    for doc in docs:
        status = doc.status_indexacao or "pendente"
        por_status[status] = por_status.get(status, 0) + 1
    timeline = next((d for d in docs if d.chave_origem == f"datajud:timeline:{case.id}"), None)
    return {
        "case_id": str(case.id),
        "alimentado": bool(timeline),
        "documentos_cognitivos": len(docs),
        "por_status_indexacao": por_status,
        "timeline_doc_id": str(timeline.id) if timeline else None,
        "deadline_source": False,
        "requires_human_review": True,
    }


async def alimentar_lote(db: AsyncSession, *, limite: int = 100) -> dict[str, Any]:
    referencias = (await db.execute(
        select(Case.id, Case.numero_interno).where(
            Case.deleted_at.is_(None),
            Case.numero_processo.isnot(None),
        ).order_by(Case.last_synced_at.desc().nullslast()).limit(max(1, min(limite, 500)))
    )).all()
    resumo = {"casos": 0, "alimentados": 0, "sem_movimentos": 0, "erros": 0}
    erro_final: str | None = None
    for case_id, numero_interno in referencias:
        resumo["casos"] += 1
        try:
            case = await db.get(Case, case_id)
            if case is None or case.deleted_at is not None:
                continue
            resultado = await alimentar_caso(db, case, embutir_vetores=False)
            resumo["alimentados" if resultado["status"] == "alimentado" else "sem_movimentos"] += 1
            await db.commit()
        except Exception as exc:
            await db.rollback()
            resumo["erros"] += 1
            erro_final = f"{type(exc).__name__}: {str(exc)[:180]}"
            logger.warning("Feed DataJud falhou para %s: %s", numero_interno or case_id, erro_final)
    status = "sucesso" if not resumo["erros"] else "parcial"
    try:
        await registrar_fonte(db, FONTE_SLUG, "DataJud/CNJ", CATEGORIA_RAG)
        await marcar_execucao(
            db,
            FONTE_SLUG,
            status=status,
            novos=resumo["alimentados"],
            total=resumo["casos"],
            erro=erro_final,
        )
        await db.commit()
    except Exception:
        await db.rollback()
    return {**resumo, "status": status}
