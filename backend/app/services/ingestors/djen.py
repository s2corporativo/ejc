# ── app/services/ingestors/djen.py ──────────────────────────────────────────
# Ingestor de comunicações processuais do DJEN (Diário de Justiça Eletrônico
# Nacional) via API Comunica/CNJ (Resolução CNJ 569/2024).
#     GET https://comunicaapi.pje.jus.br/api/v1/comunicacao
# Pública, sem autenticação. Consulta por OAB monitorada (numeroOab + ufOab),
# janela incremental diária (dataDisponibilizacaoInicio/Fim) e paginação.
#
# Papel no EJC: a retenção da API Comunica é LIMITADA — este ingestor
# persiste cada comunicação como documento RAG (knowledge_docs), tornando o
# EJC o arquivo histórico permanente e pesquisável do escritório.
#
# Relação com o fluxo de intimações (migration 065 / djen_service.py):
# `job_djen_intimacoes` (scheduler, 06h30) já alimenta a tabela
# djen_comunicacoes por advogado com OAB cadastrada no cadastro de usuários
# (djen_service.capturar_para_advogado: dedup, vínculo a caso, notificação).
# Este ingestor NÃO duplica esse fluxo: ele cobre a persistência RAG das
# OABs em DJEN_OABS_MONITORADAS (que podem incluir OABs sem usuário no EJC).
#
# Rate limit: a API não documenta limites — postura conservadora: coleta
# SEQUENCIAL (OAB a OAB, página a página) com pausa entre páginas.
#
# VALIDAÇÃO REAL: o ambiente de desenvolvimento/CI não alcança
# comunicaapi.pje.jus.br (proxy bloqueia o host). Todos os testes usam
# fixtures/mocks; a validação contra a API real só é possível na VPS.
from __future__ import annotations

import asyncio
import hashlib
import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.djen_service import (
    buscar_caso_ativo_por_processo,
    extrair_numero_cnj,
    normalizar_processo,
)
from app.services.ingestion_service import fetch, upsert_documento

logger = logging.getLogger("ejc.ingestao.djen")

BASE = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"
ITENS_POR_PAGINA = 100
MAX_PAGINAS = 30          # teto de segurança por OAB/execução (30×100 itens)
PAUSA_ENTRE_PAGINAS = 0.5  # segundos — conservador (API sem rate limit documentado)

_TAG_RE = re.compile(r"<[^>]+>")


# ══════════════════════════════════════════════════════════════════════════
# Parsing / normalização (puros — testáveis sem rede)
# ══════════════════════════════════════════════════════════════════════════

def parse_oabs(csv: str) -> list[tuple[str, str]]:
    """Converte o CSV de settings ("12345/MG,67890/MG") em [(numero, UF)].

    Tolerante a espaços, entradas vazias e máscara no número (só dígitos são
    mantidos). Entradas sem "/UF" válida são ignoradas com aviso.
    """
    oabs: list[tuple[str, str]] = []
    for parte in (csv or "").split(","):
        parte = parte.strip()
        if not parte:
            continue
        num, sep, uf = parte.partition("/")
        num = re.sub(r"\D", "", num)
        uf = uf.strip().upper()
        if not sep or not num or len(uf) != 2 or not uf.isalpha():
            logger.warning(f"DJEN: OAB monitorada inválida ignorada: {parte!r}")
            continue
        oabs.append((num, uf))
    return oabs


def _campo(it: dict, *nomes: str) -> str:
    """Primeiro valor não-vazio entre aliases (a API mistura camelCase e
    snake_case conforme o endpoint/versão)."""
    for n in nomes:
        v = it.get(n)
        if v:
            return str(v)
    return ""


def _limpar_html(texto: str) -> str:
    """Remove tags HTML do texto da comunicação (a API devolve HTML)."""
    return _TAG_RE.sub(" ", texto or "").strip()


