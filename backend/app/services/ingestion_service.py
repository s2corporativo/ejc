# ── app/services/ingestion_service.py ────────────────────────────────────────
# Infraestrutura genérica de ingestão no RAG (Bloco A).
#
# Pipeline padrão de toda fonte externa:
#     fetch (httpx async + retry/backoff)
#       → normaliza (texto limpo)
#       → chunk (por tamanho, com overlap)
#       → embeddings locais (multilingual-e5-large 1024d, opcional)
#       → UPSERT idempotente em knowledge_docs/knowledge_chunks
#       → registra execução em fontes_ingestao (auditável)
#
# Princípio: jobs diários NÃO podem duplicar documentos. A deduplicação é por
# `client_id + chave_origem`: conteúdo público/global usa client_id NULL e segue
# globalmente único; conteúdo restrito pode reutilizar a mesma chave em clientes
# diferentes sem colisão ou sobrescrita cruzada. Se o conteúdo mudou, a versão
# antiga é preservada como histórico (vigente=False, chunks intactos).
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

# Categorias derivadas de casos/clientes nunca podem nascer em escopo global.
# Mantida aqui para o WRITE path ser fail-closed, independentemente do filtro de
# recuperação em ai_service. Categoria pública não listada continua global.
_CATEGORIAS_RESTRITAS = {
    "peca_interna",
    "peca_escritorio",
    "precedente_interno",
    "comunicacao_processual",
    "andamento_processual",
}

# Categorias cujo estado de domínio é autoritativo para o estado do RAG. Nelas,
# uma regressão da peça (ex.: aprovada → em_revisao após edição) DEVE rebaixar
# `rag_status`, em vez de aplicar a regra genérica dos ingestores periódicos que
# preserva aprovações humanas contra re-feed automático.
_CATEGORIAS_RAG_ESTADO_AUTORITATIVO = {"peca_interna", "peca_escritorio"}

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


def chunk_texto_com_paginas(
    paginas: list[dict], tamanho: int = CHUNK_TAMANHO, overlap: int = CHUNK_OVERLAP
) -> list[tuple[str, int]]:
    """Divide texto por página em chunks com rastreabilidade de página.

    Cada item de ``paginas`` deve ter {"pagina": int, "texto": str}.
    Retorna lista de (chunk_texto, pagina_numero) preservando a origem.
    """
    resultado: list[tuple[str, int]] = []
    for pag in paginas:
        num = pag.get("pagina", 0)
        txt = normalizar(pag.get("texto", ""))
        if not txt:
            continue
        if len(txt) <= tamanho:
            resultado.append((txt, num))
            continue
        ini = 0
        n = len(txt)
        while ini < n:
            fim = min(ini + tamanho, n)
            if fim < n:
                janela = txt[ini:fim]
                corte = max(
                    janela.rfind(". "), janela.rfind(".\n"),
                    janela.rfind("\n\n"), janela.rfind("; "),
                )
                if corte > tamanho * 0.5:
                    fim = ini + corte + 1
            trecho = txt[ini:fim].strip()
            if trecho:
                resultado.append((trecho, num))
            if fim >= n:
                break
            ini = max(fim - overlap, ini + 1)
    return resultado


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def _filtro_escopo_cliente(client_id: str | None):
    """Predicado SQLAlchemy que reproduz a unicidade do banco.

    Conteúdo global (client_id=None) não pode capturar um documento restrito com
    a mesma chave. Conteúdo restrito só enxerga a versão vigente do próprio
    cliente. O case_id permanece metadado/subescopo operacional, mas a chave é
    única por cliente para manter a API de status determinística.
    """
    if client_id is None:
        return KnowledgeDoc.client_id.is_(None)
    return KnowledgeDoc.client_id == client_id


# ══════════════════════════════════════════════════════════════════════════
# UPSERT idempotente de documento no RAG
# ══════════════════════════════════════════════════════════════════════════

