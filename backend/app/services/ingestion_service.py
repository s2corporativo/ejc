# ── app/services/ingestion_service.py ────────────────────────────────────────
# Infraestrutura genérica de ingestão no RAG (Bloco A).
#
# Pipeline padrão de toda fonte externa:
#     fetch (httpx async + retry/backoff)
#       → normaliza (texto limpo)
#       → chunk (por tamanho, com overlap)
#       → embeddings locais (all-E5 768d, opcional)
#       → UPSERT idempotente em knowledge_docs/knowledge_chunks
#       → registra execução em fontes_ingestao (auditável)
#
# Princípio: jobs diários NÃO podem duplicar documentos. A deduplicação é por
# `chave_origem` (URN LexML, nº CNJ, código da norma...). Se o conteúdo não
# mudou (mesmo hash), o documento é deixado intacto (não re-embeda). Se mudou,
# NÃO sobrescreve: a versão antiga é preservada como histórico (vigente=False,
# chunks intactos) e uma nova versão é criada (migration 068). Tudo respeitando
# soft-delete.
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from sqlalchemy import select
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

_MAX_REDIRECTS_SSRF = 5


def _validar_sem_ssrf(u: str) -> None:
    """Bloqueia URL que aponte para IP privado/loopback/link-local (ex.:
    169.254.169.254, 127.0.0.1, 10.*). Reusa o validador anti-SSRF do callback
    público (rag_public.validar_callback_url). Import LAZY para evitar ciclo
    (rag_public importa este módulo). Levanta ValueError se bloqueada."""
    if not u.startswith(("http://", "https://")):
        raise ValueError(f"URL não-http(s) bloqueada (SSRF): {u[:80]}")
    from app.routers.rag_public import validar_callback_url
    validar_callback_url(u, exigir_https=False)


