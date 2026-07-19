# ── app/services/juris_import/tjmg.py ────────────────────────────────────────
# Conector TJMG on-demand — liga a busca pública de acórdãos do TJMG
# (jurisprudencia_externa.buscar_tjmg, formulário pesquisaPalavrasEspelhoAcordao)
# ao pipeline de IMPORTAÇÃO (RAG + base de citações validadas) via o MESMO
# registry de fontes do juris_import.
#
# FRAGILIDADE (documentada): o TJMG NÃO tem API de dados abertos — a fonte é o
# formulário HTML público, parseado por regex tolerante em buscar_tjmg. Se o
# HTML mudar, o resultado degrada para LISTA VAZIA (fail-safe; nunca levanta),
# e o job marca a fonte como parcial/erro no painel — sem quebrar o worker.
#
# DEDUP: chave PRINCIPAL "tjmg:<numero_acordao>" — o MESMO keyspace do ingestor
# agendado (app/services/ingestors/tjmg.py, _chave): o crawler agendado não
# reimporta o que o advogado importou on-demand, e vice-versa. A chave canônica
# "julgado:TJMG:<dígitos>" entra automaticamente no dedup (chaves_dedup).
#
# ANO: o formulário do TJMG aceita janela de datas (dd/mm/aaaa) — quando `ano`
# é informado, a janela 01/01..31/12 do ano vai SERVER-SIDE, e o filtro
# client-side (no_ano) permanece como garantia final.
#
# LGPD: acórdãos públicos oficiais; parse local, sem IA externa.
from __future__ import annotations

import logging

from app.services.juris_import.base import JulgadoNormalizado, no_ano
from app.services.jurisprudencia_externa import buscar_tjmg

logger = logging.getLogger("ejc.juris_import.tjmg")

PAGINA_TAMANHO = 50
MAX_PAGINAS = 5          # paginação LIMITADA — nunca varre o acervo inteiro


def normalizar_item(item: dict) -> JulgadoNormalizado | None:
    """Item do parser TJMG (dict de jurisprudencia_externa._item) →
    JulgadoNormalizado. Sem número OU sem URL de espelho → None: o gate de
    citações valida por número/URL oficial, e a chave de dedup compartilhada
    com o ingestor agendado exige o número do acórdão."""
    ementa = (item.get("ementa") or "").strip()
    numero = (item.get("numero_acordao") or "").strip()
    url = (item.get("link_original") or "").strip()
    if len(ementa) < 50 or not numero or not url:
        return None
    return JulgadoNormalizado(
        tribunal="TJMG",
        numero=numero[:80],
        data=item.get("data_julgamento"),
        ementa=ementa[:20000],
        url_fonte=url,
        orgao_julgador=item.get("orgao_julgador") or None,
        relator=item.get("relator") or None,
        classe=item.get("classe") or None,
        # MESMO keyspace do ingestor agendado (ingestors/tjmg.py::_chave).
        chave_principal=f"tjmg:{numero}",
    )


async def buscar(
    consulta: str, tribunal: str | None = None, limite: int = 20,
    ano: int | None = None,
) -> list[JulgadoNormalizado]:
    """Busca acórdãos do TJMG por palavras. Fail-safe: erro de rede/HTML na
    fonte degrada para lista vazia (comportamento herdado de buscar_tjmg)."""
    trib = (tribunal or "").strip().upper()
    if trib and trib != "TJMG":
        return []                            # fonte cobre apenas o TJMG
    if not (consulta or "").strip():
        return []
    data_ini = f"01/01/{ano}" if ano else ""
    data_fim = f"31/12/{ano}" if ano else ""
    resultados: list[JulgadoNormalizado] = []
    vistos: set[str] = set()
    for pagina in range(1, MAX_PAGINAS + 1):
        itens = await buscar_tjmg(
            consulta, pagina=pagina, por_pagina=PAGINA_TAMANHO,
            data_inicial=data_ini, data_final=data_fim,
        )
        if not itens:
            break
        for item in itens:
            j = normalizar_item(item)
            if j is None:
                continue
            if not no_ano(j.data, ano):
                continue                     # garantia client-side do ano
            chave = j.chave_dedup()
            if chave in vistos:
                continue
            vistos.add(chave)
            resultados.append(j)
            if len(resultados) >= limite:
                return resultados
        if len(itens) < PAGINA_TAMANHO:
            break                            # página incompleta = fim
    return resultados
