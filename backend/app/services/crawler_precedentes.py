"""
Crawler de Precedentes — EJC v3.0
Busca REAL de jurisprudência na pesquisa pública do STJ (SCON).

Honestidade operacional: toda resposta indica a fonte consultada e a URL.
Falha de rede/HTTP/parsing NUNCA vira "success" vazio — retorna status "erro"
com a mensagem real, para o chamador decidir o que fazer (HITL).
"""
import html as _html
import logging
import re
from urllib.parse import urlencode

import httpx

logger = logging.getLogger("crawler_precedentes")

SCON_URL = "https://scon.stj.jus.br/SCON/pesquisar.jsp"
_TIMEOUT = 20.0

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

        corpo = resp.text or ""

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
