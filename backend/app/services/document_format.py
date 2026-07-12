from __future__ import annotations

import re
import unicodedata

# Normalizações SEGURAS de apresentação: removem apenas o que realmente causa
# mojibake/instabilidade (BOM, zero-width, NBSP, aspas curvas, travessões,
# marcadores), PRESERVANDO a acentuação do português ("Petição" continua
# "Petição"). A antiga dobra agressiva para ASCII mutilava texto jurídico
# pt-BR armazenado/exibido e foi removida — WeasyPrint (PDF) e python-docx
# (DOCX) suportam UTF-8 nativamente (fonte DejaVu Sans no template PDF).
_REPLACEMENTS = {
    "\ufeff": "",   # BOM
    "\u200b": "",   # zero-width space
    "\u200c": "",   # zero-width non-joiner
    "\u200d": "",   # zero-width joiner
    "\ufe0f": "",   # variation selector (emoji)
    "\u00a0": " ",  # NBSP
    "\u2013": "-",  # en dash
    "\u2014": "-",  # em dash
    "\u2015": "-",  # horizontal bar
    "\u2212": "-",  # minus sign
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2022": "-",  # bullet
    "\u00b7": "-",  # middle dot
    "\u2192": "->",
}


# Reparo de mojibake UTF-8 lido como Latin-1 ("Ã§" no lugar de "ç"): restaura
# o caractere CORRETO em vez de rebaixar para ASCII. Sequências mais longas
# primeiro (o dict preserva ordem de inserção) para não quebrar pares.
_MOJIBAKE = {
    # minúsculas acentuadas
    "\u00c3\u00a1": "á", "\u00c3\u00a0": "à", "\u00c3\u00a2": "â", "\u00c3\u00a3": "ã",
    "\u00c3\u00a9": "é", "\u00c3\u00aa": "ê", "\u00c3\u00ad": "í",
    "\u00c3\u00b3": "ó", "\u00c3\u00b4": "ô", "\u00c3\u00b5": "õ",
    "\u00c3\u00ba": "ú", "\u00c3\u00a7": "ç",
    # maiúsculas acentuadas (o 2º byte é um caractere de controle C1)
    "\u00c3\x81": "Á", "\u00c3\x80": "À", "\u00c3\x82": "Â", "\u00c3\x83": "Ã",
    "\u00c3\x89": "É", "\u00c3\x8a": "Ê", "\u00c3\x8d": "Í",
    "\u00c3\x93": "Ó", "\u00c3\x94": "Ô", "\u00c3\x95": "Õ", "\u00c3\x9a": "Ú",
    "\u00c3\x87": "Ç",
    # símbolos comuns em texto jurídico
    "N\u00c2\u00ba": "Nº", "n\u00c2\u00ba": "nº",
    "\u00c2\u00ba": "º", "\u00c2\u00aa": "ª", "\u00c2\u00a7": "§", "\u00c2\u00b7": "-",
    "\u00e2\x80\x94": "-", "\u00e2\x80\x93": "-", "\u00e2\x86\x92": "->",
    "\u00e2\x80\u00a2": "-", "\u00e2\u0161\u00a0\u00ef\u00b8\u008f": "ATENÇÃO:",
}


def sem_caracteres_problematicos(texto: str | None) -> str:
    """Normaliza símbolos instáveis para armazenamento/exibição/PDF/DOCX.

    Repara mojibake, remove caracteres invisíveis/de controle e normaliza
    aspas curvas/travessões. PRESERVA acentuação e símbolos jurídicos
    (§, º, ª) — não altera o teor nem a grafia do texto jurídico.
    """
    if not texto:
        return ""

    saida = str(texto)
    for antigo, novo in _MOJIBAKE.items():
        saida = saida.replace(antigo, novo)
    for antigo, novo in _REPLACEMENTS.items():
        saida = saida.replace(antigo, novo)

    saida = "".join(ch for ch in saida if ch == "\n" or ch == "\t" or unicodedata.category(ch)[0] != "C")
    saida = unicodedata.normalize("NFC", saida)
    saida = re.sub(r"[^\S\n]+", " ", saida)
    saida = re.sub(r"\n{3,}", "\n\n", saida)
    return saida.strip()


def ascii_seguro(texto: str | None) -> str:
    """Dobra agressiva para ASCII (comportamento antigo de
    sem_caracteres_problematicos). Use APENAS onde ASCII é obrigatório —
    ex.: nomes de arquivo em Content-Disposition. NUNCA para conteúdo
    jurídico armazenado ou exibido.
    """
    saida = sem_caracteres_problematicos(texto)
    if not saida:
        return ""
    saida = saida.replace("º", "o").replace("ª", "a").replace("§", "paragrafo")
    saida = unicodedata.normalize("NFKD", saida)
    saida = "".join(ch for ch in saida if not unicodedata.combining(ch))
    return saida.encode("ascii", "ignore").decode("ascii").strip()


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
        "RASCUNHO EM PADRAO JURIDICO-PROFISSIONAL PARA REVISAO INTERNA. "
        "O advogado responsavel deve validar fatos, documentos, valores, prazos, "
        "pedidos, citacoes e estrategia antes de assinatura, protocolo ou uso externo."
    )


def aviso_minuta_automatica() -> str:
    return (
        "RASCUNHO AUTOMATICO EM PADRAO JURIDICO-PROFISSIONAL PARA REVISAO INTERNA. "
        "O advogado responsavel deve conferir campos entre colchetes, fatos, documentos, "
        "valores, prazos e citacoes antes de assinatura, protocolo ou uso externo."
    )
