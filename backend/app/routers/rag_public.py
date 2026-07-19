# ── app/routers/rag_public.py ────────────────────────────────────────────────
# API PÚBLICA de abastecimento da base de conhecimento (Fase 2 IA/RAG).
#
# Consumida por integradores/automações (ex.: n8n) autenticados por API key de
# serviço (header X-API-Key, escopo knowledge:write) — NÃO por JWT de usuário.
#
#   POST /rag/knowledge-base/batch   → ingestão em lote (até 100 itens),
#                                      idempotente por chave_origem+hash via
#                                      upsert_documento (versionamento 068).
#   GET  /rag/knowledge-base/status  → status de indexação por chave_origem.
#
# Vetorização segue ASSÍNCRONA via dispatcher único (app/tasks/dispatcher.py):
# Celery+Redis quando CELERY_ENABLED (Fase 3A), senão BackgroundTasks +
# _indexar_doc_bg (mesmo mecanismo da ingestão manual). Com Celery ativo, o
# callback_url pode ser notificado ANTES de a indexação concluir (o worker é
# outro processo) — o integrador deve confirmar via GET /status.
from __future__ import annotations

import ipaddress
import logging
import socket
from typing import List, Optional
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_key_auth import require_api_key
from app.core.config import get_settings
from app.core.database import get_db, AsyncSessionLocal
from app.core.rate_limit import consumir
from app.models.api_key import ApiKey
from app.models.rag import KnowledgeDoc
from app.routers.ia_governanca import Confianca
from app.services.embedding_service import disponivel as emb_disponivel
from app.tasks.dispatcher import agendar_indexacao
from app.services.ingestion_service import upsert_documento

logger = logging.getLogger("ejc.rag_public")

router = APIRouter(prefix="/rag/knowledge-base",
                   tags=["Base de Conhecimento — API Pública"])

MAX_ITENS_LOTE = 100
# Auditoria M-3 (DoS de memória): teto por item e teto AGREGADO por lote.
MAX_CHARS_ITEM = 300_000
MAX_CHARS_LOTE = 3_000_000
MAX_CALLBACK_URL_CHARS = 2_048

# Auth única do módulo: o cache de dependências do FastAPI garante que a
# validação da API key roda UMA vez por request (auth + rate limit + handler).
_auth = require_api_key("knowledge:write")


async def _rl_batch(ak: ApiKey = Depends(_auth)) -> None:
    await consumir("rag_kb_batch", f"apikey:{ak.id}", 30)


async def _rl_status(ak: ApiKey = Depends(_auth)) -> None:
    await consumir("rag_kb_status", f"apikey:{ak.id}", 60)


# ── Schemas ───────────────────────────────────────────────────────────────────

class ItemLote(BaseModel):
    """Um documento do lote de ingestão."""
    titulo: str = Field(..., min_length=3, max_length=500)
    categoria: str = Field(..., min_length=2, max_length=50,
                           description="Categoria RAG (ex.: legislacao_geral, sumula_stj, doutrina)")
    conteudo: str = Field(..., min_length=50, max_length=MAX_CHARS_ITEM,
                          description="Texto integral do documento "
                                      f"(50 a {MAX_CHARS_ITEM} caracteres)")
    chave_origem: str = Field(..., min_length=3, max_length=255,
                              description="Chave idempotente (URN, nº CNJ, id externo). "
                                          "Reenvios com o mesmo conteúdo não duplicam.")
    fonte: Optional[str] = Field(None, max_length=255)
    tribunal: Optional[str] = Field(None, max_length=20)
    extra: Optional[dict] = None
    confianca: Confianca = "media"
    client_id: Optional[str] = Field(None, description="Isolamento LGPD por cliente")
    case_id: Optional[str] = None


class BatchIngestRequest(BaseModel):
    """Lote de ingestão. Itens são validados INDIVIDUALMENTE: um item inválido
    vira `resultado="erro"` naquele item, sem derrubar o lote (por isso o tipo
    aberto `dict` — o schema efetivo de cada item é `ItemLote`)."""
    itens: List[dict] = Field(..., min_length=1, max_length=MAX_ITENS_LOTE)
    callback_url: Optional[str] = Field(
        None,
        max_length=MAX_CALLBACK_URL_CHARS,
        description="URL https pública chamada (POST) ao final da indexação, "
                    "com o resumo de status por chave_origem.",
    )


