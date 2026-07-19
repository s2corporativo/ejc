# ── app/services/datajud_cognitive_feed.py ────────────────────────────────────
"""Alimentação cognitiva do EJC a partir de movimentações públicas do DataJud.

Este módulo NÃO cria uma IA paralela e NÃO possui banco próprio. Ele transforma
os andamentos já persistidos em ``case_movimentos`` em documentos versionados do
RAG nativo (``knowledge_docs``/``knowledge_chunks``), sempre vinculados ao
``client_id`` e ``case_id`` do caso.

Regra jurídica central:
    DataJud é fonte oficial de METADADOS processuais, mas o andamento coletado
    não comprova publicação, intimação, ciência nem termo inicial de prazo.
    Portanto, os documentos gerados usam ``deadline_source=False`` e exigem
    revisão humana. O módulo nunca cria ``Deadline``.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case, CaseMovimento
from app.models.rag import KnowledgeDoc
from app.services.ingestion_service import (
    marcar_execucao,
    registrar_fonte,
    upsert_documento,
)

logger = logging.getLogger("ejc.datajud_cognitive_feed")

FONTE_SLUG = "datajud_processos"
CATEGORIA_RAG = "andamento_processual"
AVISO_JURIDICO = (
    "AVISO DE CONFIABILIDADE: o DataJud/CNJ fornece metadados públicos de "
    "tramitação. Este registro não comprova intimação, publicação, ciência, "
    "termo inicial ou vencimento de prazo. Qualquer providência processual deve "
    "ser conferida no DJEN ou no sistema judicial autenticado e validada por "
    "advogado."
)

_RE_HASH = re.compile(r"\s*\[dj:([0-9a-f]{16})\]\s*$", re.I)

# Classificação determinística e conservadora. Serve para recuperação e triagem,
# não para decisão autônoma, cálculo de prazo ou qualificação jurídica definitiva.
_REGRAS: tuple[tuple[str, str, str, str], ...] = (
    (r"senten[çc]a|julgamento\s+(procedente|improcedente)", "sentenca", "alta", "Revisar decisão e avaliar providências cabíveis."),
    (r"ac[oó]rd[aã]o", "acordao", "alta", "Revisar acórdão e avaliar providências cabíveis."),
    (r"decis[aã]o|despacho", "decisao", "alta", "Revisar o teor no sistema oficial."),
    (r"intima[çc][aã]o|cita[çc][aã]o", "possivel_comunicacao", "alta", "Conferir a comunicação oficial; não calcular prazo pelo DataJud."),
    (r"audi[eê]ncia\s+(designada|marcada)|designa[çc][aã]o\s+de\s+audi[eê]ncia", "audiencia", "alta", "Conferir data, modalidade e determinações no sistema oficial."),
    (r"laudo\s+pericial|per[ií]cia", "pericia", "media", "Revisar o evento pericial e documentos relacionados."),
    (r"recurso|apela[çc][aã]o|agravo|embargo", "recurso", "media", "Verificar natureza, autoria e efeito do recurso."),
    (r"arquivamento|baixado\s+definitivamente|tr[aâ]nsito\s+em\s+julgado", "encerramento", "alta", "Conferir situação final e pendências remanescentes."),
    (r"juntada|peti[çc][aã]o", "juntada", "informativa", "Verificar o documento juntado quando relevante."),
    (r"remessa|redistribui[çc][aã]o|distribui[çc][aã]o", "tramitacao", "informativa", "Atualizar a compreensão da tramitação."),
)


def limpar_descricao(descricao: str | None) -> str:
    """Remove apenas o marcador técnico interno, preservando o texto oficial."""
    return _RE_HASH.sub("", descricao or "").strip()


def hash_movimento(descricao: str | None) -> str | None:
    """Extrai a chave de deduplicação gravada pelo sincronizador DataJud."""
    match = _RE_HASH.search(descricao or "")
    return match.group(1).lower() if match else None


def classificar_movimento(descricao: str | None) -> dict[str, str]:
    """Classifica sem IA; a saída é sugestiva e sempre sujeita a revisão."""
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


def _metadados_base(case: Case) -> dict[str, Any]:
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
        "case_id": str(case.id),
        "client_id": str(case.client_id),
        "numero_processo": case.numero_processo,
        "numero_interno": case.numero_interno,
        "area": _valor_enum(case.area),
    }


def _conteudo_movimento(case: Case, mov: CaseMovimento) -> tuple[str, dict[str, Any]]:
    descricao = limpar_descricao(mov.descricao)
    classificacao = classificar_movimento(descricao)
    data_evento = _iso(mov.data_evento)
    texto = (
        f"ANDAMENTO PROCESSUAL — DATAJUD/CNJ\n"
        f"Caso interno: {case.numero_interno or case.id}\n"
        f"Processo: {case.numero_processo or 'não informado'}\n"
        f"Tribunal: {case.tribunal or 'derivado do número CNJ'}\n"
        f"Área: {_valor_enum(case.area) or 'não informada'}\n"
        f"Data do evento: {data_evento or 'não informada'}\n"
        f"Classificação operacional: {classificacao['tipo_evento']}\n"
        f"Severidade operacional: {classificacao['severidade']}\n"
        f"Movimentação oficial: {descricao}\n"
        f"Providência sugerida: {classificacao['providencia_sugerida']}\n\n"
        f"{AVISO_JURIDICO}"
    )
    extra = {
        **_metadados_base(case),
        **classificacao,
        "document_type": "process_movement",
        "movement_id": str(mov.id),
        "movement_date": data_evento,
        "movement_hash": hash_movimento(mov.descricao),
        "original_text_preserved": True,
    }
    return texto, extra


def _conteudo_timeline(case: Case, movimentos: list[CaseMovimento]) -> tuple[str, dict[str, Any]]:
    linhas: list[str] = []
    severidade_max = "informativa"
    ordem = {"informativa": 0, "media": 1, "alta": 2, "critica": 3}
    for mov in movimentos:
        classificacao = classificar_movimento(mov.descricao)
        if ordem.get(classificacao["severidade"], 0) > ordem.get(severidade_max, 0):
            severidade_max = classificacao["severidade"]
        linhas.append(
            f"- {_iso(mov.data_evento) or 'data não informada'} | "
            f"{classificacao['tipo_evento']} | {limpar_descricao(mov.descricao)}"
        )

    ultimo = _iso(movimentos[-1].data_evento) if movimentos else None
    texto = (
        f"LINHA DO TEMPO PROCESSUAL CONSOLIDADA — DATAJUD/CNJ\n"
        f"Caso interno: {case.numero_interno or case.id}\n"
        f"Título: {case.titulo}\n"
        f"Processo: {case.numero_processo or 'não informado'}\n"
        f"Tribunal: {case.tribunal or 'derivado do número CNJ'}\n"
        f"Área: {_valor_enum(case.area) or 'não informada'}\n"
        f"Total de movimentações oficiais indexadas: {len(movimentos)}\n\n"
        f"HISTÓRICO CRONOLÓGICO\n" + "\n".join(linhas) + "\n\n" + AVISO_JURIDICO
    )
    extra = {
        **_metadados_base(case),
        "document_type": "process_timeline",
        "movement_count": len(movimentos),
        "latest_movement_at": ultimo,
        "max_operational_severity": severidade_max,
        "versioning_reason": "timeline_changes",
    }
    return texto, extra


async def _documento_vigente(db: AsyncSession, chave: str) -> KnowledgeDoc | None:
    return (await db.execute(
        select(KnowledgeDoc).where(
            KnowledgeDoc.chave_origem == chave,
            KnowledgeDoc.deleted_at.is_(None),
            KnowledgeDoc.vigente.is_(True),
        )
    )).scalar_one_or_none()


async def alimentar_caso(
    db: AsyncSession,
    case: Case,
    *,
    embutir_vetores: bool = False,
) -> dict[str, Any]:
    """Materializa movimentos e linha do tempo do caso no RAG nativo.

    Idempotência:
      * documento unitário: ``datajud:movimento:{case_id}:{hash}``;
      * linha do tempo: ``datajud:timeline:{case_id}``, com versionamento nativo.

    O commit permanece sob responsabilidade do chamador para que timeline,
    auditoria e RAG sejam atômicos na mesma transação.
    """
    await registrar_fonte(
        db,
        FONTE_SLUG,
        "DataJud/CNJ — metadados de movimentações dos processos do escritório",
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
        return {
            "case_id": str(case.id),
            "movimentos": 0,
            "novos": 0,
            "atualizados": 0,
            "inalterados": 0,
            "timeline": None,
            "status": "sem_movimentos",
        }

    contagem = {"novo": 0, "atualizado": 0, "inalterado": 0}
    for mov in movimentos:
        chave_hash = hash_movimento(mov.descricao)
        # Registros legados sem marcador não entram no feed automático: evita
        # atribuir falsamente origem DataJud a notas manuais.
        if not chave_hash:
            continue
        conteudo, extra = _conteudo_movimento(case, mov)
        resultado = await upsert_documento(
            db,
            titulo=(
                f"Andamento DataJud — {case.numero_processo or case.numero_interno or case.id} "
                f"— {_iso(mov.data_evento) or 'sem data'}"
            ),
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
    timeline_doc = await _documento_vigente(db, timeline_chave)

    return {
        "case_id": str(case.id),
        "movimentos": len(movimentos),
        "novos": contagem.get("novo", 0),
        "atualizados": contagem.get("atualizado", 0),
        "inalterados": contagem.get("inalterado", 0),
        "timeline": timeline_resultado,
        "timeline_doc_id": str(timeline_doc.id) if timeline_doc else None,
        "status_indexacao": getattr(timeline_doc, "status_indexacao", None),
        "status": "alimentado",
        "deadline_source": False,
        "requires_human_review": True,
    }


async def status_caso(db: AsyncSession, case: Case) -> dict[str, Any]:
    """Estado auditável do feed cognitivo do caso, sem expor conteúdo sensível."""
    prefixo = f"datajud:%:{case.id}:%"
    docs = (await db.execute(
        select(KnowledgeDoc).where(
            KnowledgeDoc.case_id == case.id,
            KnowledgeDoc.chave_origem.like("datajud:%"),
            KnowledgeDoc.deleted_at.is_(None),
            KnowledgeDoc.vigente.is_(True),
        )
    )).scalars().all()
    por_status: dict[str, int] = {}
    for doc in docs:
        status = doc.status_indexacao or "pendente"
        por_status[status] = por_status.get(status, 0) + 1
    timeline = next((d for d in docs if d.chave_origem == f"datajud:timeline:{case.id}"), None)
    return {
        "case_id": str(case.id),
        "documentos_cognitivos": len(docs),
        "por_status_indexacao": por_status,
        "timeline_doc_id": str(timeline.id) if timeline else None,
        "timeline_atualizada_em": _iso(getattr(timeline, "atualizado_em", None)) if timeline else None,
        "alimentado": bool(timeline),
        "categoria": CATEGORIA_RAG,
        "isolamento": "client_id+case_id",
        "deadline_source": False,
        "requires_human_review": True,
    }


async def alimentar_lote(
    db: AsyncSession,
    *,
    limite: int = 100,
    embutir_vetores: bool = False,
) -> dict[str, Any]:
    """Backfill idempotente dos casos ativos; falha de um caso não aborta o lote."""
    casos = (await db.execute(
        select(Case).where(
            Case.deleted_at.is_(None),
            Case.numero_processo.isnot(None),
        ).order_by(Case.last_synced_at.desc().nullslast()).limit(max(1, min(limite, 500)))
    )).scalars().all()

    resumo = {
        "casos": 0,
        "alimentados": 0,
        "sem_movimentos": 0,
        "novos": 0,
        "atualizados": 0,
        "inalterados": 0,
        "erros": 0,
    }
    erro_final: str | None = None
    for case in casos:
        resumo["casos"] += 1
        try:
            resultado = await alimentar_caso(
                db, case, embutir_vetores=embutir_vetores
            )
            if resultado["status"] == "sem_movimentos":
                resumo["sem_movimentos"] += 1
            else:
                resumo["alimentados"] += 1
            for campo in ("novos", "atualizados", "inalterados"):
                resumo[campo] += int(resultado.get(campo, 0))
            await db.commit()
        except Exception as exc:  # isolamento por caso
            await db.rollback()
            resumo["erros"] += 1
            erro_final = f"{type(exc).__name__}: {str(exc)[:180]}"
            logger.warning(
                "Feed DataJud falhou para caso %s: %s",
                case.numero_interno or case.id,
                erro_final,
            )

    status = "sucesso" if not resumo["erros"] else (
        "parcial" if resumo["alimentados"] or resumo["sem_movimentos"] else "erro"
    )
    try:
        await registrar_fonte(
            db,
            FONTE_SLUG,
            "DataJud/CNJ — metadados de movimentações dos processos do escritório",
            CATEGORIA_RAG,
        )
        await marcar_execucao(
            db,
            FONTE_SLUG,
            status=status,
            novos=resumo["novos"] + resumo["atualizados"],
            total=resumo["casos"],
            erro=erro_final,
        )
        await db.commit()
    except Exception as exc:  # telemetria não invalida o lote já persistido
        await db.rollback()
        logger.warning("Falha ao registrar métricas do feed DataJud: %s", exc)

    return {**resumo, "status": status, "embutir_vetores": embutir_vetores}
