"""API transversal da Entrada Universal de Documentos."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.ownership import is_gestao, verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import ROLE_LEVEL, get_current_user
from app.models.audit_log import criar_audit_log
from app.models.client import Client
from app.models.document import DocConfidencialidade, Document
from app.models.document_intake import DocumentIntakeBatch, DocumentIntakeItem
from app.models.user import User
from app.routers.documents import _validar_conteudo
from app.services.ai.core.orchestrator import orchestrator
from app.services.entrada_universal_service import (
    CATALOGO_DOCUMENTAL, EXTENSOES_SUPORTADAS, MAX_ARQUIVOS, MAX_BYTES_LOTE,
    avaliar_prontidao, classificar_documento, comparar_documentos, expandir_arquivo,
    extrair_paginas, manifesto_pacote, montar_dossie, resumo_documentos, sha256_bytes,
)

logger = logging.getLogger("ejc.entrada_universal.router")
settings = get_settings()
router = APIRouter(prefix="/entrada-universal", tags=["Entrada Universal de Documentos"])

_SCHEMA_IA = """
Responda APENAS com JSON válido:
{
  "tipo_documento_principal": null, "fase": null, "area": null, "orgao_ou_instituicao": null,
  "identificacao_processual": {"numero_processo": null, "tribunal": null, "comarca": null, "vara": null},
  "partes": {"autor": null, "reu": null, "terceiros": []},
  "dados_pessoais": {"nome": null, "cpf": null, "cnpj": null},
  "resumo_executivo": {"fatos": null, "situacao": null, "providencia_principal": null},
  "datas_eventos": [{"evento": null, "data": null, "documento": null, "pagina": null, "trecho_literal": null, "confianca": 0.0}],
  "prazo": {"termo_inicial": null, "data_expressa": null, "regra": "verificar", "requer_confirmacao_humana": true},
  "matriz_vicios_teses": [{"vicio_ou_tese": null, "fato": null, "prova": null, "fundamento": "verificar", "forca": 0, "risco": "medio"}],
  "clausulas_contratuais": [],
  "dados_bancarios": {"taxa_mensal": null, "taxa_anual": null, "cet": null, "capitalizacao": null, "amortizacao": null, "tarifas": [], "seguros": [], "iof": null},
  "documentos_faltantes_adicionais": [],
  "estrategia": {"objetivo": null, "medidas": [], "pedidos": [], "provas_prioritarias": [], "riscos": [], "proximos_passos": []},
  "alertas": []
}
REGRAS: não invente dados, datas, fundamentos ou precedentes; cite documento e página; prazo e abusividade nunca são conclusões automáticas; toda saída é rascunho.
"""


class PrepararPacoteRequest(BaseModel):
    salvar_no_caso: bool = False


def _role_value(user: User) -> str:
    return getattr(user.role, "value", user.role)


def _parse_json(texto: str) -> dict[str, Any] | None:
    if not texto:
        return None
    try:
        value = json.loads(texto)
        return value if isinstance(value, dict) else None
    except Exception:
        match = re.search(r"\{.*\}", texto, re.DOTALL)
        if not match:
            return None
        try:
            value = json.loads(match.group(0))
            return value if isinstance(value, dict) else None
        except Exception:
            return None


async def _acesso_batch(db: AsyncSession, cu: User, batch_id: str) -> DocumentIntakeBatch:
    batch = (await db.execute(select(DocumentIntakeBatch).where(DocumentIntakeBatch.id == batch_id))).scalar_one_or_none()
    if not batch:
        raise HTTPException(404, "Lote de importação não encontrado")
    if batch.case_id:
        await verificar_acesso_caso(db, cu, batch.case_id)
    elif not is_gestao(cu) and batch.created_by != cu.id:
        raise HTTPException(403, "Sem permissão para este lote")
    return batch


async def _buscar_duplicado(db: AsyncSession, *, sha256: str, case_id: str | None,
                            client_id: str | None, user_id: str) -> DocumentIntakeItem | None:
    stmt = (select(DocumentIntakeItem)
            .join(DocumentIntakeBatch, DocumentIntakeBatch.id == DocumentIntakeItem.batch_id)
            .where(DocumentIntakeItem.sha256 == sha256)
            .order_by(DocumentIntakeItem.created_at.desc()).limit(1))
    if case_id:
        stmt = stmt.where(DocumentIntakeBatch.case_id == case_id)
    elif client_id:
        stmt = stmt.where(DocumentIntakeBatch.client_id == client_id)
    else:
        stmt = stmt.where(DocumentIntakeBatch.created_by == user_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def _salvar_original(db: AsyncSession, *, batch: DocumentIntakeBatch, virtual: dict[str, Any],
                           ordem: int, conf: DocConfidencialidade, cu: User) -> tuple[Document, DocumentIntakeItem]:
    """Persiste o original e metadados pendentes antes de qualquer OCR/IA."""
    ext, raw = virtual["extensao"], virtual["conteudo"]
    mime_real = _validar_conteudo(ext, raw)
    agora = datetime.now(timezone.utc)
    subdir = f"{agora.year}/{agora.month:02d}"
    os.makedirs(f"{settings.UPLOAD_DIR}/{subdir}", exist_ok=True)
    doc_id = str(uuid4())
    filepath = f"{subdir}/{doc_id}{ext}"
    async with aiofiles.open(f"{settings.UPLOAD_DIR}/{filepath}", "wb") as target:
        await target.write(raw)
    doc = Document(
        id=doc_id, titulo=virtual["nome"][:255], tipo=None,
        descricao=f"Entrada Universal — lote {batch.id}", filename=virtual["nome"][:255],
        filepath=filepath, mimetype=mime_real, size_bytes=len(raw), ocr_text=None,
        confidencialidade=conf, case_id=batch.case_id, client_id=batch.client_id, uploaded_by=cu.id,
    )
    item = DocumentIntakeItem(
        id=str(uuid4()), batch_id=batch.id, document_id=doc_id, filename=virtual["nome"][:255],
        original_filename=virtual["nome_origem"][:500], extension=ext, mimetype=mime_real,
        size_bytes=len(raw), sha256=sha256_bytes(raw), source_order=ordem, extraction_status="pendente",
    )
    db.add_all([doc, item])
    await criar_audit_log(db, cu.id, _role_value(cu), "UPLOAD_UNIVERSAL", "documents", doc_id,
                          detalhes=f"{virtual['nome']} | lote {batch.id}")
    await db.commit()  # preservação intencional antes do processamento
    await db.refresh(doc); await db.refresh(item)
    return doc, item


async def _analisar_ia(db: AsyncSession, cu: User, *, modalidade: str | None,
                       case_id: str | None, dossie: str, deterministico: dict[str, Any]) -> dict[str, Any]:
    if len(dossie.strip()) < 40:
        return {"alertas": ["Não houve texto suficiente para interpretação por IA."], "requer_revisao_humana": True}
    prompt = (
        "Atue como analista jurídico brasileiro sênior. Você recebeu um PACOTE DOCUMENTAL com cada documento e página identificados. "
        "Classifique fase, ato a enfrentar, datas literais, lacunas, vícios, teses, provas e providência. Compare os documentos.\n\n"
        f"MODALIDADE: {modalidade or 'geral/automática'}\n"
        f"RESULTADO DETERMINÍSTICO: {json.dumps(deterministico, ensure_ascii=False)[:10000]}\n"
        f"{_SCHEMA_IA}\n\nDOSSIÊ:\n{dossie[:36000]}"
    )
    try:
        nucleo = await orchestrator.run(
            db=db, user=cu, task_type="document_analysis", domain=f"entrada_universal:{modalidade or 'geral'}",
            mensagem=prompt, case_id=case_id, usar_rag=True, nivel_inteligencia="alto",
        )
        bruto = str(nucleo.get("conteudo") or "")
        parsed = _parse_json(bruto) or {"resumo_executivo": {"fatos": bruto[:4000]}}
        parsed.update({"fontes": nucleo.get("fontes", []), "citacoes": nucleo.get("citacoes", []),
                       "alertas_nucleo": nucleo.get("alertas", []), "modelo": nucleo.get("modelo"),
                       "provider": nucleo.get("provider"), "log_id": nucleo.get("log_id"),
                       "requer_revisao_humana": True})
        return parsed
    except Exception as exc:
        logger.warning("Análise do lote pelo núcleo falhou: %s", exc)
        return {"alertas": ["A interpretação por IA ficou indisponível; a extração determinística foi preservada."],
                "requer_revisao_humana": True}


@router.get("/meta")
async def meta(cu: User = Depends(get_current_user)):
    if ROLE_LEVEL.get(_role_value(cu), 0) < ROLE_LEVEL["estagiario"]:
        raise HTTPException(403, "Acesso restrito à equipe jurídica")
    return {"formatos": sorted(EXTENSOES_SUPORTADAS), "multiplos_arquivos": True, "zip": True,
            "max_arquivos": MAX_ARQUIVOS, "max_lote_mb": MAX_BYTES_LOTE // 1024 // 1024,
            "fluxo": ["persistir_original", "hash_e_duplicidade", "ocr_por_pagina", "classificar", "comparar",
                      "avaliar_prontidao", "analise_juridica", "preparar_pacote"],
            "modalidades": list(CATALOGO_DOCUMENTAL),
            "aviso": "Toda classificação, prazo, tese e peça exige confirmação humana."}


async def ingerir_arquivos_lote(
    db: AsyncSession, cu: User, *, batch: DocumentIntakeBatch,
    files: list[UploadFile], conf: DocConfidencialidade,
    modalidade: str | None = None, case_id: str | None = None,
    client_id: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Núcleo do pipeline de arquivos (expandir → limites → persistir original →
    hash/dedup → OCR → classificar), COMPARTILHADO entre /entrada-universal/
    processar e /entrada/analisar (Entrada Única). Retorna (processados,
    total_bytes) no mesmo formato consumido por montar_dossie/resumo_documentos."""
    total_bytes, virtuais = 0, []
    for uploaded in files:
        raw = await uploaded.read()
        try:
            expandidos = expandir_arquivo(uploaded.filename or "documento", raw, uploaded.content_type)
        except ValueError as exc:
            raise HTTPException(415, str(exc)) from exc
        for virtual in expandidos:
            total_bytes += len(virtual["conteudo"])
            if total_bytes > MAX_BYTES_LOTE:
                raise HTTPException(413, "Lote excede 120 MB")
            virtuais.append(virtual)
    if len(virtuais) > MAX_ARQUIVOS:
        raise HTTPException(413, f"Lote excede {MAX_ARQUIVOS} documentos")

    processados: list[dict[str, Any]] = []
    for ordem, virtual in enumerate(virtuais, 1):
        digest = sha256_bytes(virtual["conteudo"])
        duplicado = await _buscar_duplicado(db, sha256=digest, case_id=case_id, client_id=client_id, user_id=cu.id)
        if duplicado:
            item = DocumentIntakeItem(
                id=str(uuid4()), batch_id=batch.id, document_id=duplicado.document_id,
                filename=virtual["nome"][:255], original_filename=virtual["nome_origem"][:500],
                extension=virtual["extensao"], mimetype=virtual["mimetype"], size_bytes=len(virtual["conteudo"]),
                sha256=digest, source_order=ordem, duplicate_of_document_id=duplicado.document_id,
                extraction_status="duplicado", page_count=duplicado.page_count,
                extraction_meta=duplicado.extraction_meta, classification=duplicado.classification,
            )
            db.add(item); await db.commit()
        else:
            doc, item = await _salvar_original(db, batch=batch, virtual=virtual, ordem=ordem, conf=conf, cu=cu)
            try:
                # OCR em thread (não bloqueia o event loop) — mesmo padrão de documents.upload.
                meta_extracao = await asyncio.to_thread(
                    extrair_paginas, virtual["conteudo"], virtual["extensao"], item.mimetype
                )
                classificacao = classificar_documento(virtual["nome"], meta_extracao.get("texto", ""), modalidade)
                item.extraction_status = "concluido" if meta_extracao.get("texto") else "sem_texto"
                item.page_count = int(meta_extracao.get("page_count") or 0)
                item.extraction_meta, item.classification = meta_extracao, classificacao
                doc.ocr_text, doc.tipo = meta_extracao.get("texto") or None, classificacao.get("tipo")
                doc.descricao = f"Entrada Universal — lote {batch.id}; confiança média {meta_extracao.get('confianca_media', 0):.0%}"
            except Exception as exc:
                logger.warning("Extração falhou para %s: %s", virtual["nome"], exc)
                item.extraction_status = "erro"
                item.extraction_meta = {"paginas": [], "page_count": 0, "confianca_media": 0, "avisos": [str(exc)[:300]]}
                item.classification = {"tipo": "outro_documento", "nome": "Não classificado", "confianca": 0, "metodo": "falha_extracao"}
            await db.commit()
        processados.append({"id": item.id, "document_id": item.document_id, "filename": item.filename,
                            "source_order": ordem, "sha256": item.sha256,
                            "duplicate_of_document_id": item.duplicate_of_document_id,
                            "extraction_status": item.extraction_status, "page_count": item.page_count,
                            "extraction_meta": item.extraction_meta or {}, "classification": item.classification or {}})
    return processados, total_bytes


