"""
Crawler de Precedentes — EJC v3.0
Busca REAL de jurisprudência em fontes públicas: STJ (SCON), STF (pesquisa de
jurisprudência) e localização de processos/andamentos via DataJud/CNJ.

Honestidade operacional: toda resposta indica a fonte consultada e a URL.
Falha de rede/HTTP/parsing NUNCA vira "success" vazio — retorna status "erro"
(falha real) ou "indisponivel" (fonte sem endpoint/credencial utilizável) com a
mensagem real, para o chamador decidir o que fazer (HITL). Nunca inventa
resultado.
"""
import html as _html
import json
import logging
import re
from urllib.parse import urlencode

import httpx

logger = logging.getLogger("crawler_precedentes")

SCON_URL = "https://scon.stj.jus.br/SCON/pesquisar.jsp"
# Endpoint REST/JSON da pesquisa pública de jurisprudência do STF (backend
# Elasticsearch da página https://jurisprudencia.stf.jus.br/pages/search).
# URL FIXA por fonte (sem SSRF) — o termo vai no corpo JSON, encodado.
STF_SEARCH_URL = "https://jurisprudencia.stf.jus.br/api/search/search"
STF_SEARCH_PAGE = "https://jurisprudencia.stf.jus.br/pages/search"
_TIMEOUT = 20.0
_MAX_CORPO_BYTES = 2_000_000  # teto do corpo externo processado (~2 MB)

# Blocos de ementa/documento no HTML do SCON (best-effort — layout público).
_RE_DOC_BLOCO = re.compile(
    r'class="docTexto[^"]*"[^>]*>(.*?)</(?:div|p|span)>', re.S | re.I
)
_RE_TOTAL = re.compile(r'(\d+)\s*documento(?:s)?\s+encontrado', re.I)
_RE_NENHUM = re.compile(r"Nenhum documento encontrado", re.I)
_RE_TAGS = re.compile(r"<[^>]+>")


def _limpar_html(trecho: str) -> str:
    """Remove tags e normaliza espaços de um fragmento HTML."""
    texto = _RE_TAGS.sub(" ", trecho)
    texto = _html.unescape(texto)
    return re.sub(r"\s+", " ", texto).strip()


class CrawlerPrecedentes:
    def __init__(self):
        self.headers = {"User-Agent": "EJC-Jurimetria-Bot/3.0"}

    async def buscar_precedentes_magistrado(self, nome_magistrado: str, tema: str):
        """
        Busca decisões na pesquisa pública de jurisprudência do STJ (SCON)
        combinando magistrado e tema como termos livres.

        Retorna:
          {"status": "success", "total_encontrado": int, "precedentes": [...],
           "fonte": "STJ/SCON", "url": <url consultada>}
        ou, em falha real (rede/HTTP/parsing indeterminado):
          {"status": "erro", "mensagem": <motivo>, "fonte": "STJ/SCON",
           "total_encontrado": 0, "precedentes": []}
        """
        termos = " E ".join(
            f'"{t.strip()}"' for t in (nome_magistrado, tema) if t and t.strip()
        )
        if not termos:
            return {
                "status": "erro",
                "mensagem": "Informe magistrado e/ou tema para a busca.",
                "fonte": "STJ/SCON",
                "total_encontrado": 0,
                "precedentes": [],
            }
        params = {"livre": termos, "b": "ACOR"}
        url = f"{SCON_URL}?{urlencode(params)}"

        try:
            async with httpx.AsyncClient(
                timeout=_TIMEOUT, headers=self.headers, follow_redirects=True
            ) as client:
                logger.info(
                    f"Buscando precedentes no STJ/SCON: magistrado={nome_magistrado!r} tema={tema!r}"
                )
                resp = await client.get(SCON_URL, params=params)
                resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(f"STJ/SCON respondeu HTTP {e.response.status_code}: {e}")
            return {
                "status": "erro",
                "mensagem": f"STJ/SCON respondeu HTTP {e.response.status_code}.",
                "fonte": "STJ/SCON",
                "url": url,
                "total_encontrado": 0,
                "precedentes": [],
            }
        except httpx.HTTPError as e:
            logger.error(f"Erro de rede ao consultar STJ/SCON: {e}")
            return {
                "status": "erro",
                "mensagem": f"Falha de rede ao consultar o STJ/SCON: {e}",
                "fonte": "STJ/SCON",
                "url": url,
                "total_encontrado": 0,
                "precedentes": [],
            }

        # Limita o corpo processado (HTML externo não confiável): 2 MB bastam
        # para a página de resultados; evita consumo de memória com respostas
        # anômalas/maliciosas.
        corpo = (resp.text or "")[:_MAX_CORPO_BYTES]

        # Sem resultados — resposta legítima do tribunal, não um mock.
        if _RE_NENHUM.search(corpo):
            return {
                "status": "success",
                "total_encontrado": 0,
                "precedentes": [],
                "fonte": "STJ/SCON",
                "url": url,
            }

        blocos = [_limpar_html(b) for b in _RE_DOC_BLOCO.findall(corpo)]
        blocos = [b for b in blocos if len(b) >= 40]
        m_total = _RE_TOTAL.search(corpo)
        total = int(m_total.group(1)) if m_total else len(blocos)

        if not blocos and not m_total:
            # HTTP 200 mas layout irreconhecível: não inventar zero resultados.
            logger.warning("STJ/SCON: resposta recebida mas não interpretável.")
            return {
                "status": "erro",
                "mensagem": (
                    "Resposta do STJ/SCON recebida, mas não foi possível "
                    "interpretar os resultados (layout da página mudou?). "
                    "Consulte manualmente a URL informada."
                ),
                "fonte": "STJ/SCON",
                "url": url,
                "total_encontrado": 0,
                "precedentes": [],
            }

        precedentes = [
            {"ementa": b[:1500], "tribunal": "STJ", "fonte": "STJ/SCON"}
            for b in blocos[:20]
        ]
        return {
            "status": "success",
            "total_encontrado": total,
            "precedentes": precedentes,
            "fonte": "STJ/SCON",
            "url": url,
        }


