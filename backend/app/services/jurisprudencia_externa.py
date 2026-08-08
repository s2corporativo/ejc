"""
jurisprudencia_externa.py — Busca em fontes públicas externas.

Fontes suportadas:
  • LexML.gov.br  — legislação e jurisprudência federal (API pública XML/JSON)
  • TJMG          — jurisprudência estadual MG (busca por palavras)
  • DataJud/CNJ   — (placeholder p/ expansão futura)

Retorno padronizado: lista de JuriExternaItem compatível com JurisprudenciaInterna.
"""
from __future__ import annotations

import asyncio
import html as _html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger("ejc.juri_ext")

TIMEOUT = httpx.Timeout(20.0, connect=8.0)
HEADERS = {
    "User-Agent": "EJC-LegalAI/2.0 (ejc.depaulateixeira.adv.br; contato: adm@vetmg.com.br)",
    "Accept": "application/xml,text/html,application/json;q=0.9,*/*;q=0.8",
}


# ── Schemas de resultado ────────────────────────────────────────────────────

def _item(
    titulo: str,
    ementa: str,
    tribunal: str = "",
    relator: str = "",
    numero_acordao: str = "",
    data_julgamento: Optional[str] = None,
    fonte: str = "",
    link: str = "",
    area_juridica: str = "",
    orgao_julgador: str = "",
    classe: str = "",
) -> dict:
    return {
        "titulo": titulo[:300],
        "ementa": ementa[:2000],
        "tribunal": tribunal,
        "relator": relator,
        "numero_acordao": numero_acordao,
        "data_julgamento": data_julgamento,
        "fonte": fonte,
        "link_original": link,
        "area_juridica": area_juridica,
        # Metadados jurídicos adicionais (usados pelo ingestor RAG do TJMG;
        # os consumidores de busca ao vivo simplesmente ignoram chaves extras).
        "orgao_julgador": orgao_julgador,
        "classe": classe,
    }


# ── LexML ───────────────────────────────────────────────────────────────────

LEXML_SEARCH = "https://www.lexml.gov.br/busca/pesquisa"
LEXML_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "lexml": "http://www.lexml.gov.br/oai/lexml",
}


