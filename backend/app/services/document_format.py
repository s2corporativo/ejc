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


# Reparo de mojibake UTF-8 lido como Latin-1 OU como cp1252 ("\u00c3\u00a7" no
# lugar de "\u00e7"; "\u00c3\u2030", "\u00c3\u2021", "\u00e2\u20ac\u201d" — a forma cp1252, a MAIS
# comum, gerada por Word/Windows): restaura o caractere CORRETO acentuado em
# vez de rebaixar para ASCII. A tabela é GERADA a partir das duas
# decodificações erradas de cada caractere — as formas divergem quando um byte
# cai em 0x80–0x9F (controles C1 no latin-1; aspas curvas/travessões no
# cp1252). PRECISA rodar ANTES de _REPLACEMENTS: as substituições de aspas
# curvas/travessões destruiriam os trigramas cp1252 (ex.: "â€\u201d" contém "\u201d").
_CHARS_MOJIBAKE = (
    "áàâãéêíóôõúüçÁÀÂÃÉÊÍÓÔÕÚÜÇºª§"  # acentuação/símbolos jurídicos pt-BR
    "\u2013\u2014\u2018\u2019\u201c\u201d\u2022\u2192"  # – — ‘ ’ “ ” • → (viram ASCII depois, em _REPLACEMENTS)
)

# Bytes sem definição no cp1252 — o WHATWG windows-1252 (usado pelos leitores
# reais que produzem esse mojibake) os mantém como controles C1.
_CP1252_INDEFINIDOS = {0x81, 0x8D, 0x8F, 0x90, 0x9D}


def _decode_cp1252_tolerante(raw: bytes) -> str:
    return "".join(
        chr(b) if b in _CP1252_INDEFINIDOS else bytes([b]).decode("cp1252")
        for b in raw
    )


def _gerar_mojibake() -> dict[str, str]:
    tabela: dict[str, str] = {}
    for ch in _CHARS_MOJIBAKE:
        raw = ch.encode("utf-8")
        for forma in (raw.decode("latin-1"), _decode_cp1252_tolerante(raw)):
            if forma != ch:
                tabela[forma] = ch
    # caso especial observado no corpus (emoji ⚠️ duplamente codificado)
    tabela["\u00e2\u0161\u00a0\u00ef\u00b8\u008f"] = "ATENÇÃO:"
    # sequências mais longas primeiro, para não quebrar trigramas em pares
    return dict(sorted(tabela.items(), key=lambda kv: -len(kv[0])))


_MOJIBAKE = _gerar_mojibake()


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


def juntar_segmentos(segmentos, separador: str) -> str:
    """Junta segmentos de timbre DESCARTANDO os vazios.

    Um segmento é o par rótulo+valor já formatado ("CEP 32510-010"). Quando a
    setting por trás dele não está preenchida, o consumidor passa "" e o
    segmento some por inteiro — o timbre nunca exibe rótulo órfão ("CEP  |")
    nem placeholder de pendência interna.
    """
    return separador.join(s for s in (str(t or "").strip() for t in segmentos) if s)


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
        "RASCUNHO EM PADRÃO JURÍDICO-PROFISSIONAL PARA REVISÃO INTERNA. "
        "O advogado responsável deve validar fatos, documentos, valores, prazos, "
        "pedidos, citações e estratégia antes de assinatura, protocolo ou uso externo."
    )


def aviso_minuta_automatica() -> str:
    return (
        "RASCUNHO AUTOMÁTICO EM PADRÃO JURÍDICO-PROFISSIONAL PARA REVISÃO INTERNA. "
        "O advogado responsável deve conferir campos entre colchetes, fatos, documentos, "
        "valores, prazos e citações antes de assinatura, protocolo ou uso externo."
    )


def marca_minuta_ia() -> str:
    """Marca d'água de origem-IA EMBUTIDA no documento exportado (PDF/DOCX)
    quando a peca e ai_generated e ainda NAO foi human_reviewed. Diferente de
    aviso_rascunho_ia (campo à parte que nao viaja com o arquivo), esta marca
    vai no corpo da 1ª pagina — a salvaguarda acompanha o rascunho baixado ou
    copiado. Versao final revisada sai sem esta marca."""
    return (
        "MINUTA GERADA POR IA - REVISAO E ASSINATURA POR ADVOGADO HABILITADO (OAB) "
        "OBRIGATORIAS. NAO PROTOCOLAR SEM REVISAO."
    )
