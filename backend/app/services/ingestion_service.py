# ── app/services/ingestion_service.py ────────────────────────────────────────
# Infraestrutura genérica de ingestão no RAG (Bloco A).
#
# Pipeline padrão de toda fonte externa:
#     fetch (httpx async + retry/backoff)
#       → normaliza (texto limpo)
#       → chunk (por tamanho, com overlap)
#       → embeddings locais (all-MiniLM 384d, opcional)
#       → UPSERT idempotente em knowledge_docs/knowledge_chunks
#       → registra execução em fontes_ingestao (auditável)
#
# Princípio: jobs diários NÃO podem duplicar documentos. A deduplicação é por
# `chave_origem` (URN LexML, nº CNJ, código da norma...). Se o conteúdo não
# mudou (mesmo hash), o documento é deixado intacto (não re-embeda). Se mudou,
# os chunks antigos são removidos e regravados. Tudo respeitando soft-delete.
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from sqlalchemy import select, text as sqltext, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag import KnowledgeDoc, KnowledgeChunk, FonteIngestao
from app.services.embedding_service import gerar_embeddings

logger = logging.getLogger("ejc.ingestao")

# User-Agent realista — portais públicos rejeitam clientes anônimos/bots.
_UA = (
    "Mozilla/5.0 (compatible; EJC-LegalBot/1.0; "
    "+https://depaulateixeira.adv.br) httpx"
)
_HEADERS_PADRAO = {"User-Agent": _UA, "Accept": "application/json"}

CHUNK_TAMANHO = 1200   # caracteres por chunk
CHUNK_OVERLAP = 150    # sobreposição entre chunks (preserva contexto nas bordas)


# ══════════════════════════════════════════════════════════════════════════
# Cliente HTTP compartilhado (retry + backoff exponencial)
# ══════════════════════════════════════════════════════════════════════════

async def fetch(
    url: str,
    *,
    method: str = "GET",
    params: dict | None = None,
    json: dict | None = None,
    headers: dict | None = None,
    timeout: float = 30.0,
    tentativas: int = 3,
    espera_base: float = 1.5,
) -> httpx.Response:
    """GET/POST com retry e backoff exponencial. Levanta na última falha.

    Repete em erros de rede e HTTP 429/5xx (transientes). Não repete em 4xx
    determinísticos (exceto 429), que indicam erro de requisição.
    """
    hdrs = {**_HEADERS_PADRAO, **(headers or {})}
    ultimo_erro: Exception | None = None

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
        for n in range(tentativas):
            try:
                r = await c.request(method, url, params=params, json=json, headers=hdrs)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError(
                        f"HTTP {r.status_code}", request=r.request, response=r
                    )
                r.raise_for_status()
                return r
            except (httpx.TransportError, httpx.HTTPStatusError) as e:
                ultimo_erro = e
                # 4xx não-transiente → não adianta repetir
                resp = getattr(e, "response", None)
                if resp is not None and 400 <= resp.status_code < 500 and resp.status_code != 429:
                    raise
                if n < tentativas - 1:
                    await asyncio.sleep(espera_base * (2 ** n))
    raise ultimo_erro  # type: ignore[misc]


# ══════════════════════════════════════════════════════════════════════════
# Normalização e chunking
# ══════════════════════════════════════════════════════════════════════════

def normalizar(texto: str) -> str:
    """Remove ruído de whitespace preservando quebras de parágrafo."""
    if not texto:
        return ""
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def chunk_texto(
    texto: str, tamanho: int = CHUNK_TAMANHO, overlap: int = CHUNK_OVERLAP
) -> list[str]:
    """Divide texto em chunks com sobreposição, cortando em fronteira de frase
    quando possível (evita partir no meio de uma palavra/oração).
    """
    texto = normalizar(texto)
    if len(texto) <= tamanho:
        return [texto] if texto else []

    chunks: list[str] = []
    ini = 0
    n = len(texto)
    while ini < n:
        fim = min(ini + tamanho, n)
        if fim < n:
            # tenta recuar até a última quebra natural dentro da janela
            janela = texto[ini:fim]
            corte = max(
                janela.rfind(". "), janela.rfind(".\n"),
                janela.rfind("\n\n"), janela.rfind("; "),
            )
            if corte > tamanho * 0.5:   # só recua se não desperdiçar muito
                fim = ini + corte + 1
        trecho = texto[ini:fim].strip()
        if trecho:
            chunks.append(trecho)
        if fim >= n:
            break
        ini = max(fim - overlap, ini + 1)
    return chunks


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


# ══════════════════════════════════════════════════════════════════════════
# UPSERT idempotente de documento no RAG
# ══════════════════════════════════════════════════════════════════════════

