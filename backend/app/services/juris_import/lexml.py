# ── app/services/juris_import/lexml.py ───────────────────────────────────────
# Conector LexML Brasil via SRU (Search/Retrieval via URL — padrão da Library
# of Congress). Fonte oficial da Rede de Informação Legislativa e Jurídica
# (Senado Federal) para LEGISLAÇÃO e JURISPRUDÊNCIA com URN persistente.
#
# CONTRATO DA API (confirmado em 2026-07 contra fontes públicas):
#   • GET https://www.lexml.gov.br/busca/SRU
#       ?operation=searchRetrieve&version=1.1
#       &query=<CQL>&startRecord=<N>&maximumRecords=<M>
#     CQL: termos livres e índices nomeados (ex.: `urn any decreto`,
#     `date any 2018`) combinados com `and`.
#   • Resposta: XML SRW (http://www.loc.gov/zing/srw/) com
#     srw:numberOfRecords e srw:records/srw:record/srw:recordData contendo
#     registro Dublin Core: dc:title, dc:description (ementa), dc:date,
#     dc:identifier (URL persistente), dc:type + campos LexML: urn,
#     tipoDocumento e facet-tipoDocumento (ex.: "Jurisprudência::Acórdão",
#     "Doutrina::Livro" — usado aqui para filtrar só jurisprudência).
#   Fontes: https://projeto.lexml.gov.br/ (documentação oficial do projeto,
#   Manual de Pesquisa), wrapper público py-lexml-acervo
#   (github.com/netoferraz/py-lexml-acervo — base URL e parâmetros exatos em
#   apis/acervo.py) e dataset espelho do acervo em
#   www12.senado.leg.br/dados-abertos/legislativo/legislacao/acervo-do-portal-lexml.
#
# LGPD: registros públicos oficiais; parse local, sem IA externa.
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET

from app.services.ingestion_service import fetch
from app.services.juris_import.base import (
    JulgadoNormalizado, no_ano, texto_normalizado,
)

logger = logging.getLogger("ejc.juris_import.lexml")

SRU_URL = "https://www.lexml.gov.br/busca/SRU"
PAGINA_TAMANHO = 50      # registros por página SRU
MAX_PAGINAS = 5          # paginação LIMITADA — nunca varre o acervo inteiro

# Autoridade na URN lex (urn:lex:br:<autoridade>:...) por tribunal — usada para
# refinar a CQL via índice `urn` (sintaxe `urn any <termo>` documentada no
# wrapper py-lexml-acervo). Apenas tribunais superiores, cujo padrão de
# autoridade é estável na base LexML; demais tribunais são filtrados
# client-side pelo próprio campo urn/autoridade do registro.
_URN_TRIBUNAL = {
    "STF": "supremo.tribunal.federal",
    "STJ": "superior.tribunal.justica",
    "TST": "tribunal.superior.trabalho",
}

# Siglas inferíveis do conteúdo da URN/autoridade (filtro client-side).
# Fragmentos EXATOS de URN (autoridade estável na base LexML):
_SIGLA_POR_FRAGMENTO = {
    "supremo.tribunal.federal": "STF",
    "superior.tribunal.justica": "STJ",
    "tribunal.superior.trabalho": "TST",
    "tribunal.superior.eleitoral": "TSE",
    "superior.tribunal.militar": "STM",
}


def _sigla_composta(alvo: str) -> str | None:
    """Sigla por fragmentos COMPOSTOS sobre URN + autoridade normalizadas
    (pontos/;/- viram espaço). 100% client-side — NÃO assume padrão de URN
    server-side; só reconhece o que de fato veio no registro.

    Ordem importa: Turma Recursal/Juizado Especial classifica como JEC ANTES
    do TJ do estado (Turmas Recursais pertencem ao sistema dos Juizados)."""
    if "turma recursal" in alvo or "juizado especial" in alvo:
        return "JEC"
    if "tribunal regional" in alvo and "trabalho" in alvo:
        m = re.search(r"\bregiao 0?(\d{1,2})\b|\b0?(\d{1,2})a? regiao\b", alvo)
        n = next((g for g in (m.groups() if m else ()) if g), None)
        return f"TRT-{int(n)}" if n else "TRT"
    if "tribunal" in alvo and "justica" in alvo and "minas gerais" in alvo:
        return "TJMG"
    return None


def _casa_tribunal(sigla_registro: str, trib: str) -> bool:
    """Filtro client-side de tribunal: sigla exata ou família com sufixo
    numérico (trib="TRT" casa "TRT-3"; trib="TRT-3" casa só "TRT-3")."""
    s = (sigla_registro or "").upper()
    return s == trib or s.startswith(trib + "-")


def _cql(consulta: str, tribunal: str | None) -> str:
    """Monta a consulta CQL: termos do usuário ENTRE ASPAS + refinamento por URN.

    Sem as aspas, consulta multi-palavra vira CQL inválida ("dano moral and
    urn any ..." — "moral" seria interpretado como operador/índice) e a busca
    degrada silenciosamente para 0 resultados.
    """
    # Aspas internas removidas — não podem quebrar a sintaxe do termo quotado.
    termos = re.sub(r'["()]', " ", consulta or "").strip()
    partes = [f'"{termos}"'] if termos else []
    trib = (tribunal or "").strip().upper()
    if trib in _URN_TRIBUNAL:
        partes.append(f'urn any "{_URN_TRIBUNAL[trib]}"')
    return " and ".join(partes)


def _local(tag: str) -> str:
    """Nome local do elemento (ignora namespace — parse tolerante)."""
    return tag.rsplit("}", 1)[-1]


