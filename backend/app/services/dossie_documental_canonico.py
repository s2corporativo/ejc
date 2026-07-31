"""Dossiê documental canônico do caso.

A fonte da verdade são os originais preservados no GED e os metadados imutáveis de
entrada (document_id, SHA-256, lote, ordem e páginas extraídas). O texto produzido
por IA nunca integra o dossiê canônico: interpretações, teses e resumos permanecem
camadas derivadas e sujeitas à revisão humana.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_intake import DocumentIntakeBatch, DocumentIntakeItem

VERSAO_DOSSIE_DOCUMENTAL = "EJC-DOC-1"
_MAX_TEXTO_CONTEXTO = 24_000


def _texto_normalizado(valor: Any) -> str:
    return str(valor or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _hash_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _chave_ordenacao(item: dict[str, Any]) -> tuple[str, str, int, str, str]:
    return (
        str(item.get("batch_created_at") or ""),
        str(item.get("batch_id") or ""),
        int(item.get("source_order") or 0),
        str(item.get("filename") or ""),
        str(item.get("document_id") or ""),
    )


def construir_dossie_documental_canonico(
    itens: Iterable[dict[str, Any]],
    *,
    limite_texto: int = _MAX_TEXTO_CONTEXTO,
) -> dict[str, Any]:
    """Constrói uma representação determinística, rastreável e sem conteúdo de IA.

    O selo geral é calculado sobre um manifesto JSON ordenado contendo os hashes dos
    originais e de cada página extraída. Assim, a integridade documental permanece
    verificável mesmo quando o texto destinado ao contexto da IA precisa ser truncado.
    """
    ordenados = sorted((dict(item) for item in itens), key=_chave_ordenacao)
    vistos: set[str] = set()
    manifesto: list[dict[str, Any]] = []
    blocos: list[str] = []
    fontes: list[dict[str, Any]] = []
    avisos: list[str] = []
    duplicados_omitidos = 0

    for item in ordenados:
        sha_original = _texto_normalizado(item.get("sha256")).lower()
        document_id = _texto_normalizado(item.get("document_id"))
        chave_unica = sha_original or document_id
        if chave_unica and chave_unica in vistos:
            duplicados_omitidos += 1
            continue
        if chave_unica:
            vistos.add(chave_unica)

        meta = item.get("extraction_meta") or item.get("meta_extracao") or {}
        classificacao = item.get("classification") or item.get("classificacao") or {}
        paginas_brutas = list(meta.get("paginas") or item.get("paginas") or [])
        paginas = sorted(
            paginas_brutas,
            key=lambda pagina: (int(pagina.get("pagina") or 0), _texto_normalizado(pagina.get("texto"))),
        )
        filename = _texto_normalizado(item.get("filename") or item.get("nome")) or "Documento sem nome"
        tipo = _texto_normalizado(classificacao.get("tipo")) or "não classificado"
        status = _texto_normalizado(item.get("extraction_status") or item.get("status_extracao")) or "desconhecido"
        batch_id = _texto_normalizado(item.get("batch_id"))
        source_order = int(item.get("source_order") or 0)

        paginas_manifesto: list[dict[str, Any]] = []
        paginas_com_texto = 0
        cabecalho = (
            f"[FONTE DOCUMENTAL | documento_id={document_id or 'indisponível'} | "
            f"sha256_original={sha_original or 'indisponível'} | lote={batch_id or 'indisponível'} | "
            f"ordem={source_order} | arquivo={filename} | tipo={tipo} | status_extracao={status}]"
        )
        blocos.append(cabecalho)

        for pagina in paginas:
            numero = int(pagina.get("pagina") or 0)
            texto = _texto_normalizado(pagina.get("texto"))
            hash_pagina = _hash_texto(texto)
            paginas_manifesto.append(
                {
                    "pagina": numero,
                    "sha256_texto_extraido": hash_pagina,
                    "confianca": pagina.get("confianca"),
                    "metodo": pagina.get("metodo"),
                    "requer_revisao": bool(pagina.get("requer_revisao")),
                }
            )
            if not texto:
                continue
            paginas_com_texto += 1
            blocos.append(
                f"[PÁGINA {numero or '?'} | sha256_texto_extraido={hash_pagina}]\n{texto}"
            )
            fontes.append(
                {
                    "document_id": document_id or None,
                    "sha256_original": sha_original or None,
                    "batch_id": batch_id or None,
                    "filename": filename,
                    "tipo": tipo,
                    "pagina": numero or None,
                    "sha256_texto_extraido": hash_pagina,
                }
            )

        if paginas_com_texto == 0:
            avisos.append(f"{filename}: original preservado, mas sem texto extraído utilizável.")
            blocos.append("[SEM TEXTO EXTRAÍDO — consultar o original preservado no GED]")

        manifesto.append(
            {
                "document_id": document_id or None,
                "sha256_original": sha_original or None,
                "batch_id": batch_id or None,
                "source_order": source_order,
                "filename": filename,
                "tipo": tipo,
                "status_extracao": status,
                "paginas": paginas_manifesto,
            }
        )

    manifesto_canonico = {
        "versao": VERSAO_DOSSIE_DOCUMENTAL,
        "documentos": manifesto,
    }
    serializado = json.dumps(
        manifesto_canonico,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    selo = _hash_texto(serializado)

    prefixo = [
        f"[DOSSIÊ DOCUMENTAL CANÔNICO — {VERSAO_DOSSIE_DOCUMENTAL}]",
        f"Selo SHA-256 do manifesto: {selo}",
        "Regra de leitura: o conteúdo abaixo é transcrição/OCR vinculado ao original; não é resumo, tese ou conclusão da IA.",
    ]
    texto_integral = "\n\n".join(prefixo + blocos)
    truncado = len(texto_integral) > limite_texto
    texto_contexto = texto_integral[:limite_texto]
    if truncado:
        texto_contexto += "\n\n[CONTEÚDO DOCUMENTAL TRUNCADO NO CONTEXTO — consultar as fontes e os originais no GED]"
        avisos.append("O texto documental excedeu o limite do contexto; o manifesto e os originais permanecem íntegros.")

    return {
        "versao": VERSAO_DOSSIE_DOCUMENTAL,
        "sha256_manifesto": selo,
        "manifesto": manifesto,
        "texto_contexto": texto_contexto,
        "fontes": fontes,
        "qtd_documentos": len(manifesto),
        "qtd_paginas_com_texto": len(fontes),
        "duplicados_omitidos": duplicados_omitidos,
        "truncado": truncado,
        "avisos": avisos,
    }


async def montar_dossie_documental_canonico(
    db: AsyncSession,
    case_id: str,
    *,
    limite_texto: int = _MAX_TEXTO_CONTEXTO,
) -> dict[str, Any] | None:
    """Carrega todos os lotes concluídos do caso e monta o dossiê canônico."""
    rows = (
        await db.execute(
            select(DocumentIntakeBatch, DocumentIntakeItem)
            .join(DocumentIntakeItem, DocumentIntakeItem.batch_id == DocumentIntakeBatch.id)
            .where(
                DocumentIntakeBatch.case_id == case_id,
                DocumentIntakeBatch.status == "concluido",
            )
            .order_by(
                DocumentIntakeBatch.created_at.asc(),
                DocumentIntakeBatch.id.asc(),
                DocumentIntakeItem.source_order.asc(),
                DocumentIntakeItem.created_at.asc(),
                DocumentIntakeItem.id.asc(),
            )
        )
    ).all()
    if not rows:
        return None

    itens = []
    for batch, item in rows:
        itens.append(
            {
                "batch_id": batch.id,
                "batch_created_at": batch.created_at.isoformat() if batch.created_at else "",
                "document_id": item.document_id,
                "filename": item.filename,
                "source_order": item.source_order,
                "sha256": item.sha256,
                "extraction_status": item.extraction_status,
                "extraction_meta": item.extraction_meta or {},
                "classification": item.classification or {},
            }
        )

    return construir_dossie_documental_canonico(itens, limite_texto=limite_texto)