def chave_origem(it: dict) -> str:
    """Chave determinística de dedup no RAG: "djen:{id}" quando a API traz
    id/hash; senão hash SHA-1 estável dos campos identificadores do item."""
    ext = it.get("id") or it.get("hash")
    if ext:
        return f"djen:{ext}"
    base = "|".join([
        _campo(it, "numeroProcesso", "numero_processo", "numeroprocessocommascara"),
        _campo(it, "dataDisponibilizacao", "data_disponibilizacao"),
        _campo(it, "tipoComunicacao", "tipo_comunicacao"),
        _campo(it, "texto"),
    ])
    return "djen:" + hashlib.sha1(base.encode("utf-8")).hexdigest()


def montar_documento(it: dict) -> dict | None:
    """Normaliza um item da API em kwargs para upsert_documento.

    Retorna None para itens sem conteúdo aproveitável (sem texto).
    """
    if not isinstance(it, dict):
        return None
    texto = _limpar_html(_campo(it, "texto"))
    if not texto:
        return None

    tribunal = _campo(it, "siglaTribunal", "sigla_tribunal")[:20]
    tipo = _campo(it, "tipoComunicacao", "tipo_comunicacao")
    orgao = _campo(it, "nomeOrgao", "nome_orgao", "orgao")
    data = _campo(it, "dataDisponibilizacao", "data_disponibilizacao")[:10]
    link = _campo(it, "link")
    num_proc = _campo(it, "numeroProcesso", "numero_processo",
                      "numeroprocessocommascara")
    if not num_proc:  # fallback: extrai o nº CNJ do próprio texto
        num_proc = extrair_numero_cnj(texto) or ""

    cab = [f"Comunicação processual (DJEN){' — ' + tribunal if tribunal else ''}"]
    if num_proc:
        cab.append(f"Processo: {num_proc}")
    if tipo:
        cab.append(f"Tipo: {tipo}")
    if orgao:
        cab.append(f"Órgão: {orgao}")
    if data:
        cab.append(f"Disponibilização: {data}")

    titulo = " — ".join(x for x in [
        f"DJEN {tribunal}".strip(), tipo, f"proc. {num_proc}" if num_proc else "",
    ] if x)
    return {
        "titulo": titulo[:500] or "DJEN — comunicação processual",
        "categoria": "comunicacao_processual",
        "conteudo": "\n".join(cab) + "\n\n" + texto,
        "chave_origem": chave_origem(it),
        "fonte": "djen",
        "tribunal": tribunal or None,
        "confianca": "alta",   # fonte oficial (DJEN/CNJ)
        "extra": {
            "numero_processo": normalizar_processo(num_proc) or None,
            "tipo_comunicacao": tipo or None,
            "orgao": orgao or None,
            "data_disponibilizacao": data or None,
            "link": link or None,
        },
    }


# ══════════════════════════════════════════════════════════════════════════
# Coleta (rede — mockada nos testes)
# ══════════════════════════════════════════════════════════════════════════

def _extrair_itens(payload) -> list[dict]:
    """Tolerante ao envelope: {"items": [...]} ou lista crua; senão []."""
    if isinstance(payload, dict):
        items = payload.get("items")
        return items if isinstance(items, list) else []
    return payload if isinstance(payload, list) else []


class DjenContratoError(RuntimeError):
    """A consulta ao DJEN não foi respondida no contrato esperado.

    Erro PRÓPRIO porque, num sistema de prazos, "a fonte não respondeu" e
    "não há intimação para esta OAB" levam a condutas opostas — e confundir os
    dois é a origem documentada da armadilha do JOB_DJEN.
    """


