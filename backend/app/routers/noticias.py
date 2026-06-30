# ── app/routers/noticias.py ───────────────────────────────────────────────────
# Agregador de notícias jurídicas externas (RSS) — ConJur + JOTA por padrão.
# Copyright-safe: só manchete + resumo curto + link para a fonte (sem reproduzir
# o artigo). Cache em memória (TTL) para não bater nos feeds a cada request.
# Sem dependência nova: httpx (já usado) + xml.etree (stdlib).
from __future__ import annotations
import time
import re
import asyncio
import logging
from xml.etree import ElementTree as ET
from typing import Optional
import httpx
from fastapi import APIRouter, Depends, Query
from app.core.security import get_current_user
from app.models.user import User

logger = logging.getLogger("ejc.noticias")
router = APIRouter(prefix="/noticias", tags=["Notícias Jurídicas"])

# Fonte: (rótulo, url). Migalhas/OAB-MG não expõem RSS acessível (404/403);
# ConJur e JOTA cobrem bem notícia jurídica, OAB e legislação.
FEEDS = [
    ("ConJur", "https://www.conjur.com.br/rss.xml"),
    ("JOTA",   "https://www.jota.info/feed"),
]
_TTL = 1800  # 30 min
_cache: dict = {"ts": 0.0, "itens": []}
_TAG_RE = re.compile(r"<[^>]+>")


def _local(tag: str) -> str:
    return tag.split("}")[-1].lower()


def _limpar(txt: str, n: int = 220) -> str:
    txt = _TAG_RE.sub("", txt or "").replace("&nbsp;", " ")
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt[:n] + ("…" if len(txt) > n else "")


def _parse(xml: bytes, fonte: str) -> list[dict]:
    out: list[dict] = []
    try:
        root = ET.fromstring(xml)
    except Exception:
        return out
    for el in root.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        titulo = link = data = resumo = ""
        for ch in el:
            t = _local(ch.tag)
            if t == "title":
                titulo = (ch.text or "").strip()
            elif t == "link":
                link = (ch.text or "").strip() or ch.attrib.get("href", "")
            elif t in ("pubdate", "published", "updated", "date"):
                data = (ch.text or "").strip()
            elif t in ("description", "summary", "encoded") and not resumo:
                resumo = _limpar(ch.text or "")
        if titulo and link:
            out.append({"titulo": titulo, "link": link, "data": data,
                        "resumo": resumo, "fonte": fonte})
    return out


async def _buscar_feed(client: httpx.AsyncClient, fonte: str, url: str) -> list[dict]:
    try:
        r = await client.get(url, timeout=12, follow_redirects=True,
                             headers={"User-Agent": "Mozilla/5.0 (compatible; EJCbot/1.0)"})
        r.raise_for_status()
        return _parse(r.content, fonte)
    except Exception as e:
        logger.warning(f"Falha no feed {fonte}: {e}")
        return []


@router.get("")
async def listar_noticias(
    limit: int = Query(24, ge=1, le=60),
    forcar: bool = Query(False, description="ignora cache"),
    cu: User = Depends(get_current_user),
):
    agora = time.time()
    if forcar or (agora - _cache["ts"]) > _TTL or not _cache["itens"]:
        async with httpx.AsyncClient() as client:
            grupos = await asyncio.gather(*[_buscar_feed(client, f, u) for f, u in FEEDS])
        itens = [i for g in grupos for i in g]
        # ordena por data (string ISO/RFC desc aproxima recência; fallback estável)
        itens.sort(key=lambda x: x.get("data", ""), reverse=True)
        if itens:                       # só atualiza cache se veio algo
            _cache["itens"] = itens
            _cache["ts"] = agora
    return {
        "itens": _cache["itens"][:limit],
        "fontes": [f for f, _ in FEEDS],
        "atualizado_em": _cache["ts"],
        "total": len(_cache["itens"]),
    }