@router.post("/processar", dependencies=[Depends(rate_limit("entrada-universal-processar", 6))])
async def processar(
    files: list[UploadFile] = File(default=[]), modalidade: Optional[str] = Form(None),
    case_id: Optional[str] = Form(None), client_id: Optional[str] = Form(None),
    texto: Optional[str] = Form(None), confidencialidade: str = Form("normal"),
    db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user),
):
    if ROLE_LEVEL.get(_role_value(cu), 0) < ROLE_LEVEL["estagiario"]:
        raise HTTPException(403, "Acesso restrito à equipe jurídica")
    if modalidade and modalidade not in CATALOGO_DOCUMENTAL:
        raise HTTPException(422, f"Modalidade inválida: {modalidade}")
    if not files and len((texto or "").strip()) < 40:
        raise HTTPException(422, "Envie ao menos um arquivo ou informe texto suficiente")
    try:
        conf = DocConfidencialidade(confidencialidade)
    except ValueError:
        raise HTTPException(422, "Confidencialidade inválida")
    if case_id:
        caso = await verificar_acesso_caso(db, cu, case_id)
        if client_id and client_id != caso.client_id:
            raise HTTPException(422, "client_id diverge do cliente do caso")
        client_id = caso.client_id
    elif client_id:
        cliente = (await db.execute(select(Client).where(Client.id == client_id, Client.deleted_at.is_(None)))).scalar_one_or_none()
        if not cliente:
            raise HTTPException(404, "Cliente não encontrado")
        if not is_gestao(cu):
            raise HTTPException(403, "Vinculação avulsa a cliente exige perfil de gestão")

    batch = DocumentIntakeBatch(id=str(uuid4()), case_id=case_id, client_id=client_id,
                                modalidade=modalidade, status="processando", created_by=cu.id)
    db.add(batch); await db.commit()
    try:
        processados, total_bytes = await ingerir_arquivos_lote(
            db, cu, batch=batch, files=files, conf=conf,
            modalidade=modalidade, case_id=case_id, client_id=client_id,
        )

        dossie = montar_dossie(processados, texto)
        prontidao = avaliar_prontidao(modalidade, processados)
        comparacoes = comparar_documentos(processados)
        deterministico = {"prontidao": prontidao, "comparacoes": comparacoes,
                           "documentos": resumo_documentos(processados)}
        analise_ia = await _analisar_ia(db, cu, modalidade=modalidade, case_id=case_id,
                                        dossie=dossie, deterministico=deterministico)
        faltantes = list(dict.fromkeys(prontidao["documentos_faltantes"] + list(analise_ia.get("documentos_faltantes_adicionais") or [])))
        resultado = {
            "ok": True, "batch_id": batch.id, "modalidade": modalidade, "status": "concluido",
            "nivel_prontidao": prontidao["nivel"], "prontidao": prontidao,
            "documentos_faltantes": faltantes, "documentos": deterministico["documentos"],
            "comparacoes": comparacoes, "analise_ia": analise_ia,
            "classificacao": {"area": analise_ia.get("area"), "fase": analise_ia.get("fase"),
                              "tipo_documento": analise_ia.get("tipo_documento_principal"), "requer_confirmacao_humana": True},
            "identificacao_processual": analise_ia.get("identificacao_processual") or {},
            "partes": analise_ia.get("partes") or {}, "dados_pessoais": analise_ia.get("dados_pessoais") or {},
            "resumo_executivo": analise_ia.get("resumo_executivo") or {}, "estrategia": analise_ia.get("estrategia") or {},
            "matriz_vicios_teses": analise_ia.get("matriz_vicios_teses") or [], "datas_eventos": analise_ia.get("datas_eventos") or [],
            "prazo": analise_ia.get("prazo") or {"requer_confirmacao_humana": True},
            "dados_bancarios": analise_ia.get("dados_bancarios") or {},
            "pacote": manifesto_pacote(modalidade, prontidao), "texto_consolidado": dossie,
            "revisao_obrigatoria": True,
            "aviso": "Originais preservados no GED. OCR, classificação, prazos e estratégia exigem revisão humana.",
        }
        batch.status, batch.nivel_prontidao = "concluido", prontidao["nivel"]
        batch.document_count, batch.total_bytes, batch.resultado = len(processados), total_bytes, resultado
        await db.commit()
        return resultado
    except HTTPException:
        await db.rollback()  # limpa transação pendente antes de reusar a sessão
        batch.status = "erro"; await db.commit(); raise
    except Exception as exc:
        await db.rollback()  # limpa transação pendente antes de reusar a sessão
        batch.status = "erro"; await db.commit()
        logger.exception("Falha no lote universal %s", batch.id)
        raise HTTPException(500, f"Falha ao processar o lote: {str(exc)[:180]}")


