# ── app/services/processo_eletronico_document_mapper.py ─────────────────────
# Mapeia a resposta consultarProcesso do MNI (dadosBasicos, movimento[],
# documento[]) para o domínio EJC: atualiza Case, grava andamentos
# (CaseMovimento) e cria documentos no GED (Document), respeitando o
# nivelSigilo do MNI ao decidir a confidencialidade do documento no EJC.
#
# Idempotência: dedup por idDocumento(tribunal) via
# DocumentoProcessoEletronicoDedup — reprocessar a mesma consulta nunca
# recria o mesmo documento (Fase A, requisito da task Celery).
from __future__ import annotations

import hashlib
import base64
import logging
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.case import Case, CaseMovimento
from app.models.document import Document, DocConfidencialidade
from app.models.processo_eletronico import DocumentoProcessoEletronicoDedup
from app.services.mni_connector import ConsultaProcessoResultado
from app.services.tpu_translator import (
    traduzir_assunto, traduzir_classe, traduzir_movimento,
)

logger = logging.getLogger("ejc.mni.mapper")

# Mapa nivelSigilo (MNI) → DocConfidencialidade (EJC). Sigilo 0 = público;
# quanto maior, mais restrito. Conservador por padrão: nível desconhecido
# nunca vira "normal" (nunca afrouxa sigilo por omissão).
_MAPA_SIGILO: dict[int, DocConfidencialidade] = {
    0: DocConfidencialidade.normal,
    1: DocConfidencialidade.interno,
    2: DocConfidencialidade.restrito,
    3: DocConfidencialidade.confidencial,
    4: DocConfidencialidade.segredo_justica,
    5: DocConfidencialidade.segredo_justica,
}


def mapear_confidencialidade(nivel_sigilo: Any) -> DocConfidencialidade:
    try:
        nivel = int(nivel_sigilo)
    except (TypeError, ValueError):
        # Sigilo não informado/ilegível — trata como o mais restrito exigido
        # pela política do GED (nunca assume "normal" por omissão).
        return DocConfidencialidade.confidencial
    return _MAPA_SIGILO.get(nivel, DocConfidencialidade.confidencial)


def _get(d: dict[str, Any], *chaves: str, default: Any = None) -> Any:
    """Busca a primeira chave presente — a serialização do zeep preserva o
    nome do XSD, que varia entre implementações de tribunal (camelCase vs
    PascalCase, por ex.)."""
    for chave in chaves:
        if chave in d and d[chave] is not None:
            return d[chave]
    return default


def _extrair_binario(doc: dict[str, Any]) -> bytes | None:
    conteudo = _get(doc, "conteudo", "Conteudo")
    if conteudo is None:
        return None
    if isinstance(conteudo, dict):
        conteudo = _get(conteudo, "conteudo", "Conteudo", "value")
    if conteudo is None:
        return None
    if isinstance(conteudo, bytes):
        return conteudo
    if isinstance(conteudo, str):
        try:
            return base64.b64decode(conteudo)
        except Exception:  # noqa: BLE001 — conteúdo não-base64 é tratado como ausente
            return None
    return None


async def _atualizar_dados_basicos(case: Case, dados_basicos: dict[str, Any]) -> None:
    """Atualiza campos do Case a partir de dadosBasicos — nunca sobrescreve
    com vazio o que já existia (consulta parcial do tribunal não deve apagar
    dado bom já cadastrado)."""
    classe = _get(dados_basicos, "classeProcessual", "classe")
    orgao = _get(dados_basicos, "orgaoJulgador", "nomeOrgaoJulgador")
    valor_causa = _get(dados_basicos, "valorCausa")

    if orgao:
        orgao_nome = orgao.get("nomeOrgao") if isinstance(orgao, dict) else str(orgao)
        if orgao_nome:
            case.vara = orgao_nome
    if valor_causa not in (None, ""):
        try:
            case.valor_causa = float(valor_causa)
        except (TypeError, ValueError):
            pass
    # Assunto/classe (código TPU) — grava traduzido nas observações para não
    # colidir com campos livres de estratégia já preenchidos pelo advogado.
    assunto = _get(dados_basicos, "assunto")
    partes_extra = []
    if classe:
        codigo_classe = classe.get("codigo") if isinstance(classe, dict) else classe
        partes_extra.append(f"Classe (MNI): {traduzir_classe(codigo_classe)}")
    if assunto:
        codigo_assunto = assunto.get("codigo") if isinstance(assunto, dict) else assunto
        partes_extra.append(f"Assunto (MNI): {traduzir_assunto(codigo_assunto)}")
    if partes_extra:
        nota = " | ".join(partes_extra)
        if not case.observacoes:
            case.observacoes = nota
        elif nota not in case.observacoes:
            case.observacoes = f"{case.observacoes}\n{nota}"


async def _gravar_andamentos(
    db: AsyncSession, case: Case, movimentos: list[dict[str, Any]],
) -> int:
    """Grava um CaseMovimento por movimento novo do MNI. Dedup simples por
    (descricao, data_evento) — MNI não expõe um ID estável de movimento em
    todas as versões do protocolo, então usamos o par como chave natural."""
    if not movimentos:
        return 0
    existentes = (await db.execute(
        select(CaseMovimento.descricao, CaseMovimento.data_evento)
        .where(CaseMovimento.case_id == case.id, CaseMovimento.tipo == "andamento_mni")
    )).all()
    chaves_existentes = {(desc, data) for desc, data in existentes}

    novos = 0
    for mov in movimentos:
        codigo = _get(mov, "movimentoNacional", "codigoNacional", "codigo")
        codigo_val = codigo.get("codigo") if isinstance(codigo, dict) else codigo
        descricao = traduzir_movimento(codigo_val) if codigo_val is not None else \
            _get(mov, "descricao", default="Movimento sem descrição")
        data_hora = _get(mov, "dataHora", "data")
        data_evento = _parse_data(data_hora)
        chave = (descricao, data_evento)
        if chave in chaves_existentes:
            continue
        db.add(CaseMovimento(
            id=str(uuid4()), case_id=case.id, tipo="andamento_mni",
            descricao=descricao, data_evento=data_evento,
        ))
        chaves_existentes.add(chave)
        novos += 1
    return novos


