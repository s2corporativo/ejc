"""Conversões pequenas com políticas de ausência explícitas."""
from decimal import Decimal
from typing import Any


def confianca_percentual(value: Any) -> int | None:
    try:
        return max(0, min(100, int(float(value))))
    except (TypeError, ValueError):
        return None


def como_lista(value: Any, *, aceitar_escalar: bool = False) -> list:
    if isinstance(value, list):
        return value
    return [value] if aceitar_escalar and value is not None else []


def decimal_exato(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def nome_local_xml(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def mascara_cnj(digitos: str) -> str:
    """Só montagem; validação/tolerância e normalização pertencem ao chamador."""
    return f"{digitos[:7]}-{digitos[7:9]}.{digitos[9:13]}.{digitos[13]}.{digitos[14:16]}.{digitos[16:20]}"
