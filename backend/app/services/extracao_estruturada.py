# ── app/services/extracao_estruturada.py ────────────────────────────────────
# Extração DETERMINÍSTICA de entidades de texto jurídico (Fase 3A — sem IA).
#
# Regex + heurística + validação de dígito verificador:
#   • processos_cnj — nº CNJ (Res. 65/2008): NNNNNNN-DD.AAAA.J.TR.OOOO
#   • cpfs / cnpjs  — formatados ou só dígitos, SEMPRE validados por DV
#   • datas         — dd/mm/aaaa e "12 de março de 2024"
#   • valores       — monetários em R$
#   • emails / telefones
#
# Cada item traz o trecho encontrado e a posição (inicio/fim) no texto —
# permite realce/auditoria no frontend. Resultado é JSON-serializável e
# gravado em KnowledgeDoc.extra["extracao"].
from __future__ import annotations

import re
from typing import TypedDict

# Teto de ocorrências POR TIPO — protege o JSONB `extra` contra documentos
# patológicos (ex.: planilha com 50k CPFs) sem perder utilidade prática.
MAX_OCORRENCIAS_POR_TIPO = 200


class Ocorrencia(TypedDict):
    valor: str
    inicio: int
    fim: int


# ── Validação de dígito verificador (CPF/CNPJ) ───────────────────────────────

def validar_cpf(cpf: str) -> bool:
    """Valida CPF pelo algoritmo oficial de dígitos verificadores."""
    digitos = re.sub(r"\D", "", cpf)
    if len(digitos) != 11 or digitos == digitos[0] * 11:
        return False
    nums = [int(d) for d in digitos]
    for pos in (9, 10):
        soma = sum(n * p for n, p in zip(nums[:pos], range(pos + 1, 1, -1)))
        dv = (soma * 10) % 11
        if dv == 10:
            dv = 0
        if dv != nums[pos]:
            return False
    return True


def validar_cnpj(cnpj: str) -> bool:
    """Valida CNPJ pelo algoritmo oficial de dígitos verificadores."""
    digitos = re.sub(r"\D", "", cnpj)
    if len(digitos) != 14 or digitos == digitos[0] * 14:
        return False
    nums = [int(d) for d in digitos]
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    for pos, pesos in ((12, pesos1), (13, pesos2)):
        soma = sum(n * p for n, p in zip(nums[:pos], pesos))
        resto = soma % 11
        dv = 0 if resto < 2 else 11 - resto
        if dv != nums[pos]:
            return False
    return True


# ── Padrões ──────────────────────────────────────────────────────────────────
# Guardas (?<!\d) / (?!\d) evitam casar sub-sequências de números maiores
# (ex.: CPF "dentro" de um nº CNJ ou de um código de barras).

_RE_CNJ = re.compile(r"(?<![\d.-])\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}(?![\d.-])")
# CPF: formatado (000.000.000-00) ou 11 dígitos secos — ambos validados por DV.
_RE_CPF = re.compile(r"(?<![\d.\-/])(?:\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})(?![\d.\-/])")
# CNPJ: formatado (00.000.000/0000-00) ou 14 dígitos secos.
_RE_CNPJ = re.compile(r"(?<![\d.\-/])(?:\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{14})(?![\d.\-/])")
_RE_DATA_NUM = re.compile(r"(?<!\d)(?:0?[1-9]|[12]\d|3[01])/(?:0?[1-9]|1[0-2])/(?:19|20)\d{2}(?!\d)")
_MESES = ("janeiro|fevereiro|março|marco|abril|maio|junho|julho|agosto|"
          "setembro|outubro|novembro|dezembro")
_RE_DATA_EXT = re.compile(
    rf"(?<!\d)(?:0?[1-9]|[12]\d|3[01])\s+de\s+(?:{_MESES})\s+de\s+(?:19|20)\d{{2}}(?!\d)",
    re.IGNORECASE,
)
# R$ 1.234.567,89 | R$1234,56 | R$ 100 — separador de milhar opcional.
_RE_VALOR = re.compile(r"R\$\s?\d{1,3}(?:\.\d{3})*(?:,\d{2})?(?![\d,])|R\$\s?\d+(?:,\d{2})?(?![\d,])")
_RE_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# Telefone BR: +55 opcional, DDD entre parênteses ou seco, 8/9 dígitos com
# separador — exige ( ) ou hífen/espaço no meio p/ não casar números soltos.
_RE_FONE = re.compile(
    r"(?<![\d\-])(?:\+?55[\s.]?)?(?:\(\d{2}\)\s?|\d{2}[\s.])9?\d{4}[-\s]\d{4}(?![\d\-])"
)


def _coletar(regex: re.Pattern, texto: str,
             validador=None) -> list[Ocorrencia]:
    encontrados: list[Ocorrencia] = []
    for m in regex.finditer(texto):
        if validador is not None and not validador(m.group(0)):
            continue
        encontrados.append({"valor": m.group(0),
                            "inicio": m.start(), "fim": m.end()})
        if len(encontrados) >= MAX_OCORRENCIAS_POR_TIPO:
            break
    return encontrados


def extrair_estruturas(texto: str) -> dict:
    """Extrai entidades estruturadas do texto. Determinístico, sem IA.

    Retorno JSON-serializável:
        {"processos_cnj": [...], "cpfs": [...], "cnpjs": [...],
         "datas": [...], "valores": [...], "emails": [...],
         "telefones": [...], "total": <int>}
    Cada ocorrência: {"valor", "inicio", "fim"}.
    """
    texto = texto or ""
    cnpjs = _coletar(_RE_CNPJ, texto, validador=validar_cnpj)
    # Evita classificar como CPF os 11 dígitos internos de um CNPJ seco já
    # capturado (sobreposição de intervalos).
    intervalos_cnpj = [(o["inicio"], o["fim"]) for o in cnpjs]

    def _fora_de_cnpj(m_ini: int, m_fim: int) -> bool:
        return not any(ini <= m_ini and m_fim <= fim
                       for ini, fim in intervalos_cnpj)

    cpfs = [o for o in _coletar(_RE_CPF, texto, validador=validar_cpf)
            if _fora_de_cnpj(o["inicio"], o["fim"])]

    datas = _coletar(_RE_DATA_NUM, texto) + _coletar(_RE_DATA_EXT, texto)
    datas.sort(key=lambda o: o["inicio"])

    resultado = {
        "processos_cnj": _coletar(_RE_CNJ, texto),
        "cpfs": cpfs,
        "cnpjs": cnpjs,
        "datas": datas[:MAX_OCORRENCIAS_POR_TIPO],
        "valores": _coletar(_RE_VALOR, texto),
        "emails": _coletar(_RE_EMAIL, texto),
        "telefones": _coletar(_RE_FONE, texto),
    }
    resultado["total"] = sum(len(v) for v in resultado.values())
    return resultado
