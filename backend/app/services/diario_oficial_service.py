# ── app/services/diario_oficial_service.py ────────────────────────────────────
# Monitor de Diário Oficial — captura publicações pela API do LexML/DOU.
# Usa a API pública do DOU (imprensa.in.gov.br) sem autenticação.
# Sem LGPD: não envia dados de clientes, apenas palavras-chave genéricas.
from __future__ import annotations
import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

DOU_SEARCH_URL = "https://www.in.gov.br/consulta/-/buscar/dou"


async def buscar_dou(keyword: str, data_pub: date | None = None) -> list[dict]:
    """
    Consulta o Diário Oficial da União pela API do in.gov.br.
    Retorna lista de publicações com: titulo, resumo, link, secao, data.
    Retorna [] em caso de falha ou sem resultado.
    """
    import httpx

    data_str = (data_pub or date.today() - timedelta(days=1)).strftime("%d-%m-%Y")
    params = {
        "q":            keyword,
        "exactDate":    data_str,
        "sortType":     "0",
        "_search":      "null",
        "view":         "simple",
        "numberOfPage": "1",
        "publishedFrom": data_str,
        "publishedTo":   data_str,
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(DOU_SEARCH_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning(f"[DOU] Falha ao consultar '{keyword}': {e}")
        return []

    # Normaliza resposta
    resultados = []
    for item in data.get("content", {}).get("jsonArray", []):
        resultados.append({
            "titulo":          item.get("title", ""),
            "resumo":          item.get("excerpt", ""),
            "link":            f"https://www.in.gov.br{item.get('urlTitle', '')}",
            "secao":           str(item.get("artType", "")).replace("DOU - ", ""),
            "data_publicacao": data_pub or date.today() - timedelta(days=1),
            "edicao":          item.get("editionNumber", ""),
        })
    return resultados


async def processar_alertas_dou(db) -> int:
    """
    Verifica todas as keywords ativas, busca no DOU e persiste os alertas novos.
    Retorna o total de alertas novos criados.
    """
    from uuid import uuid4
    from sqlalchemy import select
    from app.models.diario_oficial import DiarioOficialKeyword, DiarioOficialAlerta

    ontem = date.today() - timedelta(days=1)

    keywords = (await db.execute(
        select(DiarioOficialKeyword).where(
            DiarioOficialKeyword.ativo.is_(True),
            DiarioOficialKeyword.fonte == "dou",
        )
    )).scalars().all()

    if not keywords:
        return 0

    novos = 0
    for kw in keywords:
        resultados = await buscar_dou(kw.keyword, ontem)
        for r in resultados:
            # Dedup: verifica se esse link já existe
            existe = (await db.execute(
                select(DiarioOficialAlerta).where(
                    DiarioOficialAlerta.link == r["link"],
                    DiarioOficialAlerta.keyword_id == kw.id,
                )
            )).scalar_one_or_none()
            if existe:
                continue

            alerta = DiarioOficialAlerta(
                id=str(uuid4()),
                fonte="dou",
                edicao=r["edicao"],
                data_publicacao=r["data_publicacao"],
                secao=r["secao"],
                titulo=r["titulo"][:500],
                resumo=r["resumo"][:2000],
                link=r["link"],
                keyword_match=kw.keyword[:200],
                keyword_id=kw.id,
                case_id=kw.case_id,
            )
            db.add(alerta)
            novos += 1

    if novos > 0:
        await db.commit()

    return novos