crawler = CrawlerPrecedentes()


# ── STJ (wrapper genérico por termo, reusa o crawler existente) ──────────────
async def buscar_precedentes_stj(termo: str) -> dict:
    """Busca por termo livre no STJ/SCON, reusando a lógica já validada.

    Mantém o contrato padrão (status/fonte/total_encontrado/precedentes).
    """
    return await crawler.buscar_precedentes_magistrado("", termo)


# ── STF (pesquisa pública de jurisprudência — endpoint REST/JSON) ────────────
# Campos onde o texto da ementa costuma aparecer no _source do STF (best-effort;
# a API é pública e o schema pode variar, por isso tentamos vários nomes).
_STF_CAMPOS_EMENTA = (
    "ementa", "inteiro_teor", "inteiroTeor", "dispositivo", "titulo",
    "indexacao", "decisao",
)


def _stf_texto_do_source(src: dict) -> str:
    """Extrai o melhor texto disponível de um hit do STF (best-effort)."""
    for campo in _STF_CAMPOS_EMENTA:
        val = src.get(campo)
        if isinstance(val, str) and len(val.strip()) >= 40:
            return _limpar_html(val)
    # Fallback: concatena strings curtas relevantes, se nada melhor houver.
    partes = [
        _limpar_html(v)
        for v in src.values()
        if isinstance(v, str) and v.strip()
    ]
    return max(partes, key=len) if partes else ""