async def buscar_lexml(
    palavras: str,
    tipo: str = "jurisprudencia",
    pagina: int = 1,
    por_pagina: int = 10,
) -> list[dict]:
    """
    Pesquisa na API pública XML do LexML.gov.br.
    tipo: 'jurisprudencia' | 'legislacao' | 'doutrina'
    """
    params = {
        "palavras": palavras,
        "tipo": tipo,
        "pagina": pagina,
        "tamanhoDaPagina": por_pagina,
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as cli:
            r = await cli.get(LEXML_SEARCH, params=params)
            r.raise_for_status()
    except Exception as exc:
        logger.warning("LexML indisponível: %s", exc)
        return []

    try:
        root = ET.fromstring(r.text)
    except ET.ParseError:
        logger.warning("LexML: XML inválido na resposta")
        return []

    resultados = []
    # Atom feed: <entry> com <title>, <summary>, <link>, <author>
    for entry in root.findall(".//atom:entry", LEXML_NS) or root.findall(".//entry"):
        titulo = _xml_text(entry, ["atom:title", "title"]) or "Sem título"
        ementa = _xml_text(entry, ["atom:summary", "summary", "atom:content", "content"]) or ""
        link    = _xml_attr(entry, ["atom:link", "link"], "href")
        autor   = _xml_text(entry, ["atom:author/atom:name", "author/name"]) or ""
        pub     = _xml_text(entry, ["atom:published", "published", "atom:updated", "updated"]) or ""
        # número do acórdão geralmente está no id ou titulo
        num_ac  = _xml_text(entry, ["atom:id", "id"]) or ""
        num_ac  = re.sub(r"^urn:lex:br:", "", num_ac)[:80]

        data = pub[:10] if pub else None

        resultados.append(_item(
            titulo=titulo,
            ementa=ementa,
            tribunal=_inferir_tribunal(link + titulo),
            relator=autor,
            numero_acordao=num_ac,
            data_julgamento=data,
            fonte="LexML",
            link=link,
            area_juridica=_inferir_area(titulo + " " + ementa),
        ))

    return resultados


def _xml_text(el: ET.Element, paths: list[str]) -> str:
    for p in paths:
        # Tenta com namespace e sem
        found = el.find(p, LEXML_NS)
        if found is None:
            # caminho sem namespace
            tag = p.split("/")[-1].split(":")[-1]
            found = el.find(f".//{tag}")
        if found is not None and found.text:
            return found.text.strip()
    return ""


def _xml_attr(el: ET.Element, paths: list[str], attr: str) -> str:
    for p in paths:
        found = el.find(p, LEXML_NS)
        if found is None:
            tag = p.split("/")[-1].split(":")[-1]
            found = el.find(f".//{tag}")
        if found is not None:
            val = found.get(attr, "")
            if val:
                return val
    return ""


# ── TJMG ─────────────────────────────────────────────────────────────────────

TJMG_BASE   = "https://www5.tjmg.jus.br"
TJMG_SEARCH = f"{TJMG_BASE}/jurisprudencia/pesquisaPalavrasEspelhoAcordao.do"


async def buscar_tjmg(
    palavras: str,
    pagina: int = 1,
    por_pagina: int = 10,
    *,
    data_inicial: str = "",
    data_final: str = "",
    classe: str = "",
    orgao: str = "",
    metricas: dict | None = None,
) -> list[dict]:
    """
    Busca na jurisprudência pública do TJMG via formulário web.
    Retorna lista de acórdãos parseados do HTML de resultados.

    Filtros opcionais (usados pelo ingestor RAG agendado; a busca ao vivo do
    usuário chama sem eles): `data_inicial`/`data_final` (dd/mm/aaaa),
    `classe` (ex.: para mirar IRDR/IAC) e `orgao` (código do órgão julgador).

    `metricas` (opcional, preenchido in-place — a lista de retorno não muda de
    shape para os demais chamadores): {"rede_falhou": bool, "html_bytes": int,
    "blocos": int}. É o que permite ao ingestor agendado distinguir "a rede
    caiu", "o HTML veio mas nenhum bloco casou o padrão (layout mudou)" e
    "veio e parseou" — três zeros diferentes que antes eram indistinguíveis.
    """
    # TJMG espera POST com params de formulário
    payload = {
        "buscaLivre": palavras,
        "pesquisar": "Pesquisar",
        "numeroProcesso": "",
        "numeroRegistro": "",
        "palavras": palavras,
        "codigoOrgaoJulgador": orgao or "",
        "codigoCompostoRelator": "",
        "classe": classe or "",
        "dataJulgamentoInicial": data_inicial or "",
        "dataJulgamentoFinal": data_final or "",
        "siglaLegislativa": "",
        "referenciaLegislativa": "",
        "indexPagina": str(pagina - 1),
        "tamanhoPagina": str(por_pagina),
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, headers={**HEADERS, "Referer": TJMG_BASE + "/jurisprudencia/"}, follow_redirects=True) as cli:
            r = await cli.post(TJMG_SEARCH, data=payload)
            r.raise_for_status()
    except Exception as exc:
        logger.warning("TJMG indisponível: %s", exc)
        if metricas is not None:
            metricas.update(rede_falhou=True, html_bytes=0, blocos=0)
        return []

    if metricas is not None:
        metricas["rede_falhou"] = False
    return _parse_tjmg_html(r.text, metricas)


def _parse_tjmg_html(html: str, metricas: dict | None = None) -> list[dict]:
    """Parse tolerante do HTML de resultados do TJMG.

    Baseado em regex (não há bs4/lxml nas dependências) e deliberadamente
    defensivo: campos ausentes viram string vazia e blocos sem ementa mínima
    são descartados — NUNCA levanta exceção. Se o HTML do TJMG mudar, o
    resultado degrada para lista vazia (e o job de ingestão marca a fonte como
    'parcial'/'erro' no painel, sem quebrar o scheduler).

    `metricas` (opcional, preenchido in-place): {"html_bytes": tamanho do HTML
    recebido, "blocos": quantos blocos brutos o split por classe CSS casou}.
    Instrumenta a camada onde a mudança de layout mata a coleta: html_bytes > 0
    com blocos == 0 significa "a página veio e o padrão não casou" — sinal de
    layout novo, invisível quando o retorno era só a lista vazia.
    """
    resultados = []
    tamanho_html = len(html or "")

    # Teto defensivo de tamanho: bound o custo do parse regex sobre HTML de
    # terceiros (uma resposta anômala não vira gasto de CPU desproporcional).
    # Páginas de resultado do TJMG são muito menores que isto.
    html = html[:2_000_000]

    # Decodifica entidades ANTES da extração de campos: os rótulos ("Acórdão",
    # "Órgão Julgador", "Ementa"...) casam mesmo que o TJMG os sirva
    # entity-encoded (&oacute; etc.). As tags (<tr>, <br>, </td>) permanecem
    # intactas — unescape não reintroduz marcação — então o split por classe e
    # os stops de campo por tag continuam válidos.
    html = _html.unescape(html)

    # Blocos de acórdão estão em divs com class="resultados" ou tabelas
    # Extração via regex dos campos principais
    # Padrão TJMG: Número | Relator | Órgão | Classe | Data | Ementa
    blocos = re.split(r'(?i)<(?:tr|div)[^>]*class="[^"]*(?:resultad|accordao|acordao|linha)[^"]*"', html)

    if metricas is not None:
        metricas["html_bytes"] = tamanho_html
        metricas["blocos"] = max(len(blocos) - 1, 0)

    for bloco in blocos[1:]:
        # Número do acórdão
        num = re.search(r'Acórdão[:\s]*(\d[\d\./\-]+)', bloco, re.I)
        if not num:
            num = re.search(r'(?:N[ºo°]?\s*d[oe]\s*)?Processo[:\s]*([\d\.\-\/]+)', bloco, re.I)
        numero = num.group(1).strip() if num else ""

        # Relator
        rel = re.search(r'Relator[^:]*[:\s]*([A-ZÀ-Ü][A-Za-zÀ-ü \.]+?)(?:<|,|\n|&)', bloco, re.I)
        relator = _limpar_html(rel.group(1)) if rel else ""

        # Órgão julgador — exige o rótulo; sem ele, aceita apenas uma designação
        # NUMERADA de câmara/turma (ex.: "5ª Câmara Cível"). Não casa "Câmara"
        # solta no meio da ementa (evita gravar metadado errado no `extra`).
        org = re.search(r'Órg[ãa]o\s*Julgador[^:]*[:\s]*([^<\n]+?)(?:<|\n)', bloco, re.I)
        if not org:
            org = re.search(r'(\d{1,2}[ªº]\s*(?:C[âa]mara|Turma)[^<\n]{0,40})', bloco, re.I)
        orgao = _limpar_html(org.group(1)) if org else ""

        # Classe processual (permite identificar IRDR/IAC etc.)
        cls = re.search(r'Classe[^:]*[:\s]*([^<\n]+?)(?:<|\n)', bloco, re.I)
        classe = _limpar_html(cls.group(1)) if cls else ""

        # Data de julgamento
        data = re.search(r'(?:Data[^:]*|Julgamento)[:\s]*[^\d]*(\d{2}/\d{2}/\d{4})', bloco, re.I)
        data_str = None
        if data:
            try:
                data_str = datetime.strptime(data.group(1), "%d/%m/%Y").date().isoformat()
            except ValueError:
                pass

        # Ementa — texto limpo. NÃO usar "Súmula" como parada: ementas citam
        # súmulas inline com frequência ("aplica-se a Súmula 83 do STJ") e isso
        # truncaria o conteúdo citável central do RAG.
        ementa_raw = re.search(r'(?:Ementa|EMENTA)[:\s]*(.*?)(?:Relator|RELATOR|<hr|</div|</td)', bloco, re.S | re.I)
        ementa = _limpar_html(ementa_raw.group(1)) if ementa_raw else _limpar_html(bloco[:800])

        if len(ementa) < 30:
            continue

        titulo = f"Acórdão TJMG {numero}" if numero else f"TJMG — {ementa[:80]}..."

        resultados.append(_item(
            titulo=titulo,
            ementa=ementa,
            tribunal="TJMG",
            relator=relator,
            numero_acordao=numero,
            data_julgamento=data_str,
            fonte="TJMG",
            link=f"{TJMG_BASE}/jurisprudencia/formEspelhoAcordao.do?numeroRegistro={numero}" if numero else "",
            area_juridica=_inferir_area(ementa),
            orgao_julgador=orgao,
            classe=classe,
        ))

    # Teto defensivo de memória: o chamador controla o volume real via
    # `tamanhoPagina` (TJMG_INGEST_MAX_POR_TEMA). 500 fica bem acima do volume
    # realista por página; acima disso, elevar este teto junto.
    return resultados[:500]


def _limpar_html(s: str) -> str:
    s = re.sub(r'<[^>]+>', ' ', s)
    s = _html.unescape(s)          # &amp; &ccedil; &#233; → caracteres reais
    s = re.sub(r'\s+', ' ', s)
    return s.strip()


# ── Helpers ──────────────────────────────────────────────────────────────────

# Mapa de siglas → nome canônico. Cobre as jurisdições-alvo do escritório
# (Betim/MG): TJMG estadual, TRT-3 trabalhista, TRF-1/TRF-6 federal, superiores
# (STJ/STF/TST/TSE/STM) e os 24 TRTs / 6 TRFs (federação LexML pode retornar
# julgados de qualquer região). Cada TRT/TRF entra em duas grafias — "trt3" e
# "trt-3" — porque a inferência é textual sobre link+título do registro.
_TRIBUNAL_MAP: dict[str, str] = {
    "tjmg": "TJMG", "tjsp": "TJSP",
    "stj": "STJ", "stf": "STF", "tst": "TST", "tse": "TSE", "stm": "STM",
}
for _n in range(1, 25):                    # Tribunais Regionais do Trabalho (1..24)
    _TRIBUNAL_MAP[f"trt{_n}"] = f"TRT-{_n}"
    _TRIBUNAL_MAP[f"trt-{_n}"] = f"TRT-{_n}"
for _n in range(1, 7):                      # Tribunais Regionais Federais (1..6)
    _TRIBUNAL_MAP[f"trf{_n}"] = f"TRF-{_n}"
    _TRIBUNAL_MAP[f"trf-{_n}"] = f"TRF-{_n}"
_TRIBUNAL_MAP["trt"] = "TRT"                # fallback só p/ sigla isolada (regex boundary)
_TRIBUNAL_MAP["trf"] = "TRF"


def _inferir_tribunal(texto: str) -> str:
    """Infere o tribunal a partir de texto livre (link/título).

    Casamento por FRONTEIRA (não substring simples): a sigla não pode ser
    precedida por letra/dígito nem seguida de dígito. Isso evita que "trt1"
    case dentro de "trt10"/"trt-15" (o número seguinte quebra a fronteira) e que
    o fallback genérico "trt" engula "trt3" (após "trt" vem um dígito). Assim a
    ordem do dict deixa de importar para a desambiguação numérica.
    """
    t = texto.lower()
    for k, v in _TRIBUNAL_MAP.items():
        if re.search(rf"(?<![a-z0-9]){re.escape(k)}(?![0-9])", t):
            return v
    return "TJMG"  # default para buscas locais


_AREA_MAP = [
    (["trabalhista", "clt", "rescisão", "horas extras", "jst", "trt",
      "verbas rescisórias", "vínculo empregatício", "justa causa"], "Trabalhista"),
    (["consumidor", "cdc", "fornecedor", "negativação", "serasa", "spc"], "Consumidor"),
    (["penal", "crime", "réu", "absolvição", "condenação", "habeas corpus"], "Penal"),
    (["família", "alimentos", "guarda", "divórcio", "partilha"], "Família"),
    (["previdenciário", "inss", "benefício", "aposentadoria", "bpc",
      "auxílio-doença", "loas"], "Previdenciário"),
    (["tributário", "icms", "iss", "irpf", "auto de infração", "fisco",
      "execução fiscal"], "Tributário"),
    (["ambiental", "ibama", "licença", "app", "car", "poluição"], "Ambiental"),
    (["imobiliário", "locação", "usucapião", "matrícula", "financiamento"], "Imobiliário"),
    (["bancário", "juros", "revisional", "cet", "anatocismo"], "Bancário"),
    (["empresarial", "societário", "recuperação judicial", "falência"], "Empresarial"),
    (["administrativo", "improbidade", "contrato público", "servidor",
      "licitação", "concurso público"], "Administrativo"),
    (["trânsito", "multa", "cnh", "cetran", "jari"], "Trânsito"),
    (["saúde", "plano de saúde", "ans", "médico", "hospital"], "Saúde"),
    (["digital", "lgpd", "dados pessoais", "privacidade"], "Digital/LGPD"),
    (["civil", "dano moral", "responsabilidade", "contrato", "indenização"], "Cível"),
]

def _inferir_area(texto: str) -> str:
    t = texto.lower()
    for termos, area in _AREA_MAP:
        if any(p in t for p in termos):
            return area
    return ""


# ── Busca unificada ───────────────────────────────────────────────────────────

async def buscar_todas_fontes(
    palavras: str,
    fontes: list[str] | None = None,
    pagina: int = 1,
    por_pagina: int = 10,
) -> dict:
    """
    Busca em paralelo nas fontes selecionadas.
    fontes: ['lexml', 'tjmg'] (padrão: ambas)
    """
    fontes = fontes or ["lexml", "tjmg"]

    # Coroutine-vazia real: asyncio.coroutine foi REMOVIDO no Python 3.11 e
    # levantava AttributeError, quebrando a busca sempre que uma fonte era
    # desabilitada (o gather recebia a exceção da própria construção da task).
    async def _vazio() -> list:
        return []

    tasks = []
    if "lexml" in fontes:
        tasks.append(buscar_lexml(palavras, pagina=pagina, por_pagina=por_pagina))
    else:
        tasks.append(_vazio())

    if "tjmg" in fontes:
        tasks.append(buscar_tjmg(palavras, pagina=pagina, por_pagina=por_pagina))
    else:
        tasks.append(_vazio())

    resultados = await asyncio.gather(*tasks, return_exceptions=True)

    lexml_res = resultados[0] if not isinstance(resultados[0], Exception) else []
    tjmg_res  = resultados[1] if not isinstance(resultados[1], Exception) else []

    return {
        "palavras": palavras,
        "total": len(lexml_res) + len(tjmg_res),
        "fontes": {
            "lexml": {"total": len(lexml_res), "itens": lexml_res},
            "tjmg":  {"total": len(tjmg_res),  "itens": tjmg_res},
        },
        "todos": lexml_res + tjmg_res,
    }