# ── Proteção SSRF do callback ─────────────────────────────────────────────────

def validar_callback_url(url: str, *, exigir_https: bool | None = None) -> str:
    """Valida a callback_url contra SSRF. Lança ValueError se inválida.

    - Esquema http/https apenas; https OBRIGATÓRIO em produção (APP_ENV).
    - Resolve o host e bloqueia IPs privados, loopback, link-local, multicast,
      reservados e não-especificados (169.254.*, 10.*, 127.*, ::1 etc.).

    Retorna o PRIMEIRO IP público resolvido (todos são validados). O chamador
    deve FIXAR esse IP no POST do callback (`_postar_callback(ip=...)`) — sem
    isso, uma nova resolução DNS no background permitiria DNS rebinding
    (validação vê IP público; POST resolve de novo e cai em IP privado).
    """
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise ValueError("callback_url deve usar http(s)")
    if exigir_https is None:
        exigir_https = get_settings().APP_ENV == "production"
    if exigir_https and p.scheme != "https":
        raise ValueError("callback_url deve usar https em produção")
    host = p.hostname
    if not host:
        raise ValueError("callback_url sem host")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise ValueError("host da callback_url não resolve")
    ips_validos: list[str] = []
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
            raise ValueError("callback_url aponta para endereço privado/loopback (bloqueado)")
        ips_validos.append(str(ip))
    if not ips_validos:
        raise ValueError("host da callback_url não resolve para IP utilizável")
    return ips_validos[0]


# ── Resumo de status por chave_origem (compartilhado batch/status/callback) ──

async def _resumo_status(
    db: AsyncSession, chaves: List[str], client_id: Optional[str] = None,
) -> list[dict]:
    """Resumo por chave_origem. `client_id` = isolamento fail-closed da API
    key (auditoria A-1): chave restrita a um cliente enxerga SOMENTE os docs
    daquele cliente — chave_origem de outro tenant responde `nao_encontrado`,
    como se não existisse (mesma regra que o batch já força na escrita)."""
    filtros = [
        KnowledgeDoc.chave_origem.in_(chaves),
        KnowledgeDoc.vigente.is_(True),
        KnowledgeDoc.deleted_at.is_(None),
    ]
    if client_id is not None:
        filtros.append(KnowledgeDoc.client_id == client_id)
    docs = (await db.execute(
        select(KnowledgeDoc).where(*filtros)
    )).scalars().all()
    por_chave = {d.chave_origem: d for d in docs}
    out = []
    for ch in chaves:
        d = por_chave.get(ch)
        if d is None:
            out.append({"chave_origem": ch, "doc_id": None, "versao": None,
                        "status_indexacao": "nao_encontrado"})
        else:
            out.append({"chave_origem": ch, "doc_id": d.id, "versao": d.versao,
                        "status_indexacao": d.status_indexacao})
    return out


def _filtros_doc_escopo_batch(chave_origem: str, client_id: str | None) -> list:
    """Filtros para reler exatamente o doc do mesmo escopo usado no upsert.

    O batch pode receber API key restrita a cliente ou payload com client_id.
    Após o upsert, a resposta não pode buscar só por `chave_origem`, porque
    chaves iguais em tenants diferentes poderiam vazar `doc_id`/`versao` de
    outro escopo. Para item sem cliente, restringe ao escopo global (`NULL`).
    """
    filtros = [
        KnowledgeDoc.chave_origem == chave_origem,
        KnowledgeDoc.vigente.is_(True),
        KnowledgeDoc.deleted_at.is_(None),
    ]
    if client_id is None:
        filtros.append(KnowledgeDoc.client_id.is_(None))
    else:
        filtros.append(KnowledgeDoc.client_id == client_id)
    return filtros


# ── Callback (webhook simples) ────────────────────────────────────────────────

def _url_com_ip_fixado(url: str, ip: str) -> tuple[str, str]:
    """Substitui o host da URL pelo IP validado. Retorna (url_fixada, host
    original) — o host vai no header `Host` e no SNI/verificação TLS."""
    p = urlparse(url)
    host = p.hostname or ""
    porta = f":{p.port}" if p.port else ""
    ip_fmt = f"[{ip}]" if ":" in ip else ip
    return p._replace(netloc=f"{ip_fmt}{porta}").geturl(), host


