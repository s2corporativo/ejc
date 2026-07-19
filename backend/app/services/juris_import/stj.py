# ── app/services/juris_import/stj.py ─────────────────────────────────────────
# Conector STJ — Portal de Dados Abertos (CKAN), "espelhos de acórdãos".
#
# CONTRATO DA API (o MESMO já verificado e em uso no ingestor agendado
# app/services/ingestors/stj.py):
#   • CKAN Action API: https://dadosabertos.web.stj.jus.br/api/3/action
#       GET /package_show?id=espelhos-de-acordaos-<orgao>
#     → result.resources[] com arquivos JSON mensais (nome AAAAMMDD.json).
#   • Cada arquivo JSON é uma lista de acórdãos com ementa, teseJuridica,
#     numeroRegistro, numeroProcesso, siglaClasse, ministroRelator,
#     nomeOrgaoJulgador, dataDecisao/dataPublicacao, referenciasLegislativas.
#   Fonte: https://dadosabertos.web.stj.jus.br/ (datasets "Espelhos de
#   acórdãos" por órgão julgador) — API pública CKAN padrão, sem chave.
#
# Este conector faz busca TEMÁTICA on-demand: baixa o lote mensal mais recente
# de cada órgão e filtra localmente os acórdãos cuja ementa contém TODOS os
# termos da consulta (comparação sem acentos). Sem scraping, sem IA externa.
from __future__ import annotations

import logging

from app.services.ingestion_service import fetch
# Reuso do ingestor agendado (contrato/campos já validados em produção):
from app.services.ingestors.stj import CKAN, ORGAOS, _monta_conteudo
from app.services.juris_import.base import (
    JulgadoNormalizado, no_ano, normalizar_termos, texto_normalizado,
)

logger = logging.getLogger("ejc.juris_import.stj")

MAX_REGISTROS_POR_ORGAO = 2000   # teto defensivo de varredura por arquivo


async def _ultimo_json(orgao: str) -> dict | None:
    """Recurso JSON mensal mais recente do órgão (nome AAAAMMDD.json)."""
    r = await fetch(f"{CKAN}/package_show", params={"id": orgao}, timeout=30)
    recursos = (r.json().get("result") or {}).get("resources") or []
    jsons = [x for x in recursos if (x.get("format") or "").upper() == "JSON"]
    if not jsons:
        return None
    jsons.sort(key=lambda x: x.get("name", ""))
    return jsons[-1]


def normalizar_registro(rec: dict, url_fonte: str) -> JulgadoNormalizado | None:
    """Espelho de acórdão do STJ → JulgadoNormalizado."""
    ementa = _monta_conteudo(rec)
    if not rec.get("ementa") or len(ementa) < 50:
        return None
    numero = str(rec.get("numeroProcesso") or rec.get("numeroRegistro") or "").strip()
    if not numero:
        return None
    data = (rec.get("dataDecisao") or rec.get("dataPublicacao") or "")[:10] or None
    registro = rec.get("numeroRegistro")
    return JulgadoNormalizado(
        tribunal="STJ",
        numero=numero,
        data=data,
        ementa=ementa[:20000],
        url_fonte=url_fonte,
        orgao_julgador=rec.get("nomeOrgaoJulgador"),
        relator=rec.get("ministroRelator"),
        classe=rec.get("siglaClasse"),
        # Chave PRINCIPAL = a MESMA do ingestor agendado (ingestors/stj.py,
        # "stj:<numeroRegistro>"): o que for importado aqui é reconhecido pelo
        # job diário (e vice-versa) — a canônica julgado:STJ:<dígitos> entra
        # automaticamente como chave extra de dedup via chaves_dedup().
        chave_principal=f"stj:{registro}" if registro else None,
    )


async def buscar(
    consulta: str, tribunal: str | None = None, limite: int = 20,
    ano: int | None = None,
) -> list[JulgadoNormalizado]:
    """Busca temática nos espelhos de acórdãos mais recentes do STJ.

    `ano`: filtro CLIENT-SIDE pela data da decisão (no_ano). Limitação da
    fonte: este conector varre apenas o LOTE MENSAL MAIS RECENTE de cada
    órgão — o filtro por ano é útil sobretudo para o ano CORRENTE (ex.:
    2026); anos antigos exigiriam varrer o histórico CKAN (fora do escopo
    da busca on-demand, teto defensivo)."""
    trib = (tribunal or "").strip().upper()
    if trib and trib != "STJ":
        return []                      # fonte cobre apenas o STJ
    termos = normalizar_termos(consulta)
    if not termos:
        return []
    resultados: list[JulgadoNormalizado] = []
    vistos: set[str] = set()
    for orgao in ORGAOS:
        if len(resultados) >= limite:
            break
        try:
            rec_json = await _ultimo_json(orgao)
            if not rec_json or not rec_json.get("url"):
                continue
            r = await fetch(rec_json["url"], timeout=60)
            dados = r.json()
            if not isinstance(dados, list):
                continue
        except Exception as e:   # órgão indisponível não derruba a busca toda
            logger.warning("STJ %s: %s: %s", orgao, type(e).__name__, e)
            continue
        for rec in dados[:MAX_REGISTROS_POR_ORGAO]:
            alvo = texto_normalizado(
                f"{rec.get('ementa') or ''} {rec.get('teseJuridica') or ''}")
            if not all(t in alvo for t in termos):
                continue
            j = normalizar_registro(rec, rec_json["url"])
            if j is None or j.chave_dedup() in vistos:
                continue
            if not no_ano(j.data, ano):
                continue                     # filtro client-side de ano
            vistos.add(j.chave_dedup())
            resultados.append(j)
            if len(resultados) >= limite:
                break
    return resultados