def _parse_data(valor: Any) -> datetime:
    if isinstance(valor, datetime):
        return valor
    if isinstance(valor, str):
        try:
            return datetime.fromisoformat(valor)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


async def _gravar_documentos_novos(
    db: AsyncSession, case: Case, tribunal_id: str,
    documentos: list[dict[str, Any]], uploaded_by: str | None,
) -> int:
    """Cria Document (GED) para cada documento do MNI ainda não sincronizado
    (dedup por idDocumento). Documentos sem conteúdo binário na resposta
    (metadados apenas) NÃO criam linha no GED — ficam para uma consulta
    específica com `documento=idDocumento` (fora do escopo deste helper)."""
    settings = get_settings()
    novos = 0
    for doc in documentos:
        id_doc = str(_get(doc, "idDocumento", "identificador", default=""))
        if not id_doc:
            continue
        ja_existe = (await db.execute(
            select(DocumentoProcessoEletronicoDedup.id).where(
                DocumentoProcessoEletronicoDedup.tribunal_id == tribunal_id,
                DocumentoProcessoEletronicoDedup.id_documento_tribunal == id_doc,
            )
        )).scalar_one_or_none()
        if ja_existe:
            continue

        binario = _extrair_binario(doc)
        if binario is None:
            # Sem conteúdo nesta resposta — não cria GED, mas também não marca
            # dedup (para poder tentar de novo quando o conteúdo vier).
            logger.info(
                "[MNI] documento %s sem binário na resposta — GED não criado "
                "nesta sincronização (case=%s)", id_doc, case.id,
            )
            continue

        try:
            nivel_sigilo = _get(doc, "nivelSigilo", "nivelDeSigilo", default=0)
            confidencialidade = mapear_confidencialidade(nivel_sigilo)
            tipo_documento = _get(doc, "tipoDocumento", "descricao", default="processo_eletronico")
            mimetype = _get(doc, "mimetype", default="application/octet-stream")
            titulo = _get(doc, "descricao", default=f"Documento MNI {id_doc}")

            agora = datetime.now(timezone.utc)
            subdir = f"{agora.year}/{agora.month:02d}"
            os.makedirs(f"{settings.UPLOAD_DIR}/{subdir}", exist_ok=True)
            doc_id = str(uuid4())
            ext = _extensao_por_mimetype(mimetype)
            filepath_rel = f"{subdir}/{doc_id}{ext}"
            with open(f"{settings.UPLOAD_DIR}/{filepath_rel}", "wb") as f:
                f.write(binario)

            documento_ged = Document(
                id=doc_id, titulo=str(titulo)[:255], tipo=str(tipo_documento)[:50],
                filename=f"{id_doc}{ext}", filepath=filepath_rel,
                mimetype=str(mimetype), size_bytes=len(binario),
                confidencialidade=confidencialidade,
                case_id=case.id, uploaded_by=uploaded_by,
                # Achado 30: documento baixado do tribunal (MNI) e prova
                # documental — o digest e o que sustenta que o arquivo juntado
                # e o que veio de la.
                sha256=hashlib.sha256(binario).hexdigest(),
            )
            db.add(documento_ged)
            await db.flush()

            db.add(DocumentoProcessoEletronicoDedup(
                id=str(uuid4()), tribunal_id=tribunal_id,
                id_documento_tribunal=id_doc, document_id=doc_id, case_id=case.id,
            ))
            novos += 1
        except Exception as e:  # noqa: BLE001 — erro em UM documento não aborta os demais
            logger.error(
                "[MNI] falha ao gravar documento %s (case=%s): %s",
                id_doc, case.id, e,
            )
            continue
    return novos


def _extensao_por_mimetype(mimetype: str) -> str:
    mapa = {
        "application/pdf": ".pdf",
        "text/html": ".html",
        "text/plain": ".txt",
        "application/xml": ".xml",
        "image/jpeg": ".jpg",
        "image/png": ".png",
    }
    return mapa.get(mimetype, ".bin")


async def aplicar_resultado_consulta(
    db: AsyncSession,
    case: Case,
    tribunal_id: str,
    resultado: ConsultaProcessoResultado,
    uploaded_by: str | None = None,
) -> dict[str, int]:
    """Aplica o resultado de consultar_processo ao domínio EJC dentro da
    MESMA transação (chamador faz commit) — Case, andamentos e documentos
    novos entram juntos ou nenhum entra, evitando a classe de defeito
    "gravação não transacional entre registros relacionados"."""
    if resultado.dados_basicos:
        await _atualizar_dados_basicos(case, resultado.dados_basicos)
    andamentos_novos = await _gravar_andamentos(db, case, resultado.movimentos)
    docs_novos = await _gravar_documentos_novos(
        db, case, tribunal_id, resultado.documentos, uploaded_by,
    )
    case.last_synced_at = datetime.now(timezone.utc)
    return {"andamentos_novos": andamentos_novos, "docs_novos": docs_novos}