@router.get("/{batch_id}")
async def obter_lote(batch_id: str, db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    batch = await _acesso_batch(db, cu, batch_id)
    return batch.resultado or {"batch_id": batch.id, "status": batch.status, "nivel_prontidao": batch.nivel_prontidao}


@router.post("/{batch_id}/preparar-pacote")
async def preparar_pacote(batch_id: str, req: PrepararPacoteRequest,
                          db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    batch = await _acesso_batch(db, cu, batch_id)
    resultado = dict(batch.resultado or {})
    prontidao = resultado.get("prontidao") or {"nivel": batch.nivel_prontidao or "apto_com_ressalvas"}
    pacote = manifesto_pacote(batch.modalidade, prontidao)
    saida = {"batch_id": batch.id, "case_id": batch.case_id, "nivel_prontidao": prontidao.get("nivel"),
             "itens": pacote, "bloqueios": [i for i in pacote if i["status"] == "bloqueado"],
             "orientacao": "Confirme estratégia, documentos, prazo e cálculos. A peça segue pelo Motor de Peça.",
             "revisao_obrigatoria": True}
    if req.salvar_no_caso and batch.case_id:
        from app.models.case import CaseMovimento
        resumo = (f"ENTRADA UNIVERSAL — lote {batch.id}\nProntidão: {prontidao.get('nivel')}\n"
                  f"Documentos: {batch.document_count}\nPendências: {', '.join(resultado.get('documentos_faltantes') or []) or 'nenhuma identificada'}\n"
                  "Pacote preparado como rascunho; revisão humana obrigatória.")
        db.add(CaseMovimento(id=str(uuid4()), case_id=batch.case_id, tipo="ia", descricao=resumo[:8000], created_by=cu.id))
        await db.commit(); saida["salvo_no_caso"] = True
    return saida