async def _coletar_oab(numero: str, uf: str, ini: str, fim: str) -> list[dict]:
    """Coleta paginada (sequencial + pausa) de uma OAB na janela [ini, fim]."""
    itens: list[dict] = []
    for pagina in range(1, MAX_PAGINAS + 1):
        r = await fetch(BASE, params={
            "numeroOab": numero,
            "ufOab": uf,
            "dataDisponibilizacaoInicio": ini,
            "dataDisponibilizacaoFim": fim,
            "itensPorPagina": ITENS_POR_PAGINA,
            "pagina": pagina,
        }, timeout=30)
        try:
            lote = _extrair_itens(r.json())
        except ValueError:
            logger.warning(f"DJEN OAB {numero}/{uf} p.{pagina}: JSON inválido")
            if pagina == 1:
                # Na PRIMEIRA página, JSON inválido significa que a consulta
                # não foi respondida (mudança de contrato, HTML de bloqueio) —
                # devolver lista vazia aqui faz "a fonte não respondeu" virar
                # "este advogado não tem intimação", que num sistema de prazos
                # é o erro mais caro possível. Nas páginas seguintes já há
                # itens colhidos, então parar e aproveitá-los é o correto.
                raise DjenContratoError(
                    f"DJEN OAB {numero}/{uf}: resposta sem JSON válido na "
                    "primeira página — consulta não foi respondida."
                )
            break
        itens.extend(x for x in lote if isinstance(x, dict))
        if len(lote) < ITENS_POR_PAGINA:
            break   # última página
        await asyncio.sleep(PAUSA_ENTRE_PAGINAS)
    return itens


async def ingerir(db: AsyncSession) -> tuple[int, int]:
    """Ingere no RAG as comunicações da janela incremental de cada OAB
    monitorada (DJEN_OABS_MONITORADAS). Retorna (novos, total_processados).

    Tolerante a falha por OAB (uma OAB com erro não derruba as demais) e a
    itens malformados (ignorados). Idempotente via chave_origem.
    """
    from datetime import date, timedelta
    s = get_settings()
    oabs = parse_oabs(s.DJEN_OABS_MONITORADAS)
    if not oabs:
        logger.info("DJEN: nenhuma OAB monitorada configurada — nada a fazer")
        return 0, 0

    fim = date.today()
    ini = fim - timedelta(days=max(1, s.DJEN_INGEST_JANELA_DIAS))

    novos = total = 0
    for numero, uf in oabs:   # SEQUENCIAL de propósito (rate limit desconhecido)
        try:
            itens = await _coletar_oab(numero, uf, ini.isoformat(), fim.isoformat())
            n_oab = 0
            for it in itens:
                doc = montar_documento(it)
                if not doc:
                    continue
                # LGPD / isolamento cross-tenant: a comunicação processual
                # contém PII de terceiros (nomes das partes, nº e teor da
                # intimação). Ela SÓ pode entrar no RAG vinculada ao escopo do
                # caso/cliente correto — nunca como conhecimento global
                # recuperável por qualquer cliente. Resolve o caso ATIVO pelo
                # nº do processo (normalizado no extra por montar_documento).
                num_proc = (doc.get("extra") or {}).get("numero_processo")
                case = await buscar_caso_ativo_por_processo(db, num_proc)
                if case is None:
                    # Processo não cadastrado (ou caso encerrado/arquivado):
                    # NÃO poluir o RAG global com PII de terceiros. Pula a
                    # ingestão desta comunicação (o fluxo de intimações em
                    # djen_service segue independente deste ingestor RAG).
                    logger.info(
                        "DJEN OAB %s/%s: comunicação do processo %s sem caso "
                        "ativo cadastrado — ingestão RAG pulada (evita PII de "
                        "terceiros no conhecimento global)",
                        numero, uf, num_proc or "?",
                    )
                    continue
                # Vincula ao escopo correto: recuperável apenas dentro do caso
                # e do cliente donos do processo.
                doc["case_id"] = case.id
                doc["client_id"] = case.client_id
                doc["extra"]["oab_monitorada"] = f"{numero}/{uf}"
                doc["extra"]["rag_status"] = "aprovado"
                doc["extra"]["tipo_fonte"] = "comunicacao_processual_oficial"
                total += 1
                res = await upsert_documento(db, **doc)
                if res in ("novo", "atualizado"):
                    novos += 1
                    n_oab += 1
                if total % 50 == 0:   # commit em lotes (não segura em memória)
                    await db.commit()
            await db.commit()
            logger.info(f"DJEN OAB {numero}/{uf}: {n_oab} novos / {len(itens)} itens")
        except Exception as e:
            await db.rollback()
            logger.warning(f"DJEN OAB {numero}/{uf}: {type(e).__name__}: {e}")
    return novos, total