async def _request_validado(c: httpx.AsyncClient, method: str, url: str,
                            params, json, hdrs) -> httpx.Response:
    """Faz a request seguindo redirects MANUALMENTE e revalidando cada salto
    contra SSRF (o cliente é criado com follow_redirects=False)."""
    _validar_sem_ssrf(url)
    r = await c.request(method, url, params=params, json=json, headers=hdrs)
    saltos = 0
    while r.is_redirect and saltos < _MAX_REDIRECTS_SSRF:
        destino = (str(r.next_request.url)
                   if r.next_request else r.headers.get("location", ""))
        _validar_sem_ssrf(destino)   # revalida cada salto (anti-rebind por redirect)
        r = await c.get(destino, headers=hdrs)
        saltos += 1
    return r


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
    validar_ssrf: bool = False,
) -> httpx.Response:
    """GET/POST com retry e backoff exponencial. Levanta na última falha.

    Repete em erros de rede e HTTP 429/5xx (transientes). Não repete em 4xx
    determinísticos (exceto 429), que indicam erro de requisição.

    validar_ssrf=True (opt-in): desabilita o follow_redirects automático e
    revalida a URL inicial e CADA salto de redirect contra IP interno
    (169.254.169.254/127.0.0.1/10.*...), reusando o validador do callback
    público. Usado no caminho de ingestão AUTOMÁTICA (anpd/normas_rfb), cujas
    URLs seguidas vêm de HTML raspado. Chamadas a APIs de host fixo (SGS,
    LexML...) seguem com validar_ssrf=False para não onerar o caminho legítimo.
    """
    hdrs = {**_HEADERS_PADRAO, **(headers or {})}
    ultimo_erro: Exception | None = None

    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=not validar_ssrf
    ) as c:
        for n in range(tentativas):
            try:
                if validar_ssrf:
                    r = await _request_validado(c, method, url, params, json, hdrs)
                else:
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
    confianca: str | None = None,
    embutir_vetores: bool = True,
    chunks: list[str] | None = None,
    forcar_nova_versao: bool = False,
) -> str:
    """Insere/atualiza um documento na base de conhecimento, com VERSIONAMENTO
    (migration 068) — nunca sobrescreve o conteúdo de uma versão anterior.

    Retorna: "novo" | "atualizado" | "inalterado".

    - Dedup por `chave_origem` (obrigatória aqui), olhando apenas a versão
      VIGENTE (`vigente=True`). Se já existe:
        • conteúdo idêntico (mesmo hash) → "inalterado" (não toca nos vetores).
        • conteúdo diferente → NÃO apaga a versão antiga. Marca-a
          `vigente=False` (seus chunks continuam intactos, preservando o
          histórico para auditoria/citações antigas) e cria um NOVO
          `KnowledgeDoc` com `versao = anterior.versao + 1` e
          `versao_anterior_id = anterior.id`, com seus próprios chunks
          re-vetorizados.
    - Documento novo → cria doc (versao=1, vigente=True) + chunks (+ embeddings
      se disponíveis).
    - `chunks` (opcional): chunks PRÉ-COMPUTADOS pelo chamador quando a divisão
      semântica importa (ex.: legislação dividida por artigo em
      scripts/seed_legislacao.py). Default None → chunking genérico por tamanho
      (chunk_texto). O dedup/hash continua sendo sobre `conteudo` normalizado,
      então a idempotência não muda.
    - `forcar_nova_versao=True` (opt-in): ignora o atalho "inalterado" de
      conteúdo idêntico e cria uma NOVA VERSÃO mesmo com o mesmo hash. Uso:
      migração de estratégia de chunking (ex.: legislação re-chunkada por
      artigo — ingestors/planalto._rechunk_pendente), onde o `conteudo` não
      mudou mas os chunks precisam ser regravados. O versionamento preserva a
      versão antiga como histórico, como em qualquer atualização.
    """
    conteudo = normalizar(conteudo)
    if len(conteudo) < 50:
        return "inalterado"   # conteúdo irrelevante — ignora silenciosamente
    # Gate de confiança (governança de IA): grava no extra JSONB a chave
    # canônica lida por ia_governanca._conf (vocabulário alta|media|baixa|
    # bloqueado). Sem confianca explícita, a busca assume "media".
    if confianca:
        extra = {**(extra or {}), "confidence_level": confianca}
    h = _sha1(conteudo)
    agora = datetime.now(timezone.utc)

    existente = (await db.execute(
        select(KnowledgeDoc).where(
            KnowledgeDoc.chave_origem == chave_origem,
            KnowledgeDoc.deleted_at.is_(None),
            KnowledgeDoc.vigente.is_(True),
        )
    )).scalar_one_or_none()

    # Atalho ANTES de vetorizar: documento vigente com conteúdo idêntico (mesmo
    # hash) → "inalterado", sem tocar nos vetores. `gerar_embeddings` é caro
    # (segundos por doc na CPU); embedar aqui e só depois descartar fazia o
    # re-seed a cada deploy re-vetorizar TODO o corpus (~400 docs, minutos em
    # silêncio) e estourar o timeout do SSH. Após o 1º seed completo, os deploys
    # seguintes passam por aqui de imediato.
    if existente and existente.hash_conteudo == h and not forcar_nova_versao:
        return "inalterado"

    if chunks is None:
        chunks = chunk_texto(conteudo)
    else:
        chunks = [normalizar(c) for c in chunks if c and c.strip()]
        if not chunks:
            chunks = chunk_texto(conteudo)
    # `embutir_vetores=False` → vetorização adiada (fica "pendente"; o chamador
    # agenda a indexação em background — ex.: lote da API pública, que não pode
    # bloquear a resposta embedando até ~100 documentos inline).
    vetores = await gerar_embeddings(chunks) if embutir_vetores else None
    # BUG-04: status coerente com o resultado real da vetorização.
    # 'indexado' só quando os chunks foram efetivamente embedados; senão 'pendente'
    # (embeddings desligados/indisponíveis) — nunca fica 'pendente' com vetor pronto.
    status_novo = "indexado" if vetores else "pendente"

    if existente:
        if existente.hash_conteudo == h and not forcar_nova_versao:
            return "inalterado"
        # Conteúdo mudou → NOVA VERSÃO. A versão antiga vira histórico
        # (vigente=False), seus chunks NÃO são tocados.
        existente.vigente = False
        # flush do UPDATE antes do INSERT: índice único parcial exige que a
        # versão anterior saia de vigente=true primeiro (senão o INSERT da nova
        # versão vigente colide com a antiga na mesma chave_origem).
        await db.flush()
        doc_id = str(uuid4())
        db.add(KnowledgeDoc(
            id=doc_id, titulo=titulo, categoria=categoria,
            fonte=fonte, tribunal=tribunal, extra=extra,
            client_id=client_id, case_id=case_id,
            chave_origem=chave_origem, hash_conteudo=h, atualizado_em=agora,
            status_indexacao=status_novo,
            versao=existente.versao + 1,
            versao_anterior_id=existente.id,
            vigente=True,
        ))
        await db.flush()   # FK: doc antes dos chunks
        resultado = "atualizado"
    else:
        doc_id = str(uuid4())
        db.add(KnowledgeDoc(
            id=doc_id, titulo=titulo, categoria=categoria,
            fonte=fonte, tribunal=tribunal, extra=extra,
            client_id=client_id, case_id=case_id,
            chave_origem=chave_origem, hash_conteudo=h, atualizado_em=agora,
            status_indexacao=status_novo,
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