def _registros(xml_text: str) -> list[dict]:
    """Extrai cada srw:record como dict {nome-local: texto}."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        logger.warning("LexML SRU: XML inválido na resposta")
        return []
    # `diagnostics` na raiz = erro de consulta (contrato SRU) → lista vazia.
    if any(_local(el.tag) == "diagnostics" for el in root.iter()):
        logger.warning("LexML SRU: resposta com diagnostics (CQL rejeitada?)")
        return []
    registros: list[dict] = []
    for rec in (el for el in root.iter() if _local(el.tag) == "record"):
        campos: dict[str, str] = {}
        for el in rec.iter():
            nome = _local(el.tag)
            if el.text and el.text.strip() and nome not in campos:
                campos[nome] = el.text.strip()
        if campos:
            registros.append(campos)
    return registros


def _e_jurisprudencia(campos: dict) -> bool:
    facet = texto_normalizado(campos.get("facet-tipoDocumento", ""))
    tipo = texto_normalizado(campos.get("tipoDocumento", ""))
    return facet.startswith("jurisprud") or tipo in (
        "acordao", "sumula", "sumula vinculante", "decisao monocratica",
        "orientacao jurisprudencial",
    )


def _tribunal_do_registro(campos: dict) -> str:
    urn = campos.get("urn", "")
    for frag, sigla in _SIGLA_POR_FRAGMENTO.items():
        if frag in urn:
            return sigla
    # Fragmentos compostos sobre URN + autoridade textual, normalizadas
    # (client-side — cobre TJMG, TRT-n e Turmas Recursais/Juizados → JEC).
    alvo = re.sub(r"[^a-z0-9]+", " ", texto_normalizado(
        f"{urn} {campos.get('autoridade') or ''}"))
    sigla = _sigla_composta(alvo)
    if sigla:
        return sigla
    # fallback: autoridade textual do registro (ex.: "Tribunal de Justiça...").
    return (campos.get("autoridade") or "LexML")[:20]


def _numero_do_registro(campos: dict) -> str:
    urn = campos.get("urn", "")
    # URN lex termina com ";<numero>" (ex.: ...;resp:2010-11-23;1186789).
    m = re.search(r";([\w.\-]+)$", urn)
    if m:
        return m.group(1)[:80]
    titulo = campos.get("title", "")
    m = re.search(r"\d[\d./\-]{3,}", titulo)
    return (m.group(0) if m else urn or titulo)[:80]


def normalizar_registro(campos: dict) -> JulgadoNormalizado | None:
    """Registro SRU/DC → JulgadoNormalizado (None se não for jurisprudência)."""
    if not _e_jurisprudencia(campos):
        return None
    ementa = campos.get("description") or ""
    titulo = campos.get("title") or ""
    if len(ementa) < 50:                      # sem ementa não há valor citável
        return None
    urn = campos.get("urn", "")
    url = campos.get("identifier") or (
        f"https://www.lexml.gov.br/urn/{urn}" if urn else "")
    if not url:
        return None
    data = (campos.get("date") or "")[:10] or None
    return JulgadoNormalizado(
        tribunal=_tribunal_do_registro(campos),
        numero=_numero_do_registro(campos),
        data=data,
        ementa=f"{titulo}\n\n{ementa}".strip()[:20000],
        url_fonte=url,
        orgao_julgador=None,
        classe=campos.get("tipoDocumento"),
    )


async def buscar(
    consulta: str, tribunal: str | None = None, limite: int = 20,
    ano: int | None = None,
) -> list[JulgadoNormalizado]:
    """Busca jurisprudência no LexML via SRU. Paginação limitada; sem rede
    disponível/erro de fonte → exceção do fetch propaga (o runner registra).

    `tribunal`: para STF/STJ/TST a CQL é refinada server-side pela URN
    (_URN_TRIBUNAL); para os DEMAIS (TJMG, TRT, TRT-3, JEC, ...) a consulta
    vai SEM refinamento e o filtro é 100% client-side sobre a sigla inferida
    da URN/autoridade — correto, porém menos eficiente: páginas com registros
    de outros tribunais consomem o teto MAX_PAGINAS sem render resultados.

    `ano`: filtro CLIENT-SIDE pela data do julgado (no_ano) — registro sem
    data comprovada NÃO entra quando o ano é exigido. Mesma observação de
    eficiência: o SRU não é refinado por data aqui (não inventamos sintaxe
    server-side não testável); varremos até MAX_PAGINAS e filtramos local."""
    cql = _cql(consulta, tribunal)
    if not cql:
        return []
    trib = (tribunal or "").strip().upper()
    resultados: list[JulgadoNormalizado] = []
    vistos: set[str] = set()
    start = 1
    for _ in range(MAX_PAGINAS):
        r = await fetch(SRU_URL, params={
            "operation": "searchRetrieve",
            "version": "1.1",
            "query": cql,
            "startRecord": start,
            "maximumRecords": PAGINA_TAMANHO,
        }, headers={"Accept": "application/xml"}, timeout=30.0)
        registros = _registros(r.text)
        if not registros:
            break
        for campos in registros:
            j = normalizar_registro(campos)
            if j is None:
                continue
            if trib and not _casa_tribunal(j.tribunal, trib):
                continue                     # filtro client-side de tribunal
            if not no_ano(j.data, ano):
                continue                     # filtro client-side de ano
            chave = j.chave_dedup()
            if chave in vistos:
                continue
            vistos.add(chave)
            resultados.append(j)
            if len(resultados) >= limite:
                return resultados
        if len(registros) < PAGINA_TAMANHO:
            break
        start += PAGINA_TAMANHO
    return resultados
