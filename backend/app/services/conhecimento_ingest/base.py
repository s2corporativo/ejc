# ── app/services/conhecimento_ingest/base.py ─────────────────────────────────
# Utilitários compartilhados das fontes de ingestão contínua de conhecimento
# (ANPD, Normas RFB, ...). Parsing de HTML SEM dependência nova (regex tolerante,
# mesmo estilo de jurisprudencia_externa._parse_tjmg_html) — bs4/lxml NÃO estão
# em requirements.txt e a regra do projeto é não introduzir dependências.
#
# Princípio de tolerância: página fora do padrão NUNCA levanta — os parsers
# degradam para lista vazia/string vazia e o chamador loga warning e pula.
from __future__ import annotations

import html as _html
import re

# Reuso do normalizador canônico do repo (minúsculas + sem acento).
from app.services.juris_import.base import texto_normalizado

_RE_SCRIPT = re.compile(r"<(script|style|noscript)\b[^>]*>.*?</\1>", re.S | re.I)
_RE_TAG = re.compile(r"<[^>]+>")
_RE_ANCORA = re.compile(r'<a\b[^>]*?href\s*=\s*"([^"]+)"[^>]*>(.*?)</a>', re.S | re.I)
_RE_QUEBRA = re.compile(r"(?i)</(?:p|div|li|tr|h[1-6]|section|table|ul|ol)>|<br\s*/?>")


def limpar_html(fragmento: str) -> str:
    """Fragmento HTML → texto plano de uma linha (tags fora, entidades resolvidas)."""
    if not fragmento:
        return ""
    frag = _RE_SCRIPT.sub(" ", fragmento)
    txt = _RE_TAG.sub(" ", frag)
    txt = _html.unescape(txt)
    return re.sub(r"\s+", " ", txt).strip()


def extrair_ancoras(html_bruto: str) -> list[tuple[str, str]]:
    """Todas as âncoras da página → [(href, texto_limpo)]. Nunca levanta."""
    if not html_bruto:
        return []
    return [(href.strip(), limpar_html(rotulo))
            for href, rotulo in _RE_ANCORA.findall(html_bruto)]


def html_para_texto(html_bruto: str) -> str:
    """Página HTML completa → texto plano preservando quebras de parágrafo.

    Heurística de recorte (gov.br é Plone): prefere o miolo `id="content-core"`
    (cortando no <footer>, se houver), senão <article>, senão <body>, senão a
    página inteira. Fora do padrão → ainda extrai o texto bruto (tolerante).
    """
    if not html_bruto:
        return ""
    corpo = html_bruto
    m = re.search(r'<(?:div|section)\b[^>]*\bid="content-core"[^>]*>(.*)',
                  corpo, re.S | re.I)
    if m:
        corpo = m.group(1)
        corte = re.search(r'<footer\b|\bid="doc-footer"|\bid="rodape"', corpo, re.I)
        if corte:
            corpo = corpo[:corte.start()]
    else:
        m = re.search(r"<article\b[^>]*>(.*?)</article>", corpo, re.S | re.I)
        if m:
            corpo = m.group(1)
        else:
            m = re.search(r"<body\b[^>]*>(.*?)</body>", corpo, re.S | re.I)
            if m:
                corpo = m.group(1)
    corpo = _RE_SCRIPT.sub(" ", corpo)
    corpo = _RE_QUEBRA.sub("\n", corpo)
    texto = _RE_TAG.sub(" ", corpo)
    texto = _html.unescape(texto)
    linhas = [re.sub(r"[ \t]+", " ", ln).strip() for ln in texto.split("\n")]
    return "\n".join(ln for ln in linhas if ln).strip()


def slugificar(texto: str, max_len: int = 120) -> str:
    """Texto → slug estável ascii (minúsculo, sem acento, hífens)."""
    s = texto_normalizado(texto or "")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:max_len]
