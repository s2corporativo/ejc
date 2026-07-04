# ── app/services/ingestors/senado.py ─────────────────────────────────────────
# Monitor legislativo — Senado Federal (Dados Abertos, sem auth).
# Par do monitor da Câmara: ingere a EMENTA de matérias do ano corrente dos
# tipos mais relevantes. Usa o endpoint pesquisa/lista.json (registros planos
# com Ementa) — mais estável que materia/atualizadas (JSON profundamente aninhado).
#
# Incremental por ano + dedup por código da matéria.
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ingestion_service import fetch, upsert_documento

logger = logging.getLogger("ejc.ingestao.senado")

API = "https://legis.senado.leg.br/dadosabertos/materia/pesquisa/lista.json"

# Tipos relevantes no Senado (PLS = Projeto de Lei do Senado, histórico).
SIGLAS = ["PL", "PEC", "PLP", "PLS"]
MAX_POR_SIGLA = 200


def _materias(payload: dict) -> list[dict]:
    """Extrai a lista de matérias do envelope (defensivo a variações)."""
    raiz = payload.get("PesquisaBasicaMateria", {})
    mats = raiz.get("Materias", {})
    if isinstance(mats, dict):
        m = mats.get("Materia", [])
    else:
        m = raiz.get("Materia", [])
    if isinstance(m, dict):
        return [m]
    return m if isinstance(m, list) else []


async def ingerir(db: AsyncSession) -> tuple[int, int]:
    """Ingere ementas de matérias do ano corrente. Retorna (novos, total)."""
    novos = total = 0
    ano = date.today().year

    for sigla in SIGLAS:
        try:
            r = await fetch(API, params={"ano": ano, "sigla": sigla}, timeout=30)
            mats = _materias(r.json())
            for m in mats[:MAX_POR_SIGLA]:
                ementa = (m.get("Ementa") or "").strip()
                if len(ementa) < 50:
                    continue
                cod = m.get("Codigo")
                ident = m.get("DescricaoIdentificacao") or f"{sigla} {m.get('Numero')}/{ano}"
                conteudo = (
                    f"{ident} (Senado Federal)\n"
                    f"Autor: {m.get('Autor','')}\n"
                    f"Data: {m.get('Data','')}\n\n"
                    f"Ementa: {ementa}"
                )
                total += 1
                res = await upsert_documento(
                    db, titulo=ident[:500], categoria="proposicao_legislativa",
                    conteudo=conteudo, chave_origem=f"senado:{cod}",
                    fonte=m.get("UrlDetalheMateria") or API,
                    extra={"sigla": sigla, "ano": ano, "casa": "senado",
                           "numero": m.get("Numero")},
                    confianca="alta",   # fonte oficial (Senado Federal)
                )
                if res in ("novo", "atualizado"):
                    novos += 1
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.warning(f"Senado {sigla}: {type(e).__name__}: {e}")
    return novos, total
