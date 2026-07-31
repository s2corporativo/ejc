"""Dossiê documental canônico do caso.

A fonte da verdade são os originais preservados no GED, seu versionamento e,
quando disponíveis, os metadados de entrada (SHA-256, lote, ordem e páginas
extraídas). Conteúdo produzido por IA nunca integra a camada canônica:
interpretações, teses e resumos permanecem derivados e sujeitos à revisão humana.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import DocConfidencialidade, Document
from app.models.document_intake import DocumentIntakeBatch, DocumentIntakeItem

VERSAO_DOSSIE_DOCUMENTAL = "EJC-DOC-1"
_MAX_TEXTO_CONTEXTO = 24_000
_CONFIDENCIALIDADES_PERMITIDAS_IA = {
    DocConfidencialidade.normal,
    DocConfidencialidade.interno,
}


def _texto_normalizado(valor: Any) -> str:
    return str(valor or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _hash_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _inteiro_seguro(valor: Any, padrao: int = 0) -> int:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return padrao


def _chave_ordenacao(item: dict[str, Any]) -> tuple[str, str, int, str, str]:
    return (
        str(item.get("document_created_at") or item.get("batch_created_at") or ""),
        str(item.get("versao_grupo_id") or item.get("document_id") or ""),
        _inteiro_seguro(item.get("versao"), 1),
        str(item.get("filename") or ""),
        str(item.get("document_id") or ""),
    )


def construir_dossie_documental_canonico(
    itens: Iterable[dict[str, Any]],
    *,
    limite_texto: int = _MAX_TEXTO_CONTEXTO,
) -> dict[str, Any]:
    """Constrói representação determinística, rastreável e sem conteúdo de IA.

    O selo geral é calculado sobre manifesto JSON ordenado contendo os hashes dos
    originais, quando existentes, e de cada página extraída. Cópias com o mesmo
    SHA-256 permanecem registradas no manifesto, mas seu texto não é repetido no
    contexto, evitando que o mesmo fato seja artificialmente superponderado.
    """
    ordenados = sorted((dict(item) for item in itens), key=_chave_ordenacao)
    documentos_vistos: set[str] = set()
    conteudos_vistos: dict[str, str] = {}
    manifesto: list[dict[str, Any]] = []
    blocos_contexto: list[str] = []
    fontes: list[dict[str, Any]] = []
    avisos: list[str] = []
    duplicados_omitidos = 0
    tamanho_contexto = 0
    truncado = False

    def adicionar_contexto(bloco: str) -> None:
        nonlocal tamanho_contexto, truncado
        bloco = bloco.strip()
        if not bloco:
            return
        separador = "\n\n" if blocos_contexto else ""
        restante = max(limite_texto - tamanho_contexto - len(separador), 0)
        if restante <= 0:
            truncado = True
            return
        if len(bloco) > restante:
            blocos_contexto.append(separador + bloco[:restante])
            tamanho_contexto += len(separador) + restante
            truncado = True
            return
        blocos_contexto.append(separador + bloco)
        tamanho_contexto += len(separador) + len(bloco)

    for item in ordenados:
        sha_original = _texto_normalizado(item.get("sha256")).lower()
        document_id = _texto_normalizado(item.get("document_id"))
        if document_id and document_id in documentos_vistos:
            continue
        if document_id:
            documentos_vistos.add(document_id)

        meta = item.get("extraction_meta") or item.get("meta_extracao") or {}
        classificacao = item.get("classification") or item.get("classificacao") or {}
        paginas_brutas = list(meta.get("paginas") or item.get("paginas") or [])
        paginas = sorted(
            paginas_brutas,
            key=lambda pagina: (
                _inteiro_seguro(pagina.get("pagina")),
                _texto_normalizado(pagina.get("texto")),
            ),
        )
        filename = _texto_normalizado(item.get("filename") or item.get("nome")) or "Documento sem nome"
        tipo = _texto_normalizado(classificacao.get("tipo")) or "não classificado"
        status = _texto_normalizado(item.get("extraction_status") or item.get("status_extracao")) or "desconhecido"
        batch_id = _texto_normalizado(item.get("batch_id"))
        source_order = _inteiro_seguro(item.get("source_order"))
        versao = max(_inteiro_seguro(item.get("versao"), 1), 1)
        versao_grupo_id = _texto_normalizado(item.get("versao_grupo_id"))
        versao_anterior_id = _texto_normalizado(item.get("versao_anterior_id"))
        versao_vigente = bool(item.get("versao_vigente", True))

        duplicado_de_documento_id = conteudos_vistos.get(sha_original) if sha_original else None
        if sha_original and not duplicado_de_documento_id and document_id:
            conteudos_vistos[sha_original] = document_id
        if duplicado_de_documento_id:
            duplicados_omitidos += 1

        paginas_manifesto: list[dict[str, Any]] = []
        paginas_com_texto = 0
        cabecalho = (
            f"[FONTE DOCUMENTAL | documento_id={document_id or 'indisponível'} | "
            f"sha256_original={sha_original or 'indisponível'} | lote={batch_id or 'GED'} | "
            f"ordem={source_order} | arquivo={filename} | tipo={tipo} | "
            f"versao={versao} | vigente={'sim' if versao_vigente else 'não'} | status_extracao={status}]"
        )
        adicionar_contexto(cabecalho)

        if duplicado_de_documento_id:
            adicionar_contexto(
                "[CÓPIA DOCUMENTAL — conteúdo idêntico ao documento "
                f"{duplicado_de_documento_id}; texto não repetido no contexto]"
            )

        for pagina in paginas:
            numero = _inteiro_seguro(pagina.get("pagina"))
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
            if not texto or duplicado_de_documento_id:
                continue
            paginas_com_texto += 1
            adicionar_contexto(
                f"[PÁGINA {numero or '?'} | sha256_texto_extraido={hash_pagina}]\n{texto}"
            )
            fontes.append(
                {
                    "document_id": document_id or None,
                    "sha256_original": sha_original or None,
                    "batch_id": batch_id or None,
                    "filename": filename,
                    "tipo": tipo,
                    "versao": versao,
                    "versao_vigente": versao_vigente,
                    "pagina": numero or None,
                    "sha256_texto_extraido": hash_pagina,
                }
            )

        if paginas_com_texto == 0 and not duplicado_de_documento_id:
            avisos.append(f"{filename}: original preservado, mas sem texto extraído utilizável.")
            adicionar_contexto("[SEM TEXTO EXTRAÍDO — consultar o original preservado no GED]")

        manifesto.append(
            {
                "document_id": document_id or None,
                "sha256_original": sha_original or None,
                "duplicado_de_documento_id": duplicado_de_documento_id,
                "batch_id": batch_id or None,
                "source_order": source_order,
                "filename": filename,
                "tipo": tipo,
                "versao": versao,
                "versao_grupo_id": versao_grupo_id or None,
                "versao_anterior_id": versao_anterior_id or None,
                "versao_vigente": versao_vigente,
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

    prefixo = "\n\n".join(
        [
            f"[DOSSIÊ DOCUMENTAL CANÔNICO — {VERSAO_DOSSIE_DOCUMENTAL}]",
            f"Selo SHA-256 do manifesto: {selo}",
            "Regra de leitura: o conteúdo abaixo é transcrição/OCR vinculado ao original; não é resumo, tese ou conclusão da IA.",
        ]
    )
    corpo = "".join(blocos_contexto)
    texto_contexto = f"{prefixo}\n\n{corpo}" if corpo else prefixo
    if len(texto_contexto) > limite_texto:
        texto_contexto = texto_contexto[:limite_texto]
        truncado = True
    if truncado:
        marcador = "\n\n[CONTEÚDO DOCUMENTAL TRUNCADO NO CONTEXTO — consultar as fontes e os originais no GED]"
        texto_contexto = texto_contexto[: max(limite_texto - len(marcador), 0)] + marcador
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
    """Monta o dossiê a partir de todo o GED do caso, respeitando o cofre."""
    documentos = (
        await db.execute(
            select(Document)
            .where(Document.case_id == case_id, Document.deleted_at.is_(None))
            .order_by(Document.created_at.asc(), Document.id.asc())
        )
    ).scalars().all()
    if not documentos:
        return None

    sigilosos_omitidos = [
        doc for doc in documentos
        if doc.confidencialidade not in _CONFIDENCIALIDADES_PERMITIDAS_IA
    ]
    documentos_permitidos = [
        doc for doc in documentos
        if doc.confidencialidade in _CONFIDENCIALIDADES_PERMITIDAS_IA
    ]
    ids_permitidos = [doc.id for doc in documentos_permitidos]

    intake_por_documento: dict[str, tuple[DocumentIntakeItem, DocumentIntakeBatch]] = {}
    if ids_permitidos:
        intake_rows = (
            await db.execute(
                select(DocumentIntakeItem, DocumentIntakeBatch)
                .join(DocumentIntakeBatch, DocumentIntakeBatch.id == DocumentIntakeItem.batch_id)
                .where(
                    DocumentIntakeItem.document_id.in_(ids_permitidos),
                    DocumentIntakeBatch.status == "concluido",
                )
                .order_by(
                    DocumentIntakeBatch.created_at.desc(),
                    DocumentIntakeItem.created_at.desc(),
                    DocumentIntakeItem.id.desc(),
                )
            )
        ).all()
        for item, batch in intake_rows:
            intake_por_documento.setdefault(item.document_id, (item, batch))

    maior_versao_por_grupo: dict[str, int] = {}
    for doc in documentos_permitidos:
        grupo = doc.versao_grupo_id or doc.id
        maior_versao_por_grupo[grupo] = max(
            maior_versao_por_grupo.get(grupo, 0),
            max(int(doc.versao or 1), 1),
        )

    itens: list[dict[str, Any]] = []
    for ordem, doc in enumerate(documentos_permitidos, 1):
        intake = intake_por_documento.get(doc.id)
        item, batch = intake if intake else (None, None)
        if item and item.extraction_meta:
            extraction_meta = item.extraction_meta
            extraction_status = item.extraction_status
            classification = item.classification or {"tipo": doc.tipo}
            sha256 = item.sha256
            source_order = item.source_order
        else:
            texto_ged = _texto_normalizado(doc.ocr_text)
            extraction_meta = {
                "paginas": [
                    {
                        "pagina": 1,
                        "texto": texto_ged,
                        "confianca": None,
                        "metodo": "ocr_ged_sem_paginacao",
                        "requer_revisao": True,
                    }
                ] if texto_ged else [],
                "page_count": 1 if texto_ged else 0,
            }
            extraction_status = "ged_sem_hash" if texto_ged else "ged_sem_texto"
            classification = {"tipo": doc.tipo}
            sha256 = None
            source_order = ordem

        grupo = doc.versao_grupo_id or doc.id
        versao = max(int(doc.versao or 1), 1)
        itens.append(
            {
                "batch_id": batch.id if batch else None,
                "batch_created_at": batch.created_at.isoformat() if batch and batch.created_at else "",
                "document_created_at": doc.created_at.isoformat() if doc.created_at else "",
                "document_id": doc.id,
                "filename": doc.filename,
                "source_order": source_order,
                "sha256": sha256,
                "extraction_status": extraction_status,
                "extraction_meta": extraction_meta,
                "classification": classification,
                "versao": versao,
                "versao_grupo_id": doc.versao_grupo_id,
                "versao_anterior_id": doc.versao_anterior_id,
                "versao_vigente": versao == maior_versao_por_grupo[grupo],
            }
        )

    resultado = construir_dossie_documental_canonico(itens, limite_texto=limite_texto)
    resultado["qtd_documentos_total_ged"] = len(documentos)
    resultado["qtd_documentos_sigilosos_omitidos"] = len(sigilosos_omitidos)
    if sigilosos_omitidos:
        aviso = (
            f"{len(sigilosos_omitidos)} documento(s) em cofre foram omitidos do contexto da IA; "
            "os originais permanecem preservados e acessíveis somente pelo fluxo autorizado."
        )
        resultado["avisos"].insert(0, aviso)
        marcador = f"[AVISO DE SIGILO — {aviso}]\n\n"
        resultado["texto_contexto"] = (marcador + resultado["texto_contexto"])[:limite_texto]
    return resultado