async def _postar_callback(url: str, payload: dict, ip: str | None = None) -> bool:
    """POST no callback com timeout curto e no máximo 2 tentativas.
    Falha SÓ loga — nunca propaga (a indexação já aconteceu).

    Anti-DNS-rebinding (auditoria M-2): quando `ip` (validado por
    validar_callback_url no request) é informado, o POST conecta DIRETO nesse
    IP — a URL é reescrita com o IP e o hostname original segue no header
    `Host` e na extensão `sni_hostname` do httpx/httpcore, que também é usada
    como server_hostname na verificação do certificado TLS. Assim NÃO há nova
    resolução DNS no background e um DNS que "mude" para IP privado entre a
    validação e o POST não tem efeito. (Alternativa de re-validar o IP no
    momento do POST foi descartada: ainda deixaria janela TOCTOU entre a
    re-validação e a resolução interna do httpx.)
    """
    destino, host = (url, None) if ip is None else _url_com_ip_fixado(url, ip)
    kwargs: dict = {}
    if host:
        kwargs["headers"] = {"Host": host}
        kwargs["extensions"] = {"sni_hostname": host}
    for tentativa in (1, 2):
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.post(destino, json=payload, **kwargs)
                r.raise_for_status()
                return True
        except Exception as e:
            logger.warning(
                f"[rag_public] callback falhou (tentativa {tentativa}/2) "
                f"url={url}: {type(e).__name__}: {str(e)[:200]}"
            )
    return False