async def upsert_documento(
    db: AsyncSession,
    *,
    titulo: str,
    categoria: str,
    conteudo: str,
    chave_origem: str,
    fonte: str | None = None,
    tribunal: str | None = None,
    extra: dict | None = None,
    client_id: str | None = None,
    case_id: str | None = None,
) -> str:
    """Insere/atualiza um documento na base de conhecimento, de forma idempotente.

    Retorna: "novo" | "atualizado" | "inalterado".

    - Dedup por `chave_origem` (obrigatória aqui). Se já existe documento ativo
      com a mesma chave:
        • conteúdo idêntico (mesmo hash) → "inalterado" (não toca nos vetores).
        • conteúdo diferente → remove chunks antigos, regrava + re-embeda.
    - Documento novo → cria doc + chunks (+ embeddings se disponíveis).
    """
    conteudo = normalizar(conteudo)
    if len(conteudo) < 50:
        return "inalterado"   # conteúdo irrelevante — ignora silenciosamente
    h = _sha1(conteudo)
    agora = datetime.now(timezone.utc)

    existente = (await db.execute(
        select(KnowledgeDoc).where(
            KnowledgeDoc.chave_origem == chave_origem,
            KnowledgeDoc.deleted_at.is_(None),
        )
    )).scalar_one_or_none()

    chunks = chunk_texto(conteudo)
    vetores = await gerar_embeddings(chunks)   # None se embeddings desligados

    if existente:
        if existente.hash_conteudo == h:
            return "inalterado"
        # Conteúdo mudou → troca os chunks
        await db.execute(
            delete(KnowledgeChunk).where(KnowledgeChunk.doc_id == existente.id)
        )
        existente.titulo = titulo
        existente.categoria = categoria
        existente.fonte = fonte
        existente.tribunal = tribunal
        existente.extra = extra
        existente.client_id = client_id
        existente.case_id = case_id
        existente.hash_conteudo = h
        existente.atualizado_em = agora
        doc_id = existente.id
        resultado = "atualizado"
    else:
        doc_id = str(uuid4())
        db.add(KnowledgeDoc(
            id=doc_id, titulo=titulo, categoria=categoria,
            fonte=fonte, tribunal=tribunal, extra=extra,
            client_id=client_id, case_id=case_id,
            chave_origem=chave_origem, hash_conteudo=h, atualizado_em=agora,
        ))
        await db.flush()   # FK: doc antes dos chunks
        resultado = "novo"

    for i, c in enumerate(chunks):
        db.add(KnowledgeChunk(
            id=str(uuid4()), doc_id=doc_id, chunk_index=i, conteudo=c,
            embedding=vetores[i] if vetores else None,
        ))
    return resultado


# ══════════════════════════════════════════════════════════════════════════
# Controle de fontes (auditoria no painel)
# ══════════════════════════════════════════════════════════════════════════

async def registrar_fonte(
    db: AsyncSession, slug: str, descricao: str, categoria_rag: str | None = None
) -> None:
    """Garante a existência da linha de controle da fonte (idempotente)."""
    f = (await db.execute(
        select(FonteIngestao).where(FonteIngestao.slug == slug)
    )).scalar_one_or_none()
    if f is None:
        db.add(FonteIngestao(
            slug=slug, descricao=descricao, categoria_rag=categoria_rag,
        ))
        await db.flush()


async def marcar_execucao(
    db: AsyncSession, slug: str, *,
    status: str, novos: int = 0, total: int = 0, erro: str | None = None,
) -> None:
    """Atualiza a linha de controle após uma execução do job."""
    f = (await db.execute(
        select(FonteIngestao).where(FonteIngestao.slug == slug)
    )).scalar_one_or_none()
    if f is None:
        return
    f.ultima_execucao = datetime.now(timezone.utc)
    f.ultimo_status = status
    f.registros_novos = novos
    f.registros_total = total
    f.ultimo_erro = (erro or "")[:2000] if erro else None


# ══════════════════════════════════════════════════════════════════════════
# Wrapper de execução de job (boilerplate único p/ todos os ingestores)
# ══════════════════════════════════════════════════════════════════════════

async def executar_ingestao(slug: str, descricao: str, categoria_rag: str, coro_fn):
    """Executa um ingestor com sessão própria, captura métricas e erros.

    `coro_fn(db) -> tuple[int, int]` deve retornar (novos, total_processados).
    Centraliza commit, marcação de status e log — cada job vira ~3 linhas.
    """
    from app.core.database import AsyncSessionLocal
    novos = total = 0
    erro: str | None = None
    status = "sucesso"
    try:
        async with AsyncSessionLocal() as db:
            await registrar_fonte(db, slug, descricao, categoria_rag)
            await db.commit()
        async with AsyncSessionLocal() as db:
            novos, total = await coro_fn(db)
            await db.commit()
    except Exception as e:        # nunca derruba o scheduler
        erro = f"{type(e).__name__}: {e}"
        status = "parcial" if novos else "erro"
        logger.error(f"[Ingestao:{slug}] {erro}")
    finally:
        try:
            async with AsyncSessionLocal() as db:
                await marcar_execucao(db, slug, status=status,
                                      novos=novos, total=total, erro=erro)
                await db.commit()
        except Exception as e:
            logger.error(f"[Ingestao:{slug}] falha ao marcar execução: {e}")
    logger.info(f"[Ingestao:{slug}] {status} — {novos} novos / {total} processados")
    return novos, total
