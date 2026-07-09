from __future__ import annotations

import re
import unicodedata


_REPLACEMENTS = {
    "\ufeff": "",
    "\u200b": "",
    "\u200c": "",
    "\u200d": "",
    "\ufe0f": "",
    "\u00a0": " ",
    "\u2013": "-",
    "\u2014": "-",
    "\u2015": "-",
    "\u2212": "-",
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2022": "-",
    "\u00b7": "-",
    "\u2192": "->",
    "\u00ba": "o",
    "\u00aa": "a",
    "\u00a7": "paragrafo",
}


_MOJIBAKE = {
    "Ã¡": "a", "Ã ": "a", "Ã¢": "a", "Ã£": "a", "Ã©": "e", "Ãª": "e",
    "Ã­": "i", "Ã³": "o", "Ã´": "o", "Ãµ": "o", "Ãº": "u", "Ã§": "c",
    "Ã": "A", "Ã€": "A", "Ã‚": "A", "Ãƒ": "A", "Ã‰": "E", "ÃŠ": "E",
    "Ã": "I", "Ã“": "O", "Ã”": "O", "Ã•": "O", "Ãš": "U", "Ã‡": "C",
    "NÂº": "No", "nÂº": "no", "Âº": "o", "Âª": "a", "Â§": "paragrafo", "Â·": "-",
    "â€”": "-", "â€“": "-", "â†’": "->", "â€¢": "-", "âš ï¸": "ATENCAO:",
}


def sem_caracteres_problematicos(texto: str | None) -> str:
    """Remove simbolos instaveis para PDF/DOCX mantendo texto juridico legivel.

    A saida fica em ASCII para evitar mojibake em ambientes de VPS, PDF, DOCX,
    downloads e impressao. Nao altera dados juridicos, apenas a apresentacao.
    """
    if not texto:
        return ""

    saida = str(texto)
    for antigo, novo in _MOJIBAKE.items():
        saida = saida.replace(antigo, novo)
    for antigo, novo in _REPLACEMENTS.items():
        saida = saida.replace(antigo, novo)

    saida = "".join(ch for ch in saida if ch == "\n" or ch == "\t" or unicodedata.category(ch)[0] != "C")
    saida = unicodedata.normalize("NFKD", saida)
    saida = "".join(ch for ch in saida if not unicodedata.combining(ch))
    saida = saida.encode("ascii", "ignore").decode("ascii")
    saida = re.sub(r"[^\S\n]+", " ", saida)
    saida = re.sub(r"\n{3,}", "\n\n", saida)
    return saida.strip()


def padronizar_documento_juridico(conteudo: str | None) -> str:
    texto = sem_caracteres_problematicos(conteudo)
    if not texto:
        return ""

    texto = texto.replace("**", "")
    texto = re.sub(r"^>\s*", "", texto, flags=re.MULTILINE)
    texto = re.sub(r"^#{1,6}\s*", "", texto, flags=re.MULTILINE)
    texto = texto.replace("[ ]", "( )")
    texto = texto.replace("[x]", "(x)").replace("[X]", "(x)")

    linhas = [linha.rstrip() for linha in texto.splitlines()]
    return "\n".join(linhas).strip()


def aviso_rascunho_ia() -> str:
    return (
        "Documento gerado em padrao juridico-profissional. "
        "Conferir fatos, documentos, valores, prazos, pedidos, citacoes e estrategia antes do uso externo."
    )


def aviso_minuta_automatica() -> str:
    return (
        "Documento gerado automaticamente em padrao juridico-profissional. "
        "Conferir campos entre colchetes, fatos, documentos, valores, prazos e citacoes antes do uso externo."
    )