async def _callback_bg(url: str, lote_id: str, chaves: List[str],
                       ip: str | None = None,
                       client_id: str | None = None) -> None:
    """Task de background: roda DEPOIS das tasks de indexação (BackgroundTasks
    executa em ordem), lê o status final e notifica o integrador.
    `ip` = IP fixado na validação SSRF; `client_id` = escopo da API key."""
    try:
        async with AsyncSessionLocal() as db:
            docs = await _resumo_status(db, chaves, client_id=client_id)
        await _postar_callback(url, {"lote_id": lote_id, "docs": docs}, ip=ip)
    except Exception as e:  # defesa extra: callback nunca derruba nada
        logger.warning(f"[rag_public] callback_bg erro: {type(e).__name__}: {e}")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/batch", status_code=201,
    summary="Ingestão em lote na base de conhecimento (API key)",
    dependencies=[Depends(_rl_batch)],
)
async def ingerir_lote(
    req: BatchIngestRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    ak: ApiKey = Depends(_auth),
):
    """Ingere até 100 documentos de uma vez, com idempotência por `chave_origem`
    + hash de conteúdo (reenvio idêntico → `inalterado`; conteúdo alterado →
    nova VERSÃO, preservando a anterior como histórico — migration 068).

    - Autenticação: header `X-API-Key` com escopo `knowledge:write`.
    - Falha POR ITEM: item inválido não derruba o lote (`resultado="erro"`).
    - Vetorização assíncrona (BackgroundTasks); acompanhe via
      `GET /rag/knowledge-base/status?chaves=...`.
    - `callback_url` (opcional, https em produção): POST com o resumo de status
      ao final da indexação.
    - Chave com `client_id` fixado: todo item é FORÇADO ao escopo daquele
      cliente (isolamento LGPD), ignorando o client_id do payload.
    """
    callback_ip: str | None = None
    if req.callback_url:
        try:
            callback_ip = validar_callback_url(req.callback_url)
        except ValueError as e:
            raise HTTPException(422, f"callback_url rejeitada: {e}")

    # Teto agregado do lote (auditoria M-3): soma dos conteúdos brutos.
    total_chars = sum(
        len(b.get("conteudo"))
        for b in req.itens
        if isinstance(b, dict) and isinstance(b.get("conteudo"), str)
    )
    if total_chars > MAX_CHARS_LOTE:
        raise HTTPException(
            422,
            f"Lote excede o limite agregado de {MAX_CHARS_LOTE} caracteres "
            f"de conteúdo (recebido: {total_chars}). Divida em lotes menores.",
        )

    resultados: list[dict] = []
    chaves_lote: list[str] = []
    docs_pendentes: list[str] = []
    contagem = {"novo": 0, "atualizado": 0, "inalterado": 0, "erro": 0}

    for idx, bruto in enumerate(req.itens):
        chave = bruto.get("chave_origem") if isinstance(bruto, dict) else None
        try:
            item = ItemLote.model_validate(bruto)
        except ValidationError as e:
            erros = "; ".join(
                f"{'.'.join(str(l) for l in err['loc'])}: {err['msg']}"
                for err in e.errors()[:3]
            )
            contagem["erro"] += 1
            resultados.append({"indice": idx, "chave_origem": chave,
                               "resultado": "erro", "doc_id": None,
                               "versao": None, "erro": erros[:300]})
            continue

        # Isolamento LGPD: chave restrita a cliente prevalece sobre o payload.
        client_id = ak.client_id or item.client_id
        try:
            async with db.begin_nested():   # savepoint: erro não poisona o lote
                resultado = await upsert_documento(
                    db,
                    titulo=item.titulo, categoria=item.categoria,
                    conteudo=item.conteudo, chave_origem=item.chave_origem,
                    fonte=item.fonte, tribunal=item.tribunal,
                    # API externa nunca autoaprova conteúdo, mesmo que o
                    # payload tente enviar rag_status=aprovado.
                    extra={**(item.extra or {}), "rag_status": "pendente",
                           "ingestao_api": True},
                    client_id=client_id, case_id=item.case_id,
                    confianca=item.confianca,
                    embutir_vetores=False,   # vetorização adiada p/ background
                )
        except Exception as e:
            contagem["erro"] += 1
            resultados.append({"indice": idx, "chave_origem": item.chave_origem,
                               "resultado": "erro", "doc_id": None, "versao": None,
                               "erro": f"{type(e).__name__}: {str(e)[:200]}"})
            continue

        doc = (await db.execute(
            select(KnowledgeDoc).where(
                *_filtros_doc_escopo_batch(item.chave_origem, client_id)
            )
        )).scalar_one_or_none()

        contagem[resultado] += 1
        chaves_lote.append(item.chave_origem)
        if doc is not None and resultado in ("novo", "atualizado") \
                and doc.status_indexacao == "pendente":
            docs_pendentes.append(doc.id)
        resultados.append({
            "indice": idx, "chave_origem": item.chave_origem,
            "resultado": resultado,
            "doc_id": doc.id if doc else None,
            # Doc recém-inserido pode ainda não ter o server_default carregado
            # na sessão (versao=1 só materializa no banco) — normaliza aqui.
            "versao": (doc.versao if doc.versao is not None else 1) if doc else None,
            "erro": None,
        })

    await db.commit()

    # Vetorização assíncrona — mesmo dispatcher da ingestão manual (/rag/ingest):
    # Celery quando habilitado/alcançável, senão BackgroundTasks (_indexar_doc_bg).
    if emb_disponivel():
        for doc_id in docs_pendentes:
            await agendar_indexacao(doc_id, background_tasks)

    lote_id = str(uuid4())
    # Callback por último: BackgroundTasks roda em ordem → o resumo enviado já
    # reflete o resultado da indexação.
    if req.callback_url and chaves_lote:
        background_tasks.add_task(_callback_bg, req.callback_url, lote_id,
                                  chaves_lote, callback_ip, ak.client_id)

    return {
        "lote_id": lote_id,
        "total": len(req.itens),
        **contagem,
        "indexacao_agendada": len(docs_pendentes) if emb_disponivel() else 0,
        "callback_agendado": bool(req.callback_url and chaves_lote),
        "itens": resultados,
    }


@router.get(
    "/status",
    summary="Status de indexação por chave_origem (API key)",
    dependencies=[Depends(_rl_status)],
)
async def status_lote(
    chaves: List[str] = Query(..., description="chave_origem dos documentos "
                                               "(repita o parâmetro ou separe por vírgula)"),
    db: AsyncSession = Depends(get_db),
    ak: ApiKey = Depends(_auth),
):
    """Consulta o status de indexação dos documentos enviados via `/batch`.

    Retorna por chave: `doc_id`, `versao` e `status_indexacao`
    (pendente | indexado | sem_embeddings | erro | nao_encontrado).
    """
    expandidas: list[str] = []
    for c in chaves:
        expandidas.extend(x.strip() for x in c.split(",") if x.strip())
    if not expandidas or len(expandidas) > MAX_ITENS_LOTE:
        raise HTTPException(422, f"Informe entre 1 e {MAX_ITENS_LOTE} chaves")
    # Isolamento fail-closed (auditoria A-1): chave restrita a um cliente só
    # enxerga documentos daquele cliente.
    return {"docs": await _resumo_status(db, expandidas, client_id=ak.client_id)}