async def buscar_precedentes_stf(termo: str) -> dict:
    """Busca jurisprudência na pesquisa pública do STF (endpoint REST/JSON).

    Mesmo contrato do STJ. Requisição segura: URL fixa, termo encodado no corpo
    JSON, timeout, follow_redirects controlado e teto de bytes lidos. Falha de
    rede/HTTP → "erro"; corpo 200 ininterpretável → "erro" (nunca zero fake).
    """
    fonte = "STF"
    if not termo or not termo.strip():
        return {
            "status": "erro",
            "mensagem": "Informe um termo para a busca no STF.",
            "fonte": fonte,
            "total_encontrado": 0,
            "precedentes": [],
        }

    payload = {
        "query": {"query_string": {"query": termo.strip()}},
        "size": 20,
        "from": 0,
    }
    headers = {
        "User-Agent": "EJC-Jurimetria-Bot/3.0",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT, headers=headers, follow_redirects=True
        ) as client:
            logger.info(f"Buscando jurisprudência no STF: termo={termo!r}")
            resp = await client.post(STF_SEARCH_URL, json=payload)
            resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.error(f"STF respondeu HTTP {e.response.status_code}: {e}")
        return {
            "status": "erro",
            "mensagem": f"STF respondeu HTTP {e.response.status_code}.",
            "fonte": fonte,
            "url": STF_SEARCH_PAGE,
            "total_encontrado": 0,
            "precedentes": [],
        }
    except httpx.HTTPError as e:
        logger.error(f"Erro de rede ao consultar o STF: {e}")
        return {
            "status": "erro",
            "mensagem": f"Falha de rede ao consultar o STF: {e}",
            "fonte": fonte,
            "url": STF_SEARCH_PAGE,
            "total_encontrado": 0,
            "precedentes": [],
        }

    corpo = (resp.text or "")[:_MAX_CORPO_BYTES]
    # JSON precisa estar íntegro: se o teto de bytes truncou a resposta, não
    # tente interpretar — é falha honesta, não zero resultados.
    if len(resp.text or "") > _MAX_CORPO_BYTES:
        logger.warning("STF: resposta maior que o teto de bytes; não interpretada.")
        return {
            "status": "erro",
            "mensagem": "Resposta do STF excedeu o limite processável.",
            "fonte": fonte,
            "url": STF_SEARCH_PAGE,
            "total_encontrado": 0,
            "precedentes": [],
        }

    try:
        data = json.loads(corpo)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"STF: resposta 200 não é JSON interpretável: {e}")
        return {
            "status": "erro",
            "mensagem": (
                "Resposta do STF recebida, mas não foi possível interpretar "
                "os resultados (formato inesperado). Consulte manualmente."
            ),
            "fonte": fonte,
            "url": STF_SEARCH_PAGE,
            "total_encontrado": 0,
            "precedentes": [],
        }

    # Estrutura Elasticsearch-like: {"result": {"hits": {"total", "hits": [...]}}}
    container = data.get("result", data) if isinstance(data, dict) else {}
    hits_obj = container.get("hits", {}) if isinstance(container, dict) else {}
    hits = hits_obj.get("hits") if isinstance(hits_obj, dict) else None

    if hits is None:
        # 200 mas sem o envelope esperado: schema mudou — não inventar zero.
        logger.warning("STF: JSON sem envelope de resultados reconhecível.")
        return {
            "status": "erro",
            "mensagem": (
                "Resposta do STF recebida, mas o formato dos resultados não "
                "foi reconhecido (endpoint/schema mudou?)."
            ),
            "fonte": fonte,
            "url": STF_SEARCH_PAGE,
            "total_encontrado": 0,
            "precedentes": [],
        }

    total = hits_obj.get("total")
    if isinstance(total, dict):
        total = total.get("value")
    if not isinstance(total, int):
        total = len(hits)

    precedentes = []
    for h in hits:
        src = h.get("_source", {}) if isinstance(h, dict) else {}
        texto = _stf_texto_do_source(src) if isinstance(src, dict) else ""
        if len(texto) < 40:
            continue
        precedentes.append(
            {"ementa": texto[:1500], "tribunal": "STF", "fonte": fonte}
        )

    return {
        "status": "success",
        "total_encontrado": total,
        "precedentes": precedentes[:20],
        "fonte": fonte,
        "url": STF_SEARCH_PAGE,
    }