# ── Vigência jurídica: decisão de curador × leitura de ingestor ───────────────
# Marcador que a curadoria grava em `extra.legal_status_origem` ao decidir a
# situação jurídica pelo painel (rag_governance.atualizar_governanca_documento).
# Os ingestores gravam a PRÓPRIA origem ('planalto:texto_compilado',
# 'lexml:registro'), então o prefixo distingue quem decidiu o quê.
ORIGEM_VIGENCIA_CURADORIA = "curadoria"
# Todo o bloco de auditoria da vigência anda junto: preservar só o valor e
# deixar o carimbo do ingestor faria o registro afirmar uma conferência que não
# aconteceu sobre o status preservado.
_CAMPOS_VIGENCIA = (
    "legal_status",
    "legal_status_origem",
    "legal_status_verificado_em",
    "legal_status_inferido_em",
)


def _vigencia_de_curadoria(anterior: dict) -> bool:
    """A vigência registrada é uma decisão humana explicitamente rastreada?

    Só preservamos o bloco quando há um `legal_status` decisório E a origem foi
    gravada pelo fluxo de curadoria (`curadoria` ou `curadoria:<user>`).
    Ausência de origem é ausência de prova de autoria humana: registros legados
    sem proveniência e estados automáticos continuam atualizáveis pela fonte.
    `vigencia_nao_verificada` também nunca conta como decisão humana.
    """
    status = str(anterior.get("legal_status") or "").strip().lower()
    if not status or status == "vigencia_nao_verificada":
        return False
    origem = str(anterior.get("legal_status_origem") or "").strip().lower()
    return origem == ORIGEM_VIGENCIA_CURADORIA or origem.startswith(
        f"{ORIGEM_VIGENCIA_CURADORIA}:"
    )


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
    paginas: list[dict] | None = None,
    forcar_nova_versao: bool = False,
    preservar_aprovacao_rag: bool | None = None,
) -> str:
    """Insere/atualiza um documento com versionamento e isolamento por cliente.

    Retorna: "novo" | "atualizado" | "inalterado".

    Dedup canônico: `(client_id, chave_origem, vigente=true)`. Assim, a mesma
    chave externa pode existir em clientes diferentes sem que um tenant atualize,
    desative ou reutilize chunks de outro. Documentos públicos usam client_id
    NULL e seguem globalmente únicos.

    Por padrão, ingestores preservam aprovação humana contra re-feed automático.
    Peças internas são exceção deliberada: seu próprio ciclo de vida é a fonte
    autoritativa, então aprovação/regressão deve refletir imediatamente no RAG.
    O parâmetro continua disponível para chamadores com política explícita.
    """
    conteudo = normalizar(conteudo)
    if len(conteudo) < 50:
        return "inalterado"   # conteúdo irrelevante — ignora silenciosamente
    if categoria in _CATEGORIAS_RESTRITAS and not client_id:
        raise ValueError(
            f"Categoria RAG restrita '{categoria}' exige client_id; "
            "ingestão global bloqueada por isolamento LGPD."
        )
    if not (chave_origem or "").strip():
        raise ValueError("chave_origem é obrigatória para ingestão idempotente")

    if preservar_aprovacao_rag is None:
        preservar_aprovacao_rag = categoria not in _CATEGORIAS_RAG_ESTADO_AUTORITATIVO

    # Gate de confiança (governança de IA): grava no extra JSONB a chave
    # canônica lida por ia_governanca._conf.
    if confianca:
        extra = {**(extra or {}), "confidence_level": confianca}
    h = _sha1(conteudo)
    agora = datetime.now(timezone.utc)

    existente = (await db.execute(
        select(KnowledgeDoc).where(
            KnowledgeDoc.chave_origem == chave_origem,
            _filtro_escopo_cliente(client_id),
            KnowledgeDoc.deleted_at.is_(None),
            KnowledgeDoc.vigente.is_(True),
        )
    )).scalar_one_or_none()

    # Atalho ANTES de vetorizar: documento vigente com conteúdo idêntico.
    if existente and existente.hash_conteudo == h and not forcar_nova_versao:
        if extra:
            anterior = dict(existente.extra or {})
            mesclado = {**anterior, **extra}
            # DECISÃO HUMANA sobrevive ao re-feed (review do Codex no PR #496):
            # o payload do ingestor traz `human_reviewed=False` como DEFAULT e,
            # sem esta preservação, cada atualização periódica apagava a revisão
            # já feita pelo curador — tirando do RAG um documento aprovado.
            for campo in ("human_reviewed", "curadoria"):
                if anterior.get(campo):
                    mesclado[campo] = anterior[campo]
            # RECUSA também é decisão humana (review do Codex no PR #526): o
            # ingestor manda `rag_status=pendente` por default e o merge
            # devolvia ao fluxo de pendentes um documento que o curador já
            # tinha rejeitado — a rejeição sumia a cada atualização periódica.
            # VIGÊNCIA decidida por curador também é decisão humana (review de
            # segurança do PR #642): o job semanal do Planalto reescreve
            # `legal_status` a cada re-feed, inclusive por este atalho
            # "inalterado". Sem esta preservação, um diploma marcado
            # 'revogada' no painel voltava a 'vigente' sozinho — e, como
            # `governance_updated_by` continua apontando para o curador, o
            # estado revertido AINDA PARECERIA decisão humana.
            if _vigencia_de_curadoria(anterior):
                for campo in _CAMPOS_VIGENCIA:
                    if campo in anterior:
                        mesclado[campo] = anterior[campo]
                    else:
                        mesclado.pop(campo, None)
            if anterior.get("rag_status") == "recusado":
                mesclado["rag_status"] = "recusado"
            elif (
                preservar_aprovacao_rag
                and anterior.get("rag_status") == "aprovado"
                and extra.get("rag_status") == "pendente"
            ):
                # AI-079 (auditoria 2026-07-26): doc que EXIGE revisão humana ainda
                # não revisada NÃO re-promove 'pendente'→'aprovado' no re-feed —
                # senão o estoque DataJud aprovado antes do fix nunca seria
                # rebaixado. Sem pendência de revisão, preserva a aprovação.
                requer_revisao = bool(mesclado.get("requires_human_review")) and \
                    not bool(mesclado.get("human_reviewed"))  # já preservado acima
                if not requer_revisao:
                    mesclado["rag_status"] = "aprovado"
            existente.extra = mesclado
        existente.titulo = titulo
        existente.categoria = categoria
        existente.fonte = fonte
        existente.tribunal = tribunal
        existente.client_id = client_id
        existente.case_id = case_id
        existente.atualizado_em = agora
        return "inalterado"

    if chunks is not None:
        chunks = [normalizar(c) for c in chunks if c and c.strip()]
        if not chunks:
            chunks = chunk_texto(conteudo)
        chunks_com_pagina = [(c, None) for c in chunks]
    elif paginas:
        chunks_com_pagina = chunk_texto_com_paginas(paginas)
    else:
        chunks_com_pagina = [(c, None) for c in chunk_texto(conteudo)]

    textos = [c[0] for c in chunks_com_pagina]
    vetores = await gerar_embeddings(textos) if embutir_vetores else None
    status_novo = "indexado" if vetores else "pendente"

    if existente:
        # Conteúdo mudou → NOVA VERSÃO. A versão antiga vira histórico.
        existente.vigente = False
        await db.flush()
        doc_id = str(uuid4())
        # G4 — base_rag derivada de client_id/case_id
        from app.models.rag import BaseRag
        base = BaseRag.caso if case_id else (BaseRag.escritorio if client_id else BaseRag.publica)
        # Preservar campos curados de vigência na nova versão (mesmo padrão do
        # caminho "inalterado"). CONTEÚDO mudou, mas a decisão humana sobre
        # vigência — se houver — continua aplicável ao diploma atualizado.
        extra_nova_versao = dict(extra or {})
        anterior = dict(existente.extra or {})
        if _vigencia_de_curadoria(anterior):
            for campo in _CAMPOS_VIGENCIA:
                if campo in anterior:
                    extra_nova_versao[campo] = anterior[campo]
                else:
                    extra_nova_versao.pop(campo, None)
        db.add(KnowledgeDoc(
            id=doc_id, titulo=titulo, categoria=categoria,
            fonte=fonte, tribunal=tribunal, extra=extra_nova_versao,
            client_id=client_id, case_id=case_id,
            base_rag=base,
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
        from app.models.rag import BaseRag
        base = BaseRag.caso if case_id else (BaseRag.escritorio if client_id else BaseRag.publica)
        db.add(KnowledgeDoc(
            id=doc_id, titulo=titulo, categoria=categoria,
            fonte=fonte, tribunal=tribunal, extra=extra,
            client_id=client_id, case_id=case_id,
            base_rag=base,
            chave_origem=chave_origem, hash_conteudo=h, atualizado_em=agora,
            status_indexacao=status_novo,
        ))
        await db.flush()   # FK: doc antes dos chunks
        resultado = "novo"

    for i, (c, pagina) in enumerate(chunks_com_pagina):
        db.add(KnowledgeChunk(
            id=str(uuid4()), doc_id=doc_id, chunk_index=i, conteudo=c,
            embedding=vetores[i] if vetores else None,
            pagina=pagina,
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

    # Marcador vitalício: uma vez que a fonte trouxe registro novo, ela
    # "já produziu" — para sempre. `registros_total` é sobrescrito a cada
    # execução, então uma consulta legítima com zero resultados apagaria o
    # histórico e faria uma fonte produtiva virar `nunca_produziu` no painel.
    if novos > 0:
        f.ja_produziu = True

    # Contagem de execuções improdutivas consecutivas. `registros_novos` guarda
    # só a última execução, então "rodou N vezes seguidas sem trazer nada" tem de
    # ser contado aqui — é o sinal que distingue um coletor quebrado de um
    # saudável em período vazio, e é o que faltava para o DJEN gritar.
    # - ERRO não conta: o problema dela já é o erro.
    # - PARCIAL não conta nem reseta: não é sucesso pleno (parte do lote
    #   falhou) e o sinal dela é a própria parcialidade, não a improdutividade.
    # - Sucesso com registros RECEBIDOS porém inalterados (novos=0, total>0)
    #   é ingestão idempotente saudável — o job semanal do Planalto reprocessa
    #   o catálogo fixo, o do STJ relê o lote mensal — e RESETA o contador:
    #   a fonte provou que chega à origem e processa.
    # - Só o run zerado DE VERDADE (nada recebido nem processado) incrementa.
    if status in ("erro", "parcial"):
        pass
    elif novos > 0 or total > 0:
        f.execucoes_zeradas_consecutivas = 0
    else:
        f.execucoes_zeradas_consecutivas = int(
            f.execucoes_zeradas_consecutivas or 0
        ) + 1


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
        # Erro sem mensagem é pior que o erro: o painel mostra "erro" e não há
        # por onde começar a investigar. Foi o estado em que a fonte `anpd` foi
        # encontrada (`ultimo_erro: null`). Exceção sem texto — ou falha fora do
        # try — passa a gravar ao menos a origem.
        if status == "erro" and not (erro or "").strip():
            erro = (
                "Falha sem mensagem capturada. A exceção não trouxe texto ou a "
                "falha ocorreu fora do bloco instrumentado — investigue o "
                f"ingestor '{slug}' pelos logs do container."
            )
        try:
            async with AsyncSessionLocal() as db:
                await marcar_execucao(db, slug, status=status,
                                      novos=novos, total=total, erro=erro)
                await db.commit()
        except Exception as e:
            logger.error(f"[Ingestao:{slug}] falha ao marcar execução: {e}")
    logger.info(f"[Ingestao:{slug}] {status} — {novos} novos / {total} processados")
    return novos, total