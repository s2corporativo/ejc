"""Parsing comum de respostas de IA com políticas explícitas por consumidor.

O padrão conserva a política legada: JSON direto (inclusive escalar/lista),
objeto entre primeiro/último delimitador e None em falha. Os consumidores
selecionam dict obrigatório, vazio {}, cercas ou reparo sem ampliar tolerância.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Literal


def parse_json_response(
    text: str,
    *,
    empty: Literal["none", "dict"] = "none",
    direct: bool = True,
    require_dict: bool = False,
    fences: Literal["none", "first", "strip"] = "none",
    repair: Callable[[str], dict | None] | None = None,
) -> Any:
    """Extrai JSON com a política do chamador; cada fallback {} é independente."""
    if fences == "strip":
        text = re.sub(r"```(?:json)?", "", text.strip()).strip()
    if not text:
        return {} if empty == "dict" else None
    if fences == "first":
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1] if "```" in text[3:] else text[3:]
            text = text.lstrip("json").strip()
    def candidates():
        # Regex só depois da tentativa direta: evita trabalho em JSON válido
        # e mantém a tolerância histórica de json.loads a bytes/bytearray.
        if direct:
            yield text
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            yield match.group(0)

    for candidate in candidates():
        try:
            value = json.loads(candidate)
        except Exception:
            continue
        # JSON direto válido com tipo errado era rejeitado sem tentar extrair
        # um objeto interno; conservar esse limite é importante para arrays.
        return value if not require_dict or isinstance(value, dict) else ({} if empty == "dict" else None)
    if repair is not None:
        return repair(text)
    return {} if empty == "dict" else None


def fechar_json_truncado(texto: str) -> str | None:
    """Fecha as estruturas abertas de um JSON cortado no meio.

    Devolve None quando o corte caiu DENTRO de uma string ou de um escape (aí
    não há fechamento honesto possível) ou quando há fechamento desbalanceado.
    """
    pilha: list[str] = []
    em_string = escape = False
    for ch in texto:
        if escape:
            escape = False
            continue
        if em_string:
            if ch == "\\":
                escape = True
            elif ch == '"':
                em_string = False
            continue
        if ch == '"':
            em_string = True
        elif ch in "{[":
            pilha.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if not pilha or pilha[-1] != ch:
                return None
            pilha.pop()
    if em_string or escape:
        return None
    return texto + "".join(reversed(pilha))

def reparar_json_truncado(bruto: str) -> dict[str, Any] | None:
    """Recupera o máximo possível de um JSON interrompido pelo teto de tokens.

    Tenta o texto inteiro e, em seguida, cortes sucessivos nos últimos
    separadores (`,`/`}`/`]`), descartando o valor incompleto da cauda antes de
    fechar a pilha. O número de tentativas é limitado — reparo é rede de
    segurança, não substituto de orçamento de tokens adequado.
    """
    inicio = bruto.find("{")
    if inicio < 0:
        return None
    texto = bruto[inicio:]
    cortes = [len(texto)]
    for i in range(len(texto) - 1, 0, -1):
        if texto[i] in ",}]":
            cortes.append(i + 1 if texto[i] in "}]" else i)
            if len(cortes) > 60:
                break
    for corte in cortes:
        candidato = fechar_json_truncado(texto[:corte].rstrip().rstrip(","))
        if not candidato:
            continue
        try:
            valor = json.loads(candidato)
        except Exception:
            continue
        if isinstance(valor, dict):
            return valor
    return None