# ── DataJud/CNJ (localização de processo/andamentos — reusa datajud_service) ──
async def buscar_processos_datajud(numero_cnj: str) -> dict:
    """Localiza um processo e seus andamentos no DataJud/CNJ por número CNJ.

    O DataJud indexa movimentos/metadados de processos (não ementas); por isso
    esta função serve para LOCALIZAR o processo/andamentos, não jurisprudência.
    Reusa o client/padrão de ``datajud_service`` (sem duplicar HTTP).

    Contrato padrão. Distingue honestamente:
      - "indisponivel": integração desligada, sem credencial, ou tribunal não
        coberto pelo mapeamento do DataJud (não dá para confirmar nada);
      - "success" total 0: consulta feita e processo não localizado;
      - "success" total 1: processo localizado (precedentes = 1 processo).
    """
    fonte = "DataJud/CNJ"
    if not numero_cnj or not numero_cnj.strip():
        return {
            "status": "erro",
            "mensagem": "Informe o número CNJ do processo para a busca no DataJud.",
            "fonte": fonte,
            "total_encontrado": 0,
            "precedentes": [],
        }

    # Reuso de config + mapeamento de tribunal do datajud_service (sem duplicar).
    from app.services import datajud_service as dj

    if not dj.settings.DATAJUD_ENABLED or not dj.settings.DATAJUD_API_KEY:
        return {
            "status": "indisponivel",
            "mensagem": "Integração DataJud desabilitada ou sem credencial.",
            "fonte": fonte,
            "total_encontrado": 0,
            "precedentes": [],
        }
    if dj._alias_do_numero(numero_cnj) is None:
        return {
            "status": "indisponivel",
            "mensagem": "Tribunal do número CNJ não coberto pelo DataJud (mapeamento).",
            "fonte": fonte,
            "total_encontrado": 0,
            "precedentes": [],
        }

    try:
        info = await dj.consultar_processo(numero_cnj)
    except Exception as e:  # noqa: BLE001 — falha real vira "erro" honesto.
        logger.error(f"Erro ao consultar DataJud p/ {numero_cnj}: {e}")
        return {
            "status": "erro",
            "mensagem": f"Falha ao consultar o DataJud/CNJ: {e}",
            "fonte": fonte,
            "total_encontrado": 0,
            "precedentes": [],
        }

    if not info:
        return {
            "status": "success",
            "total_encontrado": 0,
            "precedentes": [],
            "fonte": fonte,
        }

    processo = {
        "numero_cnj": re.sub(r"\D", "", numero_cnj),
        "classe": info.get("classe"),
        "orgao": info.get("orgao"),
        "movimentos": info.get("movimentos", []),
        "tribunal": info.get("orgao"),
        "fonte": fonte,
    }
    return {
        "status": "success",
        "total_encontrado": 1,
        "precedentes": [processo],
        "fonte": fonte,
    }


# ── Agregador multi-fonte com deduplicação simples ───────────────────────────
_FONTES_VALIDAS = {"STJ", "STF", "DATAJUD"}


def _chave_dedup(prec: dict) -> str:
    """Chave de dedup best-effort: ementa normalizada ou número do processo."""
    ementa = prec.get("ementa")
    if isinstance(ementa, str) and ementa.strip():
        return re.sub(r"\s+", " ", ementa).strip().lower()[:200]
    num = prec.get("numero_cnj")
    if num:
        return "proc:" + re.sub(r"\D", "", str(num))
    bruto = json.dumps(prec, sort_keys=True, ensure_ascii=False)
    return re.sub(r"\s+", " ", bruto).strip().lower()[:200]


async def buscar_precedentes(
    termo: str = "",
    fontes: list[str] | None = None,
    numero_cnj: str | None = None,
) -> dict:
    """Consolida precedentes de múltiplas fontes (STJ + STF + DataJud).

    - ``fontes``: subconjunto de {"STJ", "STF", "DATAJUD"} (default: STJ+STF).
      Cada fonte é consultada isoladamente; a falha de uma não derruba as outras.
    - ``numero_cnj``: obrigatório para a fonte DATAJUD.
    - Cada precedente carrega o campo ``fonte``. Dedup simples por ementa
      normalizada / número de processo entre as fontes.

    Retorna:
      {"status": "success"|"erro", "total_encontrado": int,
       "precedentes": [...], "fontes": {<FONTE>: <resultado bruto>, ...}}
    - "success" se ao menos UMA fonte respondeu com sucesso; "erro" caso todas
      falhem/indisponíveis (nenhum resultado inventado).
    """
    fontes = [f.upper() for f in (fontes or ["STJ", "STF"])]
    fontes = [f for f in fontes if f in _FONTES_VALIDAS]
    if not fontes:
        return {
            "status": "erro",
            "mensagem": "Nenhuma fonte válida informada (use STJ, STF, DATAJUD).",
            "total_encontrado": 0,
            "precedentes": [],
            "fontes": {},
        }

    resultados: dict[str, dict] = {}
    for fonte in fontes:
        if fonte == "STJ":
            resultados[fonte] = await buscar_precedentes_stj(termo)
        elif fonte == "STF":
            resultados[fonte] = await buscar_precedentes_stf(termo)
        elif fonte == "DATAJUD":
            resultados[fonte] = await buscar_processos_datajud(numero_cnj or "")

    precedentes: list[dict] = []
    vistos: set[str] = set()
    houve_sucesso = False
    for res in resultados.values():
        if res.get("status") != "success":
            continue
        houve_sucesso = True
        for prec in res.get("precedentes", []):
            chave = _chave_dedup(prec)
            if chave in vistos:
                continue
            vistos.add(chave)
            precedentes.append(prec)

    return {
        "status": "success" if houve_sucesso else "erro",
        "total_encontrado": len(precedentes),
        "precedentes": precedentes,
        "fontes": resultados,
    }
