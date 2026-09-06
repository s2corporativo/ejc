"""
Crawler/agregador de precedentes — EJC.

Este módulo substitui o stub antigo por um agregador honesto e seguro sobre as
fontes já existentes no sistema:

- LexML;
- TJMG;
- DataJud/CNJ, quando habilitado;
- STJ/STF marcados explicitamente como nao_implementado nesta versão.

Regra de confiança: nenhuma fonte indisponível vira "success" vazio inventado.
Cada fonte retorna seu próprio status e o agregador só retorna status success se
ao menos uma fonte executada respondeu com sucesso.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("ejc.crawler_precedentes")

_FONTES_VALIDAS = {"lexml", "tjmg", "datajud", "stj", "stf"}
_FONTES_DEFAULT = ["lexml", "tjmg"]


def _normalizar_fonte(fonte: str) -> str:
    return (fonte or "").strip().lower()


def _normalizar_precedente(item: dict[str, Any], fonte: str) -> dict[str, Any]:
    """Converte item de jurisprudência externa para contrato de precedente."""
    ementa = (item.get("ementa") or item.get("texto") or "").strip()
    titulo = (item.get("titulo") or "").strip()
    return {
        "titulo": titulo[:300] or (ementa[:120] if ementa else "Precedente sem título"),
        "ementa": ementa[:2000],
        "tribunal": item.get("tribunal") or "",
        "relator": item.get("relator") or "",
        "numero_acordao": item.get("numero_acordao") or item.get("numero_cnj") or "",
        "data_julgamento": item.get("data_julgamento"),
        "fonte": item.get("fonte") or fonte,
        "link_original": item.get("link_original") or item.get("url") or "",
        "area_juridica": item.get("area_juridica") or "",
    }


def _chave_dedup(item: dict[str, Any]) -> str:
    numero = item.get("numero_acordao")
    tribunal = item.get("tribunal")
    if numero or tribunal:
        return f"{tribunal}:{numero}".strip().lower()
    ementa = re.sub(r"\s+", " ", (item.get("ementa") or "").strip().lower())
    return ementa[:240]


async def _buscar_lexml(termo: str, pagina: int, por_pagina: int) -> dict[str, Any]:
    from app.services.jurisprudencia_externa import buscar_lexml

    try:
        itens = await buscar_lexml(termo, tipo="jurisprudencia", pagina=pagina, por_pagina=por_pagina)
        precedentes = [_normalizar_precedente(i, "LexML") for i in itens]
        return {"status": "success", "fonte": "lexml", "total": len(precedentes), "precedentes": precedentes}
    except Exception as exc:  # noqa: BLE001
        logger.warning("LexML falhou no agregador de precedentes: %s", exc)
        return {"status": "erro", "fonte": "lexml", "mensagem": "Falha ao consultar LexML.", "total": 0, "precedentes": []}


async def _buscar_tjmg(termo: str, pagina: int, por_pagina: int) -> dict[str, Any]:
    from app.services.jurisprudencia_externa import buscar_tjmg

    try:
        itens = await buscar_tjmg(termo, pagina=pagina, por_pagina=por_pagina)
        precedentes = [_normalizar_precedente(i, "TJMG") for i in itens]
        return {"status": "success", "fonte": "tjmg", "total": len(precedentes), "precedentes": precedentes}
    except Exception as exc:  # noqa: BLE001
        logger.warning("TJMG falhou no agregador de precedentes: %s", exc)
        return {"status": "erro", "fonte": "tjmg", "mensagem": "Falha ao consultar TJMG.", "total": 0, "precedentes": []}


async def _buscar_datajud(numero_cnj: str | None) -> dict[str, Any]:
    if not numero_cnj:
        return {
            "status": "indisponivel",
            "fonte": "datajud",
            "mensagem": "Fonte DataJud exige numero_cnj.",
            "total": 0,
            "precedentes": [],
        }
    try:
        from app.services import datajud_service as dj

        if not getattr(dj.settings, "DATAJUD_ENABLED", False) or not getattr(dj.settings, "DATAJUD_API_KEY", None):
            return {
                "status": "indisponivel",
                "fonte": "datajud",
                "mensagem": "DataJud desabilitado ou sem credencial.",
                "total": 0,
                "precedentes": [],
            }
        info = await dj.consultar_processo(numero_cnj)
    except Exception as exc:  # noqa: BLE001
        logger.warning("DataJud falhou no agregador de precedentes: %s", exc)
        return {"status": "erro", "fonte": "datajud", "mensagem": "Falha ao consultar DataJud.", "total": 0, "precedentes": []}

    if not info:
        return {"status": "success", "fonte": "datajud", "total": 0, "precedentes": []}

    precedente = _normalizar_precedente({
        "titulo": f"Processo DataJud {numero_cnj}",
        "ementa": str(info.get("classe") or info.get("orgao") or "Processo localizado no DataJud"),
        "tribunal": info.get("tribunal") or info.get("orgao") or "DataJud/CNJ",
        "numero_cnj": numero_cnj,
        "fonte": "DataJud/CNJ",
    }, "DataJud/CNJ")
    precedente["movimentos"] = info.get("movimentos", [])
    return {"status": "success", "fonte": "datajud", "total": 1, "precedentes": [precedente]}


def _fonte_nao_implementada(fonte: str) -> dict[str, Any]:
    return {
        "status": "nao_implementado",
        "fonte": fonte,
        "mensagem": f"Fonte {fonte.upper()} ainda não possui conector seguro nesta versão.",
        "total": 0,
        "precedentes": [],
    }


async def buscar_precedentes(
    termo: str,
    fontes: list[str] | None = None,
    *,
    numero_cnj: str | None = None,
    pagina: int = 1,
    por_pagina: int = 10,
) -> dict[str, Any]:
    """Busca precedentes em múltiplas fontes com status honesto por fonte."""
    termo = (termo or "").strip()
    fontes_norm = [_normalizar_fonte(f) for f in (fontes or _FONTES_DEFAULT)]
    fontes_norm = [f for f in fontes_norm if f in _FONTES_VALIDAS]
    if not fontes_norm:
        fontes_norm = list(_FONTES_DEFAULT)

    resultados: dict[str, Any] = {}
    for fonte in fontes_norm:
        if fonte == "lexml":
            resultados[fonte] = await _buscar_lexml(termo, pagina, por_pagina)
        elif fonte == "tjmg":
            resultados[fonte] = await _buscar_tjmg(termo, pagina, por_pagina)
        elif fonte == "datajud":
            resultados[fonte] = await _buscar_datajud(numero_cnj)
        elif fonte in {"stj", "stf"}:
            resultados[fonte] = _fonte_nao_implementada(fonte)

    precedentes: list[dict[str, Any]] = []
    vistos: set[str] = set()
    houve_sucesso = False
    for res in resultados.values():
        if res.get("status") == "success":
            houve_sucesso = True
        for item in res.get("precedentes") or []:
            chave = _chave_dedup(item)
            if chave in vistos:
                continue
            vistos.add(chave)
            precedentes.append(item)

    return {
        "status": "success" if houve_sucesso else "erro",
        "termo": termo,
        "fontes_consultadas": fontes_norm,
        "total_encontrado": len(precedentes),
        "precedentes": precedentes,
        "fontes": resultados,
    }


class CrawlerPrecedentes:
    def __init__(self):
        self.headers = {"User-Agent": "EJC-Jurimetria-Bot/3.0"}


crawler = CrawlerPrecedentes()
